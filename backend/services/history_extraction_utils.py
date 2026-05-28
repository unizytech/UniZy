"""
History Extraction Utilities

Shared utilities for extracting and processing patient history data from medical extractions.
Used by both patient_context_service.py and patient_history.py for consistency.

Functions:
1. Nurse Extraction Filtering:
   - filter_nurse_extractions() - Filter out nurse-initiated extractions (nurse_id or PRESCREEN template)
   - is_nurse_extraction() - Check if single extraction is nurse-initiated
   - Legacy aliases: filter_prescreen_extractions, is_prescreen_extraction (for import compatibility)

2. Extraction Data Access:
   - get_extraction_data() - Get edited or original extraction JSON
   - get_segment_from_extraction() - Get segment value from extraction_segments table

3. Segment/Data Extraction:
   - find_segment_value() - Find segment value from multiple possible keys
   - extract_chief_complaints() - Extract complaints from multiple locations
   - extract_vitals() - Extract vitals from multiple locations

4. Data List Extraction:
   - extract_diagnosis_list() - Normalize diagnosis data to list of dicts
   - extract_complaints_list() - Normalize complaints data to list of strings
   - extract_medicines_list() - Normalize medicines data to list of dicts

5. Prescription Extraction:
   - find_prescription_in_extraction() - Find prescription field from all possible locations
   - normalize_prescription_data() - Normalize prescription data to list of medicine dicts
   - parse_medicines_from_text() - Parse medicine names from free-text strings
   - extract_and_normalize_prescription() - Convenience function combining find + normalize

6. Name Normalization:
   - normalize_diagnosis_name() - Normalize diagnosis name for comparison
   - normalize_complaint_name() - Normalize complaint name for comparison
   - normalize_medicine_name() - Imported from medicine_service (comprehensive normalization)

7. Analysis Helpers:
   - get_dominant_level() - Get most common level from a list
   - calculate_trend() - Calculate if levels are improving/worsening/stable
   - is_within_recent_window() - Check if visit is within recent window

8. Change Detection:
   - detect_diagnosis_changes() - Detect new/recurring diagnoses
   - detect_medication_changes() - Detect medication additions/removals/changes
   - detect_complaint_changes() - Detect new/resolved complaints
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# =============================================================================
# Nurse Extraction Filtering Utilities
# =============================================================================

def _get_recording_session_fields(extraction: Dict[str, Any]) -> Dict[str, Any]:
    """Extract recording_sessions fields from an extraction dict (handles dict or list)."""
    rs = extraction.get("recording_sessions")
    if not rs:
        return {}
    if isinstance(rs, dict):
        return rs
    if isinstance(rs, list) and rs:
        return rs[0]
    return {}


def filter_nurse_extractions(
    extractions: List[Dict[str, Any]],
    max_results: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Filter out nurse-initiated extractions from a list.

    Nurse extractions are identified by:
    1. recording_sessions.nurse_id IS NOT NULL (primary check)
    2. template_code contains "PRESCREEN" (legacy fallback for 52 records with NULL nurse_id)

    These extractions typically don't have meaningful clinical data
    (prescriptions, diagnoses, etc.) so they should be excluded from
    patient history queries.

    Args:
        extractions: List of extraction dicts with recording_sessions join
                     (must include recording_sessions(template_code, nurse_id) in select)
        max_results: Optional limit on number of results to return

    Returns:
        List of non-nurse extractions
    """
    filtered = []
    for ext in extractions:
        rs = _get_recording_session_fields(ext)

        # Primary: skip if nurse_id is set
        if rs.get("nurse_id"):
            continue

        # Legacy fallback: skip PRESCREEN template extractions (for records with NULL nurse_id)
        template_code = rs.get("template_code", "") or ""
        if template_code and "PRESCREEN" in template_code.upper():
            continue

        filtered.append(ext)

        if max_results and len(filtered) >= max_results:
            break

    return filtered


# Legacy alias for import compatibility
filter_prescreen_extractions = filter_nurse_extractions


def is_nurse_extraction(extraction: Dict[str, Any]) -> bool:
    """
    Check if a single extraction is a nurse-initiated extraction.

    Checks nurse_id first, then falls back to PRESCREEN template_code for legacy records.

    Args:
        extraction: Extraction dict with recording_sessions join

    Returns:
        True if nurse extraction, False otherwise
    """
    rs = _get_recording_session_fields(extraction)

    # Primary: check nurse_id
    if rs.get("nurse_id"):
        return True

    # Legacy fallback: check PRESCREEN template_code
    template_code = rs.get("template_code", "") or ""
    return bool(template_code and "PRESCREEN" in template_code.upper())


# Legacy alias for import compatibility
is_prescreen_extraction = is_nurse_extraction


# =============================================================================
# Extraction Data Access Utilities
# =============================================================================

def get_extraction_data(extraction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get current extraction data (edited if exists, otherwise original).

    Args:
        extraction: Extraction record dict with edited_extraction_json and/or original_extraction_json

    Returns:
        The extraction JSON dict (edited preferred, original as fallback, empty dict if neither)
    """
    return extraction.get("edited_extraction_json") or extraction.get("original_extraction_json") or {}


def get_segments_batch(
    extraction_ids: List[str],
    segment_codes: List[str],
    supabase_client=None
) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch multiple segments for multiple extractions in ONE query.

    This is much more efficient than calling get_segment_from_extraction() in a loop.
    Handles case-insensitivity by fetching all and matching in memory.

    Args:
        extraction_ids: List of extraction UUID strings
        segment_codes: List of segment codes to fetch (e.g., ['SUMMARY', 'CAUTION'])
        supabase_client: Optional Supabase client (uses default if not provided)

    Returns:
        Nested dict: {extraction_id: {segment_code: segment_value}}
        Example: {"abc-123": {"SUMMARY": {...}, "CAUTION": {...}}}
    """
    if supabase_client is None:
        from services.supabase_service import supabase
        supabase_client = supabase

    if not extraction_ids or not segment_codes:
        return {}

    # Build list of all case variants for segment codes
    all_code_variants = set()
    for code in segment_codes:
        all_code_variants.add(code)
        all_code_variants.add(code.lower())
        all_code_variants.add(code.upper())

    try:
        # Single query to fetch all segments for all extractions
        # Include version_type so we can prefer edited over original
        result = supabase_client.table("extraction_segments")\
            .select("extraction_id, segment_code, segment_value, version_type")\
            .in_("extraction_id", extraction_ids)\
            .in_("segment_code", list(all_code_variants))\
            .execute()

        # Build result dict with case-insensitive matching
        segments_by_extraction: Dict[str, Dict[str, Any]] = {eid: {} for eid in extraction_ids}
        # Track version_type per extraction+code so edited overrides original
        version_tracker: Dict[str, Dict[str, str]] = {eid: {} for eid in extraction_ids}

        for row in result.data or []:
            eid = row.get("extraction_id")
            code = row.get("segment_code", "")
            value = row.get("segment_value")
            version_type = row.get("version_type", "original")

            if not eid or not value:
                continue

            # Match to original requested code (case-insensitive)
            for requested_code in segment_codes:
                if code.lower() == requested_code.lower():
                    key = requested_code.upper()
                    existing_version = version_tracker.get(eid, {}).get(key)
                    # Store if: no existing entry, OR existing is "original" and new is "edited"
                    if existing_version is None or (existing_version == "original" and version_type == "edited"):
                        segments_by_extraction[eid][key] = value
                        version_tracker[eid][key] = version_type
                    break

        logger.debug(
            f"[HISTORY_UTILS] Batch fetched segments for {len(extraction_ids)} extractions, "
            f"codes={segment_codes}, found={sum(len(v) for v in segments_by_extraction.values())} segments"
        )

        return segments_by_extraction

    except Exception as e:
        logger.warning(f"[HISTORY_UTILS] Error in batch segment fetch: {e}")
        return {eid: {} for eid in extraction_ids}


def get_segment_from_extraction(
    extraction_id: str,
    segment_code: str,
    supabase_client=None
) -> Optional[Dict[str, Any]]:
    """
    Get a specific segment value from extraction_segments table.

    NOTE: For multiple extractions, use get_segments_batch() instead for better performance.

    Handles case-insensitivity by trying the provided code, lowercase, and uppercase versions.

    Args:
        extraction_id: Extraction UUID string
        segment_code: Segment code (e.g., 'CAUTION', 'SUMMARY', 'summary')
        supabase_client: Optional Supabase client (uses default if not provided)

    Returns:
        Segment value dict or None if not found
    """
    if supabase_client is None:
        from services.supabase_service import supabase
        supabase_client = supabase

    try:
        # Try exact match first
        result = supabase_client.table("extraction_segments")\
            .select("segment_value")\
            .eq("extraction_id", extraction_id)\
            .eq("segment_code", segment_code)\
            .limit(1)\
            .execute()

        if result.data and result.data[0].get("segment_value"):
            return result.data[0]["segment_value"]

        # If not found, try lowercase version
        result = supabase_client.table("extraction_segments")\
            .select("segment_value")\
            .eq("extraction_id", extraction_id)\
            .eq("segment_code", segment_code.lower())\
            .limit(1)\
            .execute()

        if result.data and result.data[0].get("segment_value"):
            return result.data[0]["segment_value"]

        # If still not found, try uppercase version
        result = supabase_client.table("extraction_segments")\
            .select("segment_value")\
            .eq("extraction_id", extraction_id)\
            .eq("segment_code", segment_code.upper())\
            .limit(1)\
            .execute()

        if result.data and result.data[0].get("segment_value"):
            return result.data[0]["segment_value"]

        return None

    except Exception as e:
        logger.warning(f"[HISTORY_UTILS] Error getting segment {segment_code} for extraction {extraction_id}: {e}")
        return None


# =============================================================================
# Prescription Extraction Utilities
# =============================================================================

def find_prescription_in_extraction(ext_data: Dict[str, Any]) -> Optional[Any]:
    """
    Find prescription data from extraction JSON, checking all possible locations.

    Checks:
    1. Top-level keys: prescription, prescriptionOp, prescriptionDischarge, medications, drugs, drugDetails
    2. Nested in treatmentPlan: treatmentPlan.prescription, treatmentPlan.medications
    3. Nested in treatment: treatment.prescription, treatment.medications

    Args:
        ext_data: Full extraction JSON dict

    Returns:
        Prescription data (can be list, dict, or string) or None if not found
    """
    if not ext_data or not isinstance(ext_data, dict):
        return None

    # Top-level keys to check (in priority order)
    top_level_keys = [
        'prescription', 'prescriptionOp', 'prescriptionDischarge',
        'medications', 'drugs', 'drugDetails'
    ]

    # Check top-level keys first
    for key in top_level_keys:
        if key in ext_data and ext_data[key]:
            return ext_data[key]
        # Also check case variations
        for ext_key in ext_data.keys():
            if ext_key.lower() == key.lower() and ext_data[ext_key]:
                return ext_data[ext_key]

    # Check nested locations
    nested_paths = [
        ('treatmentPlan', 'prescription'),
        ('treatmentPlan', 'medications'),
        ('treatmentPlanAdviceOp', 'prescription'),
        ('treatmentPlanAdviceOp', 'medications'),
        ('treatmentPlanAdviceDischarge', 'prescription'),
        ('treatmentPlanAdviceDischarge', 'medications'),
        ('treatment', 'prescription'),
        ('treatment', 'medications'),
    ]

    for parent_key, child_key in nested_paths:
        # Check exact key
        if parent_key in ext_data and isinstance(ext_data[parent_key], dict):
            parent = ext_data[parent_key]
            if child_key in parent and parent[child_key]:
                return parent[child_key]
        # Check case variations for parent
        for ext_key in ext_data.keys():
            if ext_key.lower() == parent_key.lower() and isinstance(ext_data[ext_key], dict):
                parent = ext_data[ext_key]
                if child_key in parent and parent[child_key]:
                    return parent[child_key]

    return None


def normalize_prescription_data(
    prescription_data: Any,
    include_raw_text: bool = False
) -> List[Dict[str, Any]]:
    """
    Normalize prescription data to a list of medicine dictionaries.

    Handles:
    - List of medicine dicts
    - List of medicine strings
    - Dict with nested prescription/medications/medicines
    - String prescription (parses medicine names from text)

    Args:
        prescription_data: Raw prescription data (list, dict, or string)
        include_raw_text: If True, include 'raw_text' field for string prescriptions

    Returns:
        List of dicts with keys: name, dosage, duration, (optionally raw_text)
    """
    medicines = []

    if prescription_data is None:
        return medicines

    if isinstance(prescription_data, list):
        # List of medicines
        for med in prescription_data:
            if isinstance(med, dict):
                medicines.append({
                    'name': med.get('name') or med.get('medicine') or med.get('drug_name', ''),
                    'dosage': med.get('dosage') or med.get('dose', ''),
                    'duration': med.get('durationDays') or med.get('duration', ''),
                })
            elif isinstance(med, str) and med.strip():
                medicines.append({'name': med.strip(), 'dosage': '', 'duration': ''})

    elif isinstance(prescription_data, dict):
        # Dict with nested list
        if 'prescription' in prescription_data:
            return normalize_prescription_data(prescription_data['prescription'], include_raw_text)
        if 'medications' in prescription_data:
            return normalize_prescription_data(prescription_data['medications'], include_raw_text)
        if 'medicines' in prescription_data:
            return normalize_prescription_data(prescription_data['medicines'], include_raw_text)
        if 'drugs' in prescription_data:
            return normalize_prescription_data(prescription_data['drugs'], include_raw_text)
        # Single medicine dict
        if prescription_data.get('name') or prescription_data.get('medicine') or prescription_data.get('drug_name'):
            medicines.append({
                'name': prescription_data.get('name') or prescription_data.get('medicine') or prescription_data.get('drug_name', ''),
                'dosage': prescription_data.get('dosage') or prescription_data.get('dose', ''),
                'duration': prescription_data.get('durationDays') or prescription_data.get('duration', ''),
            })

    elif isinstance(prescription_data, str):
        # String prescription - parse medicine names
        parsed = parse_medicines_from_text(prescription_data, include_raw_text)
        if parsed:
            medicines.extend(parsed)

    return medicines


def parse_medicines_from_text(
    text: str,
    include_raw_text: bool = False
) -> List[Dict[str, Any]]:
    """
    Parse medicine names from free-text prescription strings.

    Handles patterns like:
    - "Doctor prescribed: 1) Penicillin, to be taken once every two days."
    - "Paracetamol 500mg TID, Omeprazole 20mg OD"
    - "Tab. Metformin 500mg twice daily"

    Args:
        text: Free-text prescription string
        include_raw_text: If True, include 'raw_text' field with original text

    Returns:
        List of dicts with keys: name, dosage, duration, (optionally raw_text)
        Returns empty list if text is vague (e.g., "continue previous medication")
    """
    medicines = []

    if not text or not text.strip():
        return medicines

    # Skip vague/continuation phrases - these don't contain actual medicine names
    vague_patterns = [
        r'continue\s+(with\s+)?(the\s+)?same\s+medication',
        r'continue\s+previous',
        r'same\s+medicines?\s+as\s+before',
        r'repeat\s+prescription',
        r'no\s+change\s+in\s+medication',
    ]
    for pattern in vague_patterns:
        if re.search(pattern, text.lower()):
            logger.debug(f"[HISTORY_UTILS] Skipping vague prescription text: {text[:50]}...")
            return medicines

    def add_medicine(name: str, dosage: str = '', duration: str = ''):
        """Helper to add medicine with optional raw_text"""
        name = name.strip().rstrip(',.')
        if name and len(name) > 2:
            med = {'name': name, 'dosage': dosage, 'duration': duration}
            if include_raw_text:
                med['raw_text'] = text
            medicines.append(med)

    # Pattern 1: Numbered list like "1) Penicillin, 2) Amoxicillin"
    numbered_pattern = r'\d+\)\s*([A-Za-z][A-Za-z\s\-]+?)(?:,|\.|to be|twice|once|for\s+\d|$)'
    numbered_matches = re.findall(numbered_pattern, text)
    if numbered_matches:
        for match in numbered_matches:
            add_medicine(match)
        if medicines:
            return medicines

    # Pattern 2: Common medicine prefixes (Tab., Cap., Syp., Inj.)
    prefix_pattern = r'(?:Tab\.?|Cap\.?|Syp\.?|Inj\.?|Tablet|Capsule|Syrup|Injection)\s+([A-Za-z][A-Za-z0-9\s\-]+?)(?:\s+\d|,|\.|$)'
    prefix_matches = re.findall(prefix_pattern, text, re.IGNORECASE)
    if prefix_matches:
        for match in prefix_matches:
            add_medicine(match)
        if medicines:
            return medicines

    # Pattern 3: Medicine name followed by dosage like "Paracetamol 500mg"
    dosage_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(\d+\s*(?:mg|mcg|ml|g|IU))'
    dosage_matches = re.findall(dosage_pattern, text)
    if dosage_matches:
        for med_name, dosage in dosage_matches:
            add_medicine(med_name, dosage)
        if medicines:
            return medicines

    # Pattern 4: "prescribed: X" or "prescribed X"
    prescribed_pattern = r'prescribed[:\s]+([A-Za-z][A-Za-z\s\-]+?)(?:,|\.|to be|twice|once|for|$)'
    prescribed_matches = re.findall(prescribed_pattern, text, re.IGNORECASE)
    skip_words = {'the', 'same', 'previous', 'medication', 'doctor', 'patient'}
    for match in prescribed_matches:
        med_name = match.strip().rstrip(',.')
        if med_name and len(med_name) > 2 and med_name.lower() not in skip_words:
            add_medicine(med_name)

    return medicines


def extract_and_normalize_prescription(
    ext_data: Dict[str, Any],
    include_raw_text: bool = False
) -> List[Dict[str, Any]]:
    """
    Convenience function that combines find + normalize.

    Finds prescription in extraction data and normalizes to list of medicine dicts.

    Args:
        ext_data: Full extraction JSON dict
        include_raw_text: If True, include 'raw_text' field for string prescriptions

    Returns:
        List of dicts with keys: name, dosage, duration, (optionally raw_text)
    """
    prescription_data = find_prescription_in_extraction(ext_data)
    if prescription_data is None:
        return []
    return normalize_prescription_data(prescription_data, include_raw_text)


# =============================================================================
# Segment/Data Extraction Utilities
# =============================================================================

def find_segment_value(data: Dict[str, Any], *keys: str) -> Optional[Any]:
    """
    Find first matching segment value from multiple possible keys.

    Handles case variations (lowercase, camelCase) automatically.

    Args:
        data: Extraction data dict
        *keys: Variable number of keys to search for

    Returns:
        First matching value or None
    """
    for key in keys:
        if key in data:
            return data[key]
        # Try case variations
        lower_key = key.lower()
        camel_key = ''.join(word.capitalize() if i > 0 else word.lower()
                           for i, word in enumerate(key.split('_')))
        for k in data.keys():
            if k.lower() == lower_key or k == camel_key:
                return data[k]
    return None


def extract_chief_complaints(data: Dict[str, Any]) -> Optional[Any]:
    """
    Extract chief complaints from multiple possible locations.

    Chief complaints can be found in:
    1. Direct keys: chiefComplaints, chiefComplaintsOp, chiefComplaintsDischarge, complaints
    2. Embedded in history object: history.chief_complaints
    3. Embedded in chiefComplaints object: chiefComplaints.chief_complaints

    Args:
        data: Extraction data dict

    Returns:
        Chief complaints data or None
    """
    # First try direct keys
    complaints = find_segment_value(
        data,
        'chiefComplaints', 'chiefComplaintsOp', 'chiefComplaintsDischarge',
        'complaints', 'chief_complaints'
    )

    if complaints:
        # If it's a dict with chief_complaints inside, extract it
        if isinstance(complaints, dict) and 'chief_complaints' in complaints:
            return complaints['chief_complaints']
        return complaints

    # Fallback: Check if chief_complaints is embedded in history object
    history = find_segment_value(data, 'history', 'historyOp', 'historyDischarge')
    if history and isinstance(history, dict):
        if 'chief_complaints' in history:
            return history['chief_complaints']
        # Also check camelCase variant
        if 'chiefComplaints' in history:
            return history['chiefComplaints']

    return None


def extract_vitals(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract vitals from the dedicated VITALS segment.

    Args:
        data: Extraction data dict

    Returns:
        Vitals dict or None
    """
    vitals = find_segment_value(data, 'vitals')
    if vitals:
        return vitals

    return None


# =============================================================================
# Data List Extraction Utilities
# =============================================================================

def extract_diagnosis_list(diagnosis_data: Any) -> List[Dict[str, Any]]:
    """
    Extract normalized diagnosis list from various formats.

    Handles:
    - List of diagnosis dicts
    - List of diagnosis strings
    - Dict with primary_diagnosis/secondary_diagnoses
    - Single string diagnosis

    Args:
        diagnosis_data: Raw diagnosis data

    Returns:
        List of dicts with keys: name, code, type
    """
    diagnoses = []

    if diagnosis_data is None:
        return diagnoses

    if isinstance(diagnosis_data, list):
        for dx in diagnosis_data:
            if isinstance(dx, dict):
                diagnoses.append({
                    'name': dx.get('name') or dx.get('diagnosis') or dx.get('primary_diagnosis') or str(dx),
                    'code': dx.get('code') or dx.get('icd_code') or dx.get('icd10_code'),
                    'type': dx.get('type', 'unspecified')
                })
            elif isinstance(dx, str):
                diagnoses.append({'name': dx, 'code': None, 'type': 'unspecified'})
    elif isinstance(diagnosis_data, dict):
        # Single diagnosis as dict
        if 'primary_diagnosis' in diagnosis_data:
            diagnoses.append({
                'name': diagnosis_data['primary_diagnosis'],
                'code': diagnosis_data.get('icd_code'),
                'type': 'Primary'
            })
        if 'secondary_diagnoses' in diagnosis_data:
            for dx in diagnosis_data['secondary_diagnoses']:
                if isinstance(dx, str):
                    diagnoses.append({'name': dx, 'code': None, 'type': 'Secondary'})
                elif isinstance(dx, dict):
                    diagnoses.append({
                        'name': dx.get('name', str(dx)),
                        'code': dx.get('code'),
                        'type': 'Secondary'
                    })
        # If it's a simple dict with name
        if 'name' in diagnosis_data:
            diagnoses.append({
                'name': diagnosis_data['name'],
                'code': diagnosis_data.get('code'),
                'type': diagnosis_data.get('type', 'unspecified')
            })
    elif isinstance(diagnosis_data, str):
        diagnoses.append({'name': diagnosis_data, 'code': None, 'type': 'unspecified'})

    return diagnoses


def extract_complaints_list(complaints_data: Any) -> List[str]:
    """
    Extract normalized complaints list from various formats.

    Handles:
    - List of complaint strings
    - List of complaint dicts
    - Dict with primary_complaint/secondary_complaints
    - Single string complaint

    Args:
        complaints_data: Raw complaints data

    Returns:
        List of complaint strings
    """
    complaints = []

    if complaints_data is None:
        return complaints

    if isinstance(complaints_data, list):
        for c in complaints_data:
            if isinstance(c, str):
                complaints.append(c)
            elif isinstance(c, dict):
                complaints.append(c.get('complaint') or c.get('name') or str(c))
    elif isinstance(complaints_data, dict):
        if 'primary_complaint' in complaints_data:
            complaints.append(complaints_data['primary_complaint'])
        if 'secondary_complaints' in complaints_data:
            for c in complaints_data['secondary_complaints']:
                if isinstance(c, str):
                    complaints.append(c)
        if 'complaints' in complaints_data:
            return extract_complaints_list(complaints_data['complaints'])
        if 'main_complaint' in complaints_data:
            complaints.append(complaints_data['main_complaint'])
    elif isinstance(complaints_data, str):
        complaints.append(complaints_data)

    return complaints


def extract_medicines_list(prescription_data: Any) -> List[Dict[str, Any]]:
    """
    Extract normalized medicine list from prescription data.

    Uses normalize_prescription_data for consistent parsing across the codebase.

    Args:
        prescription_data: Raw prescription data

    Returns:
        List of medicine dicts with keys: name, dosage, duration
    """
    return normalize_prescription_data(prescription_data)


# =============================================================================
# Name Normalization Utilities
# =============================================================================
# Note: normalize_diagnosis_name() and normalize_complaint_name() have identical
# implementations but are kept separate for semantic clarity and future extensibility
# (e.g., diagnoses might need "suspected" prefix removal in the future)

def normalize_diagnosis_name(name: str) -> str:
    """
    Normalize diagnosis name for comparison.

    Args:
        name: Raw diagnosis name

    Returns:
        Lowercased, stripped name
    """
    return name.lower().strip() if name else ""


def normalize_complaint_name(name: str) -> str:
    """
    Normalize complaint name for comparison.

    Args:
        name: Raw complaint name

    Returns:
        Lowercased, stripped name
    """
    return name.lower().strip() if name else ""


# normalize_medicine_name is imported from medicine_service to avoid duplication
# It's more comprehensive there (handles prefixes like TAB., CAP., etc.)
from services.medicine_service import normalize_medicine_name


# =============================================================================
# Analysis Helper Utilities
# =============================================================================

def get_dominant_level(levels: List[str]) -> str:
    """
    Get the most common level from a list.

    Normalizes levels (high/severe → High, moderate/medium → Moderate, etc.)
    and returns the most frequent one.

    Args:
        levels: List of level strings

    Returns:
        Most common normalized level or "Unknown"
    """
    if not levels:
        return "Unknown"

    # Normalize levels
    normalized = []
    for lvl in levels:
        lvl_lower = lvl.lower() if lvl else ""
        if "high" in lvl_lower or "severe" in lvl_lower:
            normalized.append("High")
        elif "moderate" in lvl_lower or "medium" in lvl_lower:
            normalized.append("Moderate")
        elif "low" in lvl_lower or "mild" in lvl_lower or "minimal" in lvl_lower:
            normalized.append("Low")
        elif "none" in lvl_lower or "no " in lvl_lower:
            normalized.append("None")
        else:
            normalized.append(lvl.capitalize() if lvl else "Unknown")

    # Count occurrences
    counts = {}
    for lvl in normalized:
        counts[lvl] = counts.get(lvl, 0) + 1

    # Return most common
    return max(counts.items(), key=lambda x: x[1])[0]


def calculate_trend(levels: List[str]) -> Optional[str]:
    """
    Calculate if levels are improving, worsening, or stable.

    Higher scores = worse (for anxiety/concerns).
    Trend is based on comparing first half to second half average.

    Args:
        levels: List of level strings (oldest to newest)

    Returns:
        "improving", "worsening", "stable", or None if insufficient data
    """
    if len(levels) < 2:
        return None

    # Convert to numeric (higher = worse for anxiety/concerns)
    def to_score(lvl: str) -> int:
        lvl_lower = lvl.lower() if lvl else ""
        if "high" in lvl_lower or "severe" in lvl_lower:
            return 3
        elif "moderate" in lvl_lower or "medium" in lvl_lower:
            return 2
        elif "low" in lvl_lower or "mild" in lvl_lower or "minimal" in lvl_lower:
            return 1
        elif "none" in lvl_lower or "no " in lvl_lower:
            return 0
        else:
            return 1  # Default to low

    scores = [to_score(lvl) for lvl in levels]

    # Compare first half average to second half average
    mid = len(scores) // 2
    first_avg = sum(scores[:mid]) / mid if mid > 0 else scores[0]
    second_avg = sum(scores[mid:]) / (len(scores) - mid) if len(scores) > mid else scores[-1]

    diff = second_avg - first_avg
    if diff < -0.5:
        return "improving"
    elif diff > 0.5:
        return "worsening"
    return "stable"


def is_within_recent_window(
    visit_date: str,
    current_date: str,
    max_visits_dates: List[str],
    max_visits: int = 2,
    max_months: int = 6
) -> bool:
    """
    Check if a visit is within the recent window for "new" diagnosis detection.

    Window is: last N visits OR last M months, whichever is smaller (earlier cutoff).

    Args:
        visit_date: ISO date string of the visit to check
        current_date: ISO date string of current/reference date
        max_visits_dates: List of visit dates (most recent first)
        max_visits: Maximum number of visits in window (default 2)
        max_months: Maximum months in window (default 6)

    Returns:
        True if visit is within the recent window
    """
    try:
        current_dt = datetime.fromisoformat(current_date.replace('Z', '+00:00'))
        visit_dt = datetime.fromisoformat(visit_date.replace('Z', '+00:00'))

        # Check if within last N months
        months_ago = current_dt - timedelta(days=30 * max_months)
        within_months = visit_dt >= months_ago

        # Check if within last N visits
        within_visits = visit_date in max_visits_dates[:max_visits]

        # Return true if within BOTH constraints (whichever is earlier/smaller window)
        return within_months and within_visits
    except Exception:
        return False


# =============================================================================
# Change Detection Utilities
# =============================================================================

def detect_diagnosis_changes(
    current_diagnoses: List[Dict[str, Any]],
    previous_visits_diagnoses: List[List[Dict[str, Any]]],
    all_historical_diagnoses: set,
    recent_window_diagnoses: set
) -> List[Dict[str, Any]]:
    """
    Detect diagnosis changes for a visit.

    Logic:
    - If diagnosis NOT in recent_window AND NOT in all_history → "first_time_diagnosis"
    - If diagnosis NOT in recent_window BUT in all_history → "recurring_diagnosis"
    - Otherwise → no change label

    Args:
        current_diagnoses: List of diagnosis dicts for current visit
        previous_visits_diagnoses: List of diagnosis lists from previous visits
        all_historical_diagnoses: Set of all normalized diagnosis names ever
        recent_window_diagnoses: Set of normalized diagnosis names in recent window

    Returns:
        List of change dicts with keys: type, category, name, details, confidence
    """
    changes = []

    for dx in current_diagnoses:
        dx_name = normalize_diagnosis_name(dx.get('name', ''))
        if not dx_name:
            continue

        in_recent = dx_name in recent_window_diagnoses
        in_all_history = dx_name in all_historical_diagnoses

        if not in_recent:
            if not in_all_history:
                # First time ever
                changes.append({
                    "type": "first_time_diagnosis",
                    "category": "diagnosis",
                    "name": dx.get('name', ''),
                    "details": dx.get('code') or dx.get('icd_code'),
                    "confidence": "high"
                })
            else:
                # Was seen before but not recently - recurring
                changes.append({
                    "type": "recurring_diagnosis",
                    "category": "diagnosis",
                    "name": dx.get('name', ''),
                    "details": dx.get('code') or dx.get('icd_code'),
                    "confidence": "high"
                })

    return changes


def detect_medication_changes(
    current_medications: List[Dict[str, Any]],
    previous_medications: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Detect medication changes between current and previous visit.

    Detects:
    - medication_added: New medicine not in previous visit
    - medication_removed: Medicine was in previous but not in current
    - medication_changed: Same medicine but different dosage

    Args:
        current_medications: List of medicine dicts for current visit
        previous_medications: List of medicine dicts for previous visit

    Returns:
        List of change dicts with keys: type, category, name, details, previous_value, new_value
    """
    changes = []

    # Normalize current and previous
    current_meds = {normalize_medicine_name(m.get('name', '')): m for m in current_medications if m.get('name')}
    previous_meds = {normalize_medicine_name(m.get('name', '')): m for m in previous_medications if m.get('name')}

    # Find added medications
    for med_key, med in current_meds.items():
        if med_key not in previous_meds:
            changes.append({
                "type": "medication_added",
                "category": "medication",
                "name": med.get('name', ''),
                "details": f"Dosage: {med.get('dosage', 'N/A')}, Duration: {med.get('duration', 'N/A')}",
                "new_value": med.get('dosage', '')
            })
        else:
            # Check for dosage change
            prev_med = previous_meds[med_key]
            curr_dosage = str(med.get('dosage', '')).lower().strip()
            prev_dosage = str(prev_med.get('dosage', '')).lower().strip()

            if curr_dosage and prev_dosage and curr_dosage != prev_dosage:
                changes.append({
                    "type": "medication_changed",
                    "category": "medication",
                    "name": med.get('name', ''),
                    "details": f"Dosage changed from {prev_dosage} to {curr_dosage}",
                    "previous_value": prev_dosage,
                    "new_value": curr_dosage
                })

    # Find removed medications
    for med_key, med in previous_meds.items():
        if med_key not in current_meds:
            changes.append({
                "type": "medication_removed",
                "category": "medication",
                "name": med.get('name', ''),
                "details": f"Was: {med.get('dosage', 'N/A')}",
                "previous_value": med.get('dosage', '')
            })

    return changes


def detect_complaint_changes(
    current_complaints: List[str],
    previous_complaints: List[str],
    two_visits_ago_complaints: List[str],
    current_diagnoses_normalized: set
) -> List[Dict[str, Any]]:
    """
    Detect complaint changes with resolution inference.

    Logic:
    - If complaint in previous but NOT in current:
      - If also not in two_visits_ago → "complaint_not_mentioned" (low confidence)
      - If was in two_visits_ago AND related diagnosis gone → "complaint_resolved" (high)
      - If was in two_visits_ago but diagnosis still active → "complaint_not_mentioned" (medium)
    - If complaint in current but NOT in previous → "complaint_new"

    Args:
        current_complaints: List of complaint strings for current visit
        previous_complaints: List of complaint strings for previous visit
        two_visits_ago_complaints: List of complaint strings from 2 visits ago
        current_diagnoses_normalized: Set of normalized diagnosis names

    Returns:
        List of change dicts with keys: type, category, name, confidence
    """
    changes = []

    current_normalized = {normalize_complaint_name(c) for c in current_complaints}
    previous_normalized = {normalize_complaint_name(c) for c in previous_complaints}
    two_ago_normalized = {normalize_complaint_name(c) for c in two_visits_ago_complaints}

    # Find new complaints
    for complaint in current_complaints:
        if normalize_complaint_name(complaint) not in previous_normalized:
            changes.append({
                "type": "complaint_new",
                "category": "complaint",
                "name": complaint,
                "confidence": "high"
            })

    # Find potentially resolved complaints
    for complaint in previous_complaints:
        complaint_norm = normalize_complaint_name(complaint)
        if complaint_norm not in current_normalized:
            # Complaint was in previous but not in current
            was_in_two_ago = complaint_norm in two_ago_normalized

            if was_in_two_ago:
                # Was present for at least 2 visits, now gone
                # Check if there's a related diagnosis still active (simplified check)
                complaint_words = set(complaint_norm.split())
                related_diagnosis_active = any(
                    word in dx for word in complaint_words for dx in current_diagnoses_normalized
                    if len(word) > 3  # Skip short words
                )

                if related_diagnosis_active:
                    changes.append({
                        "type": "complaint_not_mentioned",
                        "category": "complaint",
                        "name": complaint,
                        "confidence": "medium"
                    })
                else:
                    changes.append({
                        "type": "complaint_resolved",
                        "category": "complaint",
                        "name": complaint,
                        "confidence": "high"
                    })
            else:
                # Only in last visit, now gone - low confidence
                changes.append({
                    "type": "complaint_not_mentioned",
                    "category": "complaint",
                    "name": complaint,
                    "confidence": "low"
                })

    return changes

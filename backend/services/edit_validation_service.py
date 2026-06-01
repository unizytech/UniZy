"""
Edit Validation Service - Post-enrichment warnings for extraction edit-save flow.

Inspects enriched data AFTER postprocessing and generates user-facing warnings
about missing EHR IDs, missing segments, and edit feedback compatibility issues.

Warnings are non-blocking: the save always succeeds regardless of warnings.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Common field names used across templates
_PRESCRIPTION_KEYS = ['prescription', 'medications', 'drugs', 'prescribedMedicines']
_INVESTIGATION_KEYS = ['investigations', 'labs', 'tests', 'labTests']
_MEDICINE_NAME_FIELDS = ['name', 'medicine_name', 'drugName', 'medication']
_INVESTIGATION_NAME_FIELDS = ['name', 'Test_Name', 'test_name', 'investigation_name']


def _find_prescription_items(data: Dict[str, Any]) -> Tuple[Optional[str], List[dict]]:
    """Find prescription items in extraction data. Returns (key_name, list_of_meds)."""
    for key in _PRESCRIPTION_KEYS:
        if key in data:
            val = data[key]
            if isinstance(val, list):
                return key, [m for m in val if isinstance(m, dict)]
            elif isinstance(val, dict):
                # Check for nested list inside dict
                for nested_key in ['prescription', 'medications', 'drugs', 'items']:
                    if nested_key in val and isinstance(val[nested_key], list):
                        return key, [m for m in val[nested_key] if isinstance(m, dict)]
                return key, [val]
            return key, []
    return None, []


def _find_investigation_items(data: Dict[str, Any]) -> Tuple[Optional[str], List[dict]]:
    """Find investigation items in extraction data. Returns (key_name, list_of_tests)."""
    # Check top-level keys
    for key in _INVESTIGATION_KEYS:
        if key in data:
            val = data[key]
            if isinstance(val, list):
                return key, [t for t in val if isinstance(t, dict)]
            elif isinstance(val, dict):
                # Dict format with laboratory_tests, imaging_studies, etc.
                items = []
                for sub_key in ['laboratory_tests', 'imaging_studies', 'other_tests']:
                    if sub_key in val and isinstance(val[sub_key], list):
                        items.extend([t for t in val[sub_key] if isinstance(t, dict)])
                return key, items
            return key, []

    # Check nested inside clinicalNotes/CLINICAL_NOTES
    for parent_key in ['clinicalNotes', 'CLINICAL_NOTES']:
        parent = data.get(parent_key)
        if isinstance(parent, dict):
            for key in _INVESTIGATION_KEYS:
                if key in parent:
                    val = parent[key]
                    if isinstance(val, list):
                        return key, [t for t in val if isinstance(t, dict)]
    return None, []


def _get_item_name(item: dict, name_fields: List[str]) -> str:
    """Extract name from item dict using field priority list."""
    for field in name_fields:
        val = item.get(field)
        if val:
            return str(val)
    return ""


def generate_edit_warnings(
    enriched_data: Dict[str, Any],
    ehr_code: Optional[str],
    template_code: Optional[str],
    original_extraction: Optional[Dict[str, Any]],
    edited_extraction: Dict[str, Any],
) -> List[dict]:
    """
    Inspect enriched extraction data and generate user-facing warnings.

    Args:
        enriched_data: Extraction data after postprocessing (with _external_id etc.)
        ehr_code: Counsellor's EHR type (e.g., "aosta", "kg_ehr", "raster", or None)
        template_code: Template code for context
        original_extraction: Original AI extraction (before any edits)
        edited_extraction: Raw edit data before enrichment

    Returns:
        List of dicts with {category, severity, message}
    """
    warnings = []

    try:
        if ehr_code == "aosta":
            warnings.extend(_check_aosta_warnings(enriched_data))
        elif ehr_code == "kg_ehr":
            warnings.extend(_check_kg_warnings(enriched_data))
        elif ehr_code == "raster":
            warnings.extend(_check_raster_warnings(enriched_data))

        # Medicine edit feedback check (all EHR types)
        if original_extraction and edited_extraction:
            warnings.extend(_check_feedback_compatibility(original_extraction, edited_extraction))

    except Exception as e:
        logger.warning(f"[EDIT_VALIDATION] Error generating warnings: {e}")

    return warnings


def _check_aosta_warnings(data: Dict[str, Any]) -> List[dict]:
    """Check AOSTA-specific warnings for missing EHR IDs."""
    warnings = []

    # Check medicines
    _, meds = _find_prescription_items(data)
    missing_meds = []
    for med in meds:
        if not med.get("_external_id"):
            name = _get_item_name(med, _MEDICINE_NAME_FIELDS)
            if name:
                missing_meds.append(name)

    if missing_meds:
        warnings.append({
            "category": "ehr_medicines",
            "severity": "warning",
            "message": f"{len(missing_meds)} medicine(s) missing EHR brand ID — will be sent to AOSTA with brand_id='null': {', '.join(missing_meds)}"
        })

    # Check investigations
    _, tests = _find_investigation_items(data)
    missing_tests = []
    for test in tests:
        if not test.get("_external_id") and not test.get("Test_id"):
            name = _get_item_name(test, _INVESTIGATION_NAME_FIELDS)
            if name:
                missing_tests.append(name)

    if missing_tests:
        warnings.append({
            "category": "ehr_investigations",
            "severity": "warning",
            "message": f"{len(missing_tests)} investigation(s) missing Test_id — will be sent to AOSTA with Test_id='null': {', '.join(missing_tests)}"
        })

    return warnings


def _check_kg_warnings(data: Dict[str, Any]) -> List[dict]:
    """Check KG EHR-specific warnings for missing segments."""
    warnings = []

    # Check vitals
    vitals = data.get("VITALS") or data.get("vitals")
    if not vitals or (isinstance(vitals, dict) and not vitals):
        warnings.append({
            "category": "ehr_segments",
            "severity": "info",
            "message": "Vitals segment is empty — KG EHR will receive empty vitals"
        })

    # Check general history
    history = data.get("GENERAL_HISTORY") or data.get("generalHistory")
    if not history:
        warnings.append({
            "category": "ehr_segments",
            "severity": "info",
            "message": "General history is missing — medical history checkboxes will default to 'No' in KG EHR"
        })

    # Check prescription
    rx_key, rx_items = _find_prescription_items(data)
    if not rx_key or not rx_items:
        warnings.append({
            "category": "ehr_segments",
            "severity": "info",
            "message": "Prescription is empty — no medicines will be sent to KG EHR"
        })

    return warnings


def _check_raster_warnings(data: Dict[str, Any]) -> List[dict]:
    """Check Raster-specific warnings."""
    warnings = []

    # Check prescription items for missing name fields
    _, meds = _find_prescription_items(data)
    unnamed_count = 0
    for med in meds:
        name = _get_item_name(med, _MEDICINE_NAME_FIELDS)
        if not name:
            unnamed_count += 1

    if unnamed_count:
        warnings.append({
            "category": "ehr_medicines",
            "severity": "warning",
            "message": f"{unnamed_count} medicine(s) missing name field — drug lookup will fail in Raster"
        })

    # Check key segments
    missing_segments = []
    for seg in ['chiefComplaints', 'diagnosis', 'vitals']:
        if not data.get(seg):
            missing_segments.append(seg)

    if missing_segments:
        warnings.append({
            "category": "ehr_segments",
            "severity": "info",
            "message": f"Missing segments for Raster: {', '.join(missing_segments)}"
        })

    return warnings


def _check_feedback_compatibility(
    original: Dict[str, Any],
    edited: Dict[str, Any],
) -> List[dict]:
    """Check if prescription key changed between original and edited (affects feedback comparison)."""
    warnings = []

    orig_key, orig_items = _find_prescription_items(original) if isinstance(original, dict) else (None, [])
    edit_key, edit_items = _find_prescription_items(edited) if isinstance(edited, dict) else (None, [])

    # Key name changed
    if orig_key and edit_key and orig_key != edit_key:
        warnings.append({
            "category": "feedback_compatibility",
            "severity": "warning",
            "message": f"Prescription field name changed from '{orig_key}' to '{edit_key}' — medicine feedback comparison may be affected"
        })

    # Prescription removed entirely
    if orig_items and not edit_items:
        warnings.append({
            "category": "feedback_compatibility",
            "severity": "warning",
            "message": "All medicines were removed in edit — medicine feedback will have no edited data to compare"
        })

    # Prescription added (wasn't in original)
    if not orig_items and edit_items:
        warnings.append({
            "category": "feedback_compatibility",
            "severity": "info",
            "message": f"{len(edit_items)} medicine(s) added in edit that weren't in original AI extraction — these won't generate feedback corrections"
        })

    return warnings

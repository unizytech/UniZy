"""
Raster Investigation Package Lookup Tables

This file contains the investigation package name to investigationId mappings from Raster DB.
Used to convert extracted investigation names to their Raster database IDs.

Used by: NEO_OP, NEO_DAILY, NEO_PROFORMA, NEO_DISCHARGE, NEO_ADMISSION templates
"""

from typing import Dict, Optional, List, Tuple


# ============================================================================
# INVESTIGATION PACKAGES FROM RASTER DATABASE
# Format: {id: package_name}
# ============================================================================

INVESTIGATION_DATABASE: Dict[int, str] = {
    1: "NICU Admission Investigation",
    2: "NICU Surgical Investigation",
    4: "Test Investigation",
    5: "S. Bilirubin direct and indirect",
    6: "Varun_Fever package",
    7: "Varun_ICU/Sepsis + Metabolic",
    8: "Bleeding",
    9: "Imaging",
    10: "ROUTINE INVESTIGATION",
    11: "Loose stools investigation",
    12: "Dengue investigations",
}


# ============================================================================
# BUILD LOOKUP INDEX FOR FAST SEARCHING
# ============================================================================

def _normalize_investigation_name(name: str) -> str:
    """Normalize investigation name for matching."""
    if not name:
        return ""
    return name.lower().strip()


def _build_investigation_index() -> Dict[str, int]:
    """Build a normalized lookup index from investigation names to IDs."""
    index = {}
    for inv_id, package_name in INVESTIGATION_DATABASE.items():
        normalized = _normalize_investigation_name(package_name)
        if normalized:
            index[normalized] = inv_id
    return index


# Build the index at module load time
INVESTIGATION_NAME_INDEX = _build_investigation_index()


# ============================================================================
# INVESTIGATION ALIASES AND KEYWORDS
# Maps common terms/keywords to investigation package IDs
# ============================================================================

INVESTIGATION_KEYWORDS: Dict[str, int] = {
    # NICU Admission (ID: 1)
    "nicu admission": 1,
    "admission investigation": 1,
    "admission workup": 1,
    "admission labs": 1,

    # NICU Surgical (ID: 2)
    "nicu surgical": 2,
    "surgical investigation": 2,
    "pre-op": 2,
    "preop": 2,
    "pre operative": 2,
    "surgical workup": 2,

    # Test Investigation (ID: 4)
    "test investigation": 4,
    "test": 4,

    # Bilirubin (ID: 5)
    "bilirubin": 5,
    "s. bilirubin": 5,
    "serum bilirubin": 5,
    "bilirubin direct": 5,
    "bilirubin indirect": 5,
    "direct bilirubin": 5,
    "indirect bilirubin": 5,
    "total bilirubin": 5,
    "jaundice workup": 5,
    "jaundice": 5,

    # Fever package (ID: 6)
    "fever": 6,
    "fever package": 6,
    "fever workup": 6,
    "pyrexia": 6,

    # ICU/Sepsis + Metabolic (ID: 7)
    "icu": 7,
    "sepsis": 7,
    "metabolic": 7,
    "sepsis workup": 7,
    "septic workup": 7,
    "sepsis screen": 7,
    "metabolic workup": 7,
    "icu workup": 7,

    # Bleeding (ID: 8)
    "bleeding": 8,
    "coagulation": 8,
    "coagulation profile": 8,
    "bleeding workup": 8,
    "clotting": 8,
    "pt inr": 8,
    "aptt": 8,

    # Imaging (ID: 9)
    "imaging": 9,
    "radiology": 9,
    "x-ray": 9,
    "xray": 9,
    "ultrasound": 9,
    "usg": 9,
    "ct scan": 9,
    "mri": 9,
    "scan": 9,

    # Routine Investigation (ID: 10)
    "routine investigation": 10,
    "routine": 10,
    "routine labs": 10,
    "routine workup": 10,
    "routine blood work": 10,

    # Loose stools investigation (ID: 11)
    "loose stools investigation": 11,
    "loose stools": 11,
    "diarrhea": 11,
    "diarrhoea": 11,
    "stool investigation": 11,
    "stool workup": 11,

    # Dengue investigations (ID: 12)
    "dengue investigations": 12,
    "dengue": 12,
    "dengue workup": 12,
    "dengue panel": 12,
    "dengue test": 12,
    "ns1": 12,
}


# ============================================================================
# PUBLIC LOOKUP FUNCTIONS
# ============================================================================

def lookup_investigation_id(investigation_name: str) -> Optional[int]:
    """
    Look up the Raster investigationId for a given investigation name.

    Args:
        investigation_name: Investigation package name extracted from audio

    Returns:
        The Raster investigationId if found, None otherwise
    """
    if not investigation_name:
        return None

    normalized = _normalize_investigation_name(investigation_name)

    # Direct match in database
    if normalized in INVESTIGATION_NAME_INDEX:
        return INVESTIGATION_NAME_INDEX[normalized]

    # Check keyword matches
    for keyword, inv_id in INVESTIGATION_KEYWORDS.items():
        if keyword in normalized or normalized in keyword:
            return inv_id

    # Partial match in database names
    for indexed_name, inv_id in INVESTIGATION_NAME_INDEX.items():
        if normalized in indexed_name or indexed_name in normalized:
            return inv_id

    return None


def lookup_investigation_id_with_fallback(investigation_name: str, fallback_id: int = 1) -> int:
    """
    Look up the Raster investigationId with a fallback value.

    Args:
        investigation_name: Investigation package name extracted from audio
        fallback_id: ID to return if no match found (default: 1 for NICU Admission)

    Returns:
        The Raster investigationId if found, otherwise the fallback_id
    """
    result = lookup_investigation_id(investigation_name)
    return result if result is not None else fallback_id


def get_investigation_name(investigation_id: int) -> Optional[str]:
    """
    Get investigation package name by ID.

    Args:
        investigation_id: The Raster investigationId

    Returns:
        The package name or None if not found
    """
    return INVESTIGATION_DATABASE.get(investigation_id)


def get_all_investigations() -> List[Tuple[int, str]]:
    """
    Get all investigation packages.

    Returns:
        List of (investigation_id, package_name) tuples
    """
    return [(inv_id, name) for inv_id, name in INVESTIGATION_DATABASE.items()]


def search_investigations(query: str) -> List[Tuple[int, str]]:
    """
    Search for investigations matching a query.

    Args:
        query: Search query (partial name match)

    Returns:
        List of (investigation_id, package_name) tuples
    """
    if not query:
        return list(INVESTIGATION_DATABASE.items())

    query_lower = query.lower()
    results = []

    for inv_id, package_name in INVESTIGATION_DATABASE.items():
        if query_lower in package_name.lower():
            results.append((inv_id, package_name))

    return results

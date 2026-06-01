"""
Raster Counsellor (seenBy) Lookup Tables

Maps counsellor names to their Raster database IDs for the seenBy field.
Used by: NEO_OP, NEO_DAILY, NEO_DAILY_FREE, NEO_ADMISSION templates.

Reference: references/Neopaed - One Hat integration values reference sheet.md
"""

import logging
from typing import Dict, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Default counsellor ID when no match is found
DEFAULT_SEEN_BY_ID = 7  # Dr S Ramakrishnan


# ============================================================================
# COUNSELLOR DATABASE FROM RASTER
# Format: {id: display_name}
# ============================================================================

DOCTOR_DATABASE: Dict[int, str] = {
    7: "Dr S Ramakrishnan",
    8: "Dr D.V. Suresh",
    11: "Dr Kuralvanan",
    13: "Dr R Swaminathan",
    14: "Not Applicable",
    18: "Dr Ravichandran",
    21: "Dr D. Maheshwari",
    22: "Dr Reshma Raj",
    25: "Dr Lathika Saran",
    26: "Dr Pradeepa",
    27: "Dr Nirranjana N S",
    28: "Dr Thangavel M",
    29: "Dr Myilvahanan",
    30: "Dr Sathish Kumar M",
    32: "Dr Saminathan R",
    33: "Dr S. Deepika",
    34: "Dr Deepak",
    35: "Dr Ravichandran M.S",
    36: "Dr Suresh Kumar A",
    37: "Dr Varun S",
    38: "Dr Hemnath K A",
    39: "Dr Jesna I",
    40: "Dr Priyanka V",
    41: "Dr Sanjana",
    43: "Dr D. V. Suresh",
    46: "Dr Ravichandran",
    47: "Dr Ravichandran (Pediatric Surgery)",
    48: "J. Nivetha",
    50: "Dr Pavithra",
    51: "Dr Kabil Raj",
    52: "Dr R. Shinika",
    54: "Dr R.V. Selva Bharathi",
    55: "Dr A. Suresh Kumar (Neurosurgery)",
    56: "Dr T. V. Rajagopal",
    57: "Dr Sabarirajan",
    58: "Dr Sabari Rajan",
    60: "Dr A Suresh Kumar (Neurosurgeon)",
    61: "Dr V. Senthil Kumar (Neuro)",
    62: "Dr Senthil Kumaran (Plastic Surgery)",
    63: "Dr Senthil Raja",
    64: "Dr M. Senthil Raja (Endocrinologist)",
    65: "Dr S. Kiruthika (Clinical Genetics)",
    66: "Dr M. Thangavel (Uro)",
    67: "Dr Puviarasan G (Gastroenterology)",
    69: "Dr M. Preethi (Dermatologist)",
    70: "Dr Karthika V (Haematologist)",
    71: "Dr M. Thangavel (Urology)",
    72: "Dr Saranya (Paediatrics)",
    73: "Dr Senthil Kumaran (Plastic Surgery)",
    75: "Dr Thangavel (Urologist)",
    76: "Dr R. Swaminathan (Paed Surgery)",
    77: "Dr Swaminathan (Paed Surgery)",
    78: "Dr Aarthi Chandrasekaran (Nephro)",
    80: "Dr P. Vani",
    81: "M. Parimala",
    82: "Dr P. Kannan (Cardio)",
    83: "Dr Gunaseelan G (Pulmonary)",
    84: "Dr P Sabarirajan (ENT)",
    85: "Dr Thirumalaivasan (Pediatric Intensivist)",
    86: "Dr R. Saminathan (Paed Surgeon)",
    87: "Dr G Puviarasan (Gastro)",
    88: "Soundarya G (OT)",
    89: "Dr Aarthi Chandrasekaran (Nephro)",
    90: "Dr Logesh T",
    91: "Dr V J Preethi",
    92: "Dr Shylaja S S",
    93: "Dr M Thirumalai Vasan (Pediatric Intensivist)",
}


# ============================================================================
# KEYWORD / ALIAS MAP — common name variants to counsellor IDs
# ============================================================================

DOCTOR_ALIASES: Dict[str, int] = {
    # Dr S Ramakrishnan (ID: 7) — primary neonatologist
    "ramakrishnan": 7,
    "rama": 7,
    "ramki": 7,
    "dr rama": 7,
    "dr ramakrishnan": 7,
    "sr": 7,

    # Dr D.V. Suresh (ID: 8)
    "suresh": 8,
    "dv suresh": 8,
    "dr suresh": 8,
    "d.v. suresh": 8,

    # Dr Kuralvanan (ID: 11)
    "kuralvanan": 11,
    "kural": 11,

    # Dr R Swaminathan (ID: 13) — general
    "swaminathan": 13,
    "swami": 13,

    # Dr Ravichandran (ID: 18)
    "ravichandran": 18,
    "ravi": 18,

    # Dr Maheshwari (ID: 21)
    "maheshwari": 21,

    # Dr Reshma Raj (ID: 22)
    "reshma": 22,
    "reshma raj": 22,

    # Dr Lathika Saran (ID: 25)
    "lathika": 25,
    "lathika saran": 25,

    # Dr Pradeepa (ID: 26)
    "pradeepa": 26,

    # Dr Nirranjana (ID: 27)
    "nirranjana": 27,
    "niranjana": 27,

    # Dr Thangavel M (ID: 28)
    "thangavel": 28,

    # Dr Myilvahanan (ID: 29)
    "myilvahanan": 29,

    # Dr Sathish Kumar M (ID: 30)
    "sathish": 30,
    "sathish kumar": 30,

    # Dr Saminathan R (ID: 32)
    "saminathan": 32,

    # Dr Deepika (ID: 33)
    "deepika": 33,

    # Dr Deepak (ID: 34)
    "deepak": 34,

    # Dr Varun S (ID: 37)
    "varun": 37,
    "dr varun": 37,

    # Dr Hemnath (ID: 38)
    "hemnath": 38,

    # Dr Jesna (ID: 39)
    "jesna": 39,

    # Dr Priyanka (ID: 40)
    "priyanka": 40,

    # Dr Sanjana (ID: 41)
    "sanjana": 41,

    # Dr Pavithra (ID: 50)
    "pavithra": 50,

    # Dr Kabil Raj (ID: 51)
    "kabil": 51,
    "kabil raj": 51,

    # Dr Shinika (ID: 52)
    "shinika": 52,

    # Dr Selva Bharathi (ID: 54)
    "selva bharathi": 54,
    "selva": 54,

    # Dr Sabarirajan (ID: 57)
    "sabarirajan": 57,
    "sabari": 57,

    # Dr Senthil Kumar (neuro) (ID: 61)
    "senthil kumar": 61,

    # Dr Senthil Kumaran (plastic) (ID: 62)
    "senthil kumaran": 62,

    # Dr Senthil Raja (ID: 63)
    "senthil raja": 63,

    # Dr Kiruthika (ID: 65)
    "kiruthika": 65,

    # Dr Puviarasan (ID: 67)
    "puviarasan": 67,

    # Dr Preethi (derma) (ID: 69)
    "preethi": 69,

    # Dr Karthika (haematologist) (ID: 70)
    "karthika": 70,

    # Dr Saranya (paediatrics) (ID: 72)
    "saranya": 72,

    # Dr Kannan (cardio) (ID: 82)
    "kannan": 82,

    # Dr Gunaseelan (pulmonary) (ID: 83)
    "gunaseelan": 83,

    # Dr Thirumalaivasan (ID: 85)
    "thirumalaivasan": 85,
    "thirumalai": 85,

    # Dr Logesh (ID: 90)
    "logesh": 90,

    # Dr Shylaja (ID: 92)
    "shylaja": 92,

    # Nivetha (ID: 48) — psychologist
    "nivetha": 48,

    # Dr Vani (ID: 80)
    "vani": 80,

    # Parimala (ID: 81)
    "parimala": 81,

    # Dr Aarthi (nephro) (ID: 78)
    "aarthi": 78,
    "aarthi chandrasekaran": 78,
}


# ============================================================================
# BUILD LOOKUP INDEX
# ============================================================================

def _normalize_counsellor_name(name: str) -> str:
    """Normalize counsellor name for matching."""
    if not name:
        return ""
    normalized = name.lower().strip()
    # Strip common prefixes
    for prefix in ["dr.", "dr ", "counsellor ", "dr. "]:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
    return normalized


def _build_counsellor_index() -> Dict[str, int]:
    """Build a normalized lookup index from counsellor display names to IDs."""
    index = {}
    for doc_id, display_name in DOCTOR_DATABASE.items():
        normalized = _normalize_counsellor_name(display_name)
        if normalized and normalized not in index:
            index[normalized] = doc_id
    return index


# Build at module load time
DOCTOR_NAME_INDEX = _build_counsellor_index()


# ============================================================================
# PUBLIC LOOKUP FUNCTIONS
# ============================================================================

def lookup_counsellor_id(name: str) -> Optional[int]:
    """
    Look up a Raster counsellor ID from a name string.

    Matching order:
    1. Exact normalized match against database names
    2. Alias/keyword match
    3. Fuzzy match at 85% threshold

    Args:
        name: Counsellor name extracted from audio

    Returns:
        Raster counsellor ID if found, None otherwise
    """
    if not name:
        return None

    normalized = _normalize_counsellor_name(name)
    if not normalized:
        return None

    # 1. Exact match in database index
    if normalized in DOCTOR_NAME_INDEX:
        return DOCTOR_NAME_INDEX[normalized]

    # 2. Alias match
    if normalized in DOCTOR_ALIASES:
        return DOCTOR_ALIASES[normalized]

    # 3. Fuzzy match against database names + aliases
    best_id = None
    best_score = 0.0

    for indexed_name, doc_id in DOCTOR_NAME_INDEX.items():
        score = SequenceMatcher(None, normalized, indexed_name).ratio()
        if score > best_score:
            best_score = score
            best_id = doc_id

    for alias, doc_id in DOCTOR_ALIASES.items():
        score = SequenceMatcher(None, normalized, alias).ratio()
        if score > best_score:
            best_score = score
            best_id = doc_id

    if best_id is not None and best_score >= 0.85:
        logger.info(f"[DOCTOR_LOOKUP] Fuzzy match: '{name}' -> ID {best_id} (score: {best_score:.1%})")
        return best_id

    logger.info(f"[DOCTOR_LOOKUP] No match for '{name}' (best score: {best_score:.1%})")
    return None


def resolve_seen_by_ids(seen_by_values: list) -> list:
    """
    Resolve a list of seenBy values (may be IDs or names) to integer IDs.

    - Numeric values pass through as-is
    - String names are looked up in the counsellor database
    - Unresolved strings are dropped

    Args:
        seen_by_values: List of counsellor IDs (int) or names (str)

    Returns:
        List of resolved integer counsellor IDs
    """
    if not isinstance(seen_by_values, list):
        return [DEFAULT_SEEN_BY_ID]

    resolved = []
    for val in seen_by_values:
        if isinstance(val, int):
            resolved.append(val)
        elif isinstance(val, str):
            val_stripped = val.strip()
            if val_stripped.isdigit():
                resolved.append(int(val_stripped))
            elif val_stripped:
                doc_id = lookup_counsellor_id(val_stripped)
                if doc_id is not None:
                    resolved.append(doc_id)
                else:
                    logger.warning(f"[DOCTOR_LOOKUP] Could not resolve seenBy name: '{val_stripped}'")

    return resolved if resolved else [DEFAULT_SEEN_BY_ID]


def resolve_seen_by_single(value) -> int:
    """
    Resolve a single seenBy value (ID or name) to an integer ID.

    Used by NEO_OP where seenBy is a single value, not an array.

    Args:
        value: Counsellor ID (int), name (str), or None

    Returns:
        Resolved integer counsellor ID, or DEFAULT_SEEN_BY_ID if unresolved
    """
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        val_stripped = value.strip()
        if val_stripped.isdigit() and int(val_stripped) > 0:
            return int(val_stripped)
        if val_stripped:
            doc_id = lookup_counsellor_id(val_stripped)
            if doc_id is not None:
                return doc_id
    return DEFAULT_SEEN_BY_ID

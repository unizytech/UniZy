"""
Investigation Service - Counsellor Investigation List Management and Matching

This module handles:
- CSV parsing and investigation list upload
- Investigation normalization and tokenization
- 7-level matching algorithm with feedback learning
- Post-processing for investigation extraction
- Adaptive learning via segment definition updates

Matching Priority (7 levels):
1. Counsellor's previous feedback (agreed/disagreed) → 95% confidence
2. Counsellor's personal list - exact match → 100% confidence
3. Counsellor's personal list - common name match → 98% confidence
4. School list - exact match → 90% confidence
5. School list - common name match → 88% confidence
6. Counsellor's personal list - fuzzy match → 85-95% confidence
7. School list - fuzzy match → 81-90% confidence
"""

import uuid
import re
import csv
import io
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from .supabase_service import supabase

# Try to import rapidfuzz, fallback to basic matching if not available
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logging.warning("rapidfuzz not available - using basic string matching")

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# INVESTIGATION LIST DATA CACHE (with TTL and invalidation)
# ============================================================================
# Caches actual investigation list data to avoid repeated DB queries
# Separate from extraction_service's _list_availability_cache (which only caches existence check)

_doctor_investigations_cache: Dict[str, Dict[str, Any]] = {}
_hospital_investigations_cache: Dict[str, Dict[str, Any]] = {}
_INVESTIGATION_CACHE_TTL_SECONDS = 31536000  # 1 year (effectively infinite - invalidated on list updates, cleared on server restart)


def _get_counsellor_inv_cache_key(counsellor_id: uuid.UUID, inv_type: Optional[str] = None, category: Optional[str] = None) -> str:
    """Generate cache key for counsellor investigation list."""
    return f"doc_inv_{counsellor_id}_{inv_type or 'all'}_{category or 'all'}"


def _get_school_inv_cache_key(school_id: uuid.UUID, inv_type: Optional[str] = None, category: Optional[str] = None) -> str:
    """Generate cache key for school investigation list."""
    return f"hosp_inv_{school_id}_{inv_type or 'all'}_{category or 'all'}"


def get_cached_counsellor_investigations(counsellor_id: uuid.UUID, inv_type: Optional[str] = None, category: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """Get cached counsellor investigation list if not expired."""
    cache_key = _get_counsellor_inv_cache_key(counsellor_id, inv_type, category)
    if cache_key in _doctor_investigations_cache:
        entry = _doctor_investigations_cache[cache_key]
        if datetime.now() < entry["expires_at"]:
            logger.info(f"[TIMING_INVESTIGATION_LIST] ♻️ Cache HIT for counsellor {str(counsellor_id)[:8]}... ({len(entry['data'])} investigations)")
            return entry["data"]
        else:
            del _doctor_investigations_cache[cache_key]
    return None


def get_cached_school_investigations(school_id: uuid.UUID, inv_type: Optional[str] = None, category: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """Get cached school investigation list if not expired."""
    cache_key = _get_school_inv_cache_key(school_id, inv_type, category)
    if cache_key in _hospital_investigations_cache:
        entry = _hospital_investigations_cache[cache_key]
        if datetime.now() < entry["expires_at"]:
            logger.info(f"[TIMING_INVESTIGATION_LIST] ♻️ Cache HIT for school {str(school_id)[:8]}... ({len(entry['data'])} investigations)")
            return entry["data"]
        else:
            del _hospital_investigations_cache[cache_key]
    return None


def set_cached_counsellor_investigations(counsellor_id: uuid.UUID, data: List[Dict[str, Any]], inv_type: Optional[str] = None, category: Optional[str] = None) -> None:
    """Cache counsellor investigation list with TTL."""
    cache_key = _get_counsellor_inv_cache_key(counsellor_id, inv_type, category)
    _doctor_investigations_cache[cache_key] = {
        "data": data,
        "expires_at": datetime.now() + timedelta(seconds=_INVESTIGATION_CACHE_TTL_SECONDS),
        "cached_at": datetime.now()
    }
    logger.debug(f"[INVESTIGATION_CACHE] 💾 Cached {len(data)} investigations for counsellor {str(counsellor_id)[:8]}... (TTL: ∞, invalidated on update)")


def set_cached_school_investigations(school_id: uuid.UUID, data: List[Dict[str, Any]], inv_type: Optional[str] = None, category: Optional[str] = None) -> None:
    """Cache school investigation list with TTL."""
    cache_key = _get_school_inv_cache_key(school_id, inv_type, category)
    _hospital_investigations_cache[cache_key] = {
        "data": data,
        "expires_at": datetime.now() + timedelta(seconds=_INVESTIGATION_CACHE_TTL_SECONDS),
        "cached_at": datetime.now()
    }
    logger.debug(f"[INVESTIGATION_CACHE] 💾 Cached {len(data)} investigations for school {str(school_id)[:8]}... (TTL: ∞, invalidated on update)")


def invalidate_counsellor_investigation_cache(counsellor_id: uuid.UUID) -> int:
    """Invalidate cache for a specific counsellor. Call this when investigations are updated."""
    count = 0
    keys_to_delete = [k for k in _doctor_investigations_cache if str(counsellor_id) in k]
    for key in keys_to_delete:
        del _doctor_investigations_cache[key]
        count += 1
    if count > 0:
        logger.debug(f"[INVESTIGATION_CACHE] 🗑️ Invalidated {count} cache entries for counsellor {str(counsellor_id)[:8]}...")
    return count


def invalidate_school_investigation_cache(school_id: uuid.UUID) -> int:
    """Invalidate cache for a specific school. Call this when investigations are updated."""
    count = 0
    keys_to_delete = [k for k in _hospital_investigations_cache if str(school_id) in k]
    for key in keys_to_delete:
        del _hospital_investigations_cache[key]
        count += 1
    if count > 0:
        logger.debug(f"[INVESTIGATION_CACHE] 🗑️ Invalidated {count} cache entries for school {str(school_id)[:8]}...")
    return count


def invalidate_all_counsellor_investigation_caches() -> int:
    """Invalidate ALL counsellor investigation caches. Used for global cache refresh."""
    count = len(_doctor_investigations_cache)
    _doctor_investigations_cache.clear()
    if count:
        logger.debug(f"[INVESTIGATION_CACHE] 🗑️ Invalidated ALL counsellor investigation caches ({count} entries)")
    return count


def invalidate_all_school_investigation_caches() -> int:
    """Invalidate ALL school investigation caches. Used for global cache refresh."""
    count = len(_hospital_investigations_cache)
    _hospital_investigations_cache.clear()
    if count:
        logger.debug(f"[INVESTIGATION_CACHE] 🗑️ Invalidated ALL school investigation caches ({count} entries)")
    return count


# ============================================================================
# Configuration
# ============================================================================

ADAPTIVE_LEARNING_THRESHOLD = 0.85  # Threshold for auto-updating segment definitions
MIN_FUZZY_THRESHOLD = 0.75  # Threshold for fuzzy matching - catches transcription errors
PREFIX_MATCH_COVERAGE = 0.60  # Minimum coverage for prefix/substring matching (60% of full name)

# Investigation prefixes to remove during normalization
INVESTIGATION_PREFIXES = [
    "X-RAY ", "XRAY ", "X RAY ",
    "CT ", "CT-", "CECT ",
    "MRI ", "MR ",
    "USG ", "U/S ", "ULTRASOUND ",
    "ECHO ", "2D ECHO ",
    "ECG ", "EKG ",
    "TEST ", "TESTS ",
]

# Investigation type keywords for auto-classification
INVESTIGATION_TYPE_KEYWORDS = {
    "laboratory": [
        "blood", "urine", "serum", "plasma", "culture", "biopsy", "count",
        "level", "test", "panel", "profile", "cbc", "lft", "kft", "rft",
        "hba1c", "lipid", "thyroid", "liver", "kidney", "hemoglobin",
        "creatinine", "glucose", "electrolyte", "coagulation"
    ],
    "imaging": [
        "x-ray", "xray", "ct", "mri", "ultrasound", "usg", "scan", "echo",
        "doppler", "mammogram", "radiograph", "fluoroscopy", "pet",
        "angiography", "venography", "arthrography"
    ],
    "other": [
        "ecg", "ekg", "eeg", "emg", "spirometry", "endoscopy", "colonoscopy",
        "bronchoscopy", "cystoscopy", "biopsy", "pft", "audiometry",
        "visual field", "nerve conduction", "holter"
    ]
}

# Column mapping for alternate CSV formats (maps alternate column names to internal names)
# Keys are lowercase for case-insensitive matching
INVESTIGATION_COLUMN_MAP = {
    # Test Name -> name (primary investigation name)
    "test name": "name",
    "testname": "name",
    "test_name": "name",
    # Test Short Name -> common_names (as alias)
    "test short name": "common_names",
    "testshortname": "common_names",
    "test_short_name": "common_names",
    "test_shortname": "common_names",  # Aosta format: test_ShortName
    # Test Type -> type (lowercase conversion applied)
    "test type": "type",
    "testtype": "type",
    "test_type": "type",
    # TestID -> external_id
    "testid": "external_id",
    "test_id": "external_id",
    "test id": "external_id",
}


# ============================================================================
# Investigation Alias Extraction
# ============================================================================
# Common abbreviations for investigation names - used to auto-generate common_names
# for better Gemini recognition

INVESTIGATION_ABBREVIATIONS = {
    # Blood tests
    "complete blood count": ["CBC", "HEMOGRAM", "FBC"],
    "hemoglobin": ["HB", "HGB"],
    "white blood cell count": ["WBC", "TLC"],
    "platelet count": ["PLT", "PLATELET"],
    "erythrocyte sedimentation rate": ["ESR"],
    "c-reactive protein": ["CRP"],
    "prothrombin time": ["PT", "INR"],
    "activated partial thromboplastin time": ["APTT", "PTT"],
    "peripheral blood smear": ["PBS", "BLOOD SMEAR"],

    # Liver function
    "liver function test": ["LFT", "LIVER PANEL"],
    "alanine transaminase": ["ALT", "SGPT"],
    "aspartate transaminase": ["AST", "SGOT"],
    "alkaline phosphatase": ["ALP"],
    "gamma glutamyl transferase": ["GGT"],
    "bilirubin": ["TBIL", "BILI"],

    # Kidney function
    "kidney function test": ["KFT", "RFT", "RENAL PANEL"],
    "renal function test": ["RFT", "KFT"],
    "blood urea nitrogen": ["BUN"],
    "creatinine": ["CREAT", "CR"],
    "glomerular filtration rate": ["GFR", "EGFR"],
    "uric acid": ["UA"],

    # Diabetes / Metabolic
    "random blood sugar": ["RBS", "RANDOM GLUCOSE"],
    "fasting blood sugar": ["FBS", "FASTING GLUCOSE"],
    "postprandial blood sugar": ["PPBS", "PP GLUCOSE"],
    "glycated hemoglobin": ["HBA1C", "A1C"],
    "oral glucose tolerance test": ["OGTT", "GTT"],

    # Lipid profile
    "lipid profile": ["LIPID PANEL", "CHOLESTEROL PANEL"],
    "total cholesterol": ["TC", "CHOL"],
    "high density lipoprotein": ["HDL"],
    "low density lipoprotein": ["LDL"],
    "triglycerides": ["TG", "TRIG"],
    "very low density lipoprotein": ["VLDL"],

    # Thyroid
    "thyroid stimulating hormone": ["TSH"],
    "thyroid profile": ["TFT", "THYROID PANEL"],
    "triiodothyronine": ["T3"],
    "thyroxine": ["T4"],
    "free t3": ["FT3"],
    "free t4": ["FT4"],

    # Electrolytes
    "serum electrolytes": ["ELECTROLYTES", "LYTES"],
    "sodium": ["NA"],
    "potassium": ["K"],
    "chloride": ["CL"],
    "bicarbonate": ["HCO3", "CO2"],
    "calcium": ["CA"],
    "magnesium": ["MG"],
    "phosphorus": ["PHOS", "P"],

    # Urine
    "urine routine": ["URINE R/M", "URINALYSIS", "U/A"],
    "urine culture": ["U/C", "URINE C/S"],
    "urine protein creatinine ratio": ["UPCR", "PCR"],
    "urine albumin creatinine ratio": ["UACR", "ACR"],
    "24 hour urine protein": ["24H URINE PROTEIN"],

    # Cardiac
    "electrocardiogram": ["ECG", "EKG"],
    "echocardiogram": ["ECHO", "2D ECHO"],
    "troponin": ["TROP", "TROPONIN I", "TROPONIN T"],
    "brain natriuretic peptide": ["BNP", "NT-PROBNP"],
    "creatine kinase": ["CK", "CPK"],
    "creatine kinase mb": ["CK-MB", "CKMB"],

    # Imaging
    "x-ray chest": ["CXR", "CHEST XRAY", "CHEST X-RAY"],
    "x-ray abdomen": ["AXR", "KUB"],
    "computed tomography": ["CT", "CAT SCAN"],
    "magnetic resonance imaging": ["MRI", "MR"],
    "ultrasonography": ["USG", "U/S", "ULTRASOUND"],
    "ultrasound abdomen": ["USG ABDOMEN", "ABD USG"],
    "mammography": ["MAMMO"],
    "positron emission tomography": ["PET", "PET-CT"],

    # Other
    "arterial blood gas": ["ABG"],
    "pulmonary function test": ["PFT", "SPIROMETRY"],
    "electroencephalogram": ["EEG"],
    "electromyography": ["EMG", "NCV"],
    "nerve conduction study": ["NCS", "NCV"],
    "upper gi endoscopy": ["OGD", "EGD", "UGIE"],
    "colonoscopy": ["COLONOSCOPY"],
    "stool routine": ["STOOL R/M"],
    "stool culture": ["STOOL C/S"],
    "sputum culture": ["SPUTUM C/S"],
    "blood culture": ["BLOOD C/S", "B/C"],
    "cerebrospinal fluid analysis": ["CSF ANALYSIS", "LP"],
}

# Noise patterns to remove from complex investigation names
INVESTIGATION_NOISE_PATTERNS = [
    r'\s+TEST\s*$',           # trailing " TEST"
    r'\s+TESTS\s*$',          # trailing " TESTS"
    r'\s+LEVEL\s*$',          # trailing " LEVEL"
    r'\s+LEVELS\s*$',         # trailing " LEVELS"
    r'\s+SERUM\s*$',          # trailing " SERUM"
    r'\s+BLOOD\s*$',          # trailing " BLOOD"
    r'\s+ESTIMATION\s*$',     # trailing " ESTIMATION"
    r'\s+DETERMINATION\s*$',  # trailing " DETERMINATION"
    r'\s+QUANTITATIVE\s*$',   # trailing " QUANTITATIVE"
    r'\s+QUALITATIVE\s*$',    # trailing " QUALITATIVE"
    r'\s*\(AUTOMATED\)\s*$',  # trailing "(AUTOMATED)"
    r'\s*\(AUTO\)\s*$',       # trailing "(AUTO)"
]


def extract_investigation_aliases(investigation_name: str, existing_common_names: Optional[List[str]] = None) -> List[str]:
    """
    Extract short recognizable aliases from investigation names.

    This helps Gemini recognize investigations when the school list has verbose names like:
    "Complete Blood Count (Automated)" -> aliases: ["CBC", "HEMOGRAM", "FBC"]

    Args:
        investigation_name: The full investigation name
        existing_common_names: Existing common names to avoid duplicates

    Returns:
        List of unique aliases not already in existing_common_names

    Examples:
        >>> extract_investigation_aliases("Complete Blood Count")
        ['CBC', 'HEMOGRAM', 'FBC']
        >>> extract_investigation_aliases("X-Ray Chest PA View")
        ['CXR', 'CHEST XRAY', 'CHEST X-RAY']
        >>> extract_investigation_aliases("Liver Function Test (Automated)")
        ['LFT', 'LIVER PANEL']
    """
    if not investigation_name:
        return []

    existing_set = set()
    if existing_common_names:
        existing_set = {cn.lower().strip() for cn in existing_common_names if cn}

    # Also add the original name to avoid returning it as an alias
    existing_set.add(investigation_name.lower().strip())

    aliases = []

    # Clean the investigation name
    cleaned = investigation_name.upper().strip()

    # Remove noise patterns
    for pattern in INVESTIGATION_NOISE_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned_lower = cleaned.lower()

    # Check for known abbreviations
    for full_name, abbrevs in INVESTIGATION_ABBREVIATIONS.items():
        # Check if this investigation matches a known pattern
        # Use word-boundary-like matching to avoid partial matches
        if full_name in cleaned_lower or cleaned_lower in full_name:
            # Found a match - add all abbreviations
            for abbrev in abbrevs:
                if abbrev.lower() not in existing_set:
                    aliases.append(abbrev)
                    existing_set.add(abbrev.lower())
            break  # Only match one investigation type
        else:
            # Also check if all words from full_name are present
            full_name_words = set(full_name.split())
            cleaned_words = set(cleaned_lower.split())
            # If at least 60% of words match, consider it a match
            if len(full_name_words) >= 2:
                overlap = len(full_name_words & cleaned_words)
                if overlap >= len(full_name_words) * 0.6:
                    for abbrev in abbrevs:
                        if abbrev.lower() not in existing_set:
                            aliases.append(abbrev)
                            existing_set.add(abbrev.lower())
                    break

    # Also extract short form from the name if it has parenthetical abbreviation
    # e.g., "Complete Blood Count (CBC)" -> extract "CBC"
    paren_match = re.search(r'\(([A-Z0-9\-/]+)\)', investigation_name, re.IGNORECASE)
    if paren_match:
        abbrev = paren_match.group(1).upper()
        if abbrev.lower() not in existing_set and len(abbrev) <= 10:
            aliases.append(abbrev)
            existing_set.add(abbrev.lower())

    return aliases


# ============================================================================
# Normalization Functions
# ============================================================================

def normalize_investigation_name(name: str) -> str:
    """
    Normalize investigation name for matching.

    - Remove prefixes (X-RAY, CT, MRI, USG, etc.)
    - Lowercase
    - Collapse multiple spaces
    - Strip leading/trailing whitespace

    Args:
        name: Raw investigation name

    Returns:
        Normalized name
    """
    if not name:
        return ""

    result = name.strip().upper()

    # Remove known prefixes
    for prefix in INVESTIGATION_PREFIXES:
        if result.startswith(prefix):
            result = result[len(prefix):]
            break

    # Lowercase and clean up spaces
    result = result.lower().strip()
    result = re.sub(r'\s+', ' ', result)

    return result


def generate_search_tokens(investigation_name: str, common_names: Optional[List[str]] = None) -> List[str]:
    """
    Generate search tokens for GIN index search.

    Args:
        investigation_name: Primary investigation name
        common_names: List of alternative names

    Returns:
        List of search tokens
    """
    tokens = set()

    # Tokenize main name
    normalized = normalize_investigation_name(investigation_name)
    tokens.update(normalized.split())

    # Tokenize common names
    if common_names:
        for name in common_names:
            if name:
                tokens.update(normalize_investigation_name(name).split())

    # Remove very short tokens (less than 2 chars)
    tokens = {t for t in tokens if len(t) >= 2}

    return sorted(list(tokens))


def classify_investigation_type(name: str) -> str:
    """
    Auto-classify investigation type based on keywords.

    Args:
        name: Investigation name

    Returns:
        Investigation type: 'laboratory', 'imaging', or 'other'
    """
    name_lower = name.lower()

    # Check each type's keywords
    for inv_type, keywords in INVESTIGATION_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in name_lower:
                return inv_type

    # Default to 'other' if no match
    return "other"


# ============================================================================
# Shared Enrichment (used by both CSV and JSON upload paths)
# ============================================================================

def _enrich_investigation_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply all enrichment logic to a raw investigation dict (alias generation,
    type detection/mapping, normalization). Used by both CSV and JSON paths.

    Expected input keys: investigation_name (required), common_names (list),
    investigation_type, category, normal_range, loinc_code, cpt_code, external_id.
    """
    name = raw["investigation_name"]
    common_names = list(raw.get("common_names") or [])

    # Auto-generate aliases
    auto_aliases = extract_investigation_aliases(name, common_names)
    for alias in auto_aliases:
        if alias.lower() not in {cn.lower() for cn in common_names}:
            common_names.append(alias)

    # Get or auto-detect investigation type
    inv_type = (raw.get("investigation_type") or "").strip().lower()
    type_aliases = {
        'lab': 'laboratory',
        'labs': 'laboratory',
        'blood': 'laboratory',
        'radiology': 'imaging',
        'xray': 'imaging',
        'x-ray': 'imaging',
        'scan': 'imaging',
        'ct': 'imaging',
        'mri': 'imaging',
        'usg': 'imaging',
        'ultrasound': 'imaging',
    }
    inv_type = type_aliases.get(inv_type, inv_type)
    if inv_type not in ('laboratory', 'imaging', 'other'):
        inv_type = classify_investigation_type(name)

    return {
        "investigation_name": name,
        "common_names": common_names,
        "investigation_type": inv_type,
        "category": raw.get("category") or None,
        "normal_range": raw.get("normal_range") or None,
        "loinc_code": raw.get("loinc_code") or None,
        "cpt_code": raw.get("cpt_code") or None,
        "external_id": raw.get("external_id") or None,
        "normalized_name": normalize_investigation_name(name),
        "search_tokens": generate_search_tokens(name, common_names),
    }


# ============================================================================
# CSV Parsing
# ============================================================================

def parse_csv_investigation_list(csv_content: str) -> Tuple[List[Dict], List[Dict]]:
    """
    Parse CSV content into investigation records.

    Expected columns: name, common_names, type, category, normal_range, loinc_code, cpt_code, external_id
    Alternate columns supported: Test Name, Test Short Name, Test Type, TestID (auto-mapped)
    Minimum required: name (or Test Name)

    Args:
        csv_content: CSV string content

    Returns:
        Tuple of (valid_investigations, errors)
    """
    valid_investigations = []
    errors = []

    try:
        reader = csv.DictReader(io.StringIO(csv_content))

        # Normalize header names (lowercase, strip, remove BOM) and apply column mapping
        if reader.fieldnames:
            # Remove BOM (\ufeff) from field names - common in Excel CSVs
            original_fieldnames = [f.lower().strip().lstrip('\ufeff') for f in reader.fieldnames]
            # Apply column mapping: map alternate column names to internal names
            mapped_fieldnames = []
            for field in original_fieldnames:
                mapped_field = INVESTIGATION_COLUMN_MAP.get(field, field)
                mapped_fieldnames.append(mapped_field)
            reader.fieldnames = mapped_fieldnames

        # Read all rows first for pre-validation
        all_rows = list(enumerate(reader, start=2))

        # Pre-validation: reject entire upload if any row is missing external_id
        missing_ext_id_rows = []
        for row_num, row in all_rows:
            ext_id = row.get('external_id', '').strip()
            if not ext_id:
                missing_ext_id_rows.append(row_num)
        if missing_ext_id_rows:
            errors.append({
                "row": 0,
                "error": f"Upload rejected: rows {missing_ext_id_rows} are missing required 'external_id' field. All rows must have an external_id.",
                "data": None
            })
            return [], errors

        for row_num, row in all_rows:
            try:
                # Get required name field
                name = row.get('name', '').strip()
                if not name:
                    errors.append({
                        "row": row_num,
                        "error": "Missing required 'name' field",
                        "data": row
                    })
                    continue

                external_id = row.get('external_id', '').strip()

                # Parse common_names
                # Original format: comma-separated in 'common_name' or 'common_names' column
                # Alternate format: single value in 'common_names' column (mapped from 'Test Short Name')
                common_names_str = row.get('common_name', '') or row.get('common_names', '')
                common_names = []
                if common_names_str:
                    # If it contains commas, split; otherwise treat as single alias
                    if ',' in common_names_str:
                        common_names = [n.strip() for n in common_names_str.split(',') if n.strip()]
                    else:
                        # Single short name (from 'Test Short Name' mapping)
                        stripped = common_names_str.strip()
                        if stripped:
                            common_names = [stripped]

                # Build raw record and enrich via shared function
                raw = {
                    "investigation_name": name,
                    "common_names": common_names,
                    "investigation_type": row.get('type', '').strip().lower() or None,
                    "category": row.get('category', '').strip() or None,
                    "normal_range": row.get('normal_range', '').strip() or None,
                    "loinc_code": row.get('loinc_code', '').strip() or None,
                    "cpt_code": row.get('cpt_code', '').strip() or None,
                    "external_id": external_id,
                }

                valid_investigations.append(_enrich_investigation_record(raw))

            except Exception as e:
                errors.append({
                    "row": row_num,
                    "error": str(e),
                    "data": row
                })

    except Exception as e:
        errors.append({
            "row": 0,
            "error": f"CSV parsing error: {str(e)}",
            "data": None
        })

    return valid_investigations, errors


# ============================================================================
# Upload Functions (shared pipeline + thin wrappers)
# ============================================================================

def _upsert_investigation_records(
    counsellor_id: uuid.UUID,
    investigations: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    replace_existing: bool,
    upload_id: str,
) -> Dict[str, Any]:
    """
    Shared upload pipeline used by both CSV and JSON upload paths.
    Handles: replace_existing deactivation, dedup, batch upsert,
    upload record update, cache invalidation, result formatting.

    Args:
        counsellor_id: Counsellor ID
        investigations: List of enriched investigation dicts (already passed through _enrich_investigation_record)
        errors: List of errors from parsing phase (will be extended with upsert errors)
        replace_existing: If True, deactivate existing investigations first
        upload_id: Upload tracking record ID

    Returns:
        Upload result with statistics
    """
    try:
        # Deactivate existing if requested
        if replace_existing and investigations:
            supabase.table('counsellor_investigations').update({
                'is_active': False
            }).eq('counsellor_id', str(counsellor_id)).execute()

        # Prepare all investigations with counsellor_id and is_active
        for investigation in investigations:
            investigation['counsellor_id'] = str(counsellor_id)
            investigation['is_active'] = True

        # Deduplicate by normalized_name (last occurrence wins) —
        # PostgreSQL ON CONFLICT cannot handle duplicate conflict keys in a single batch
        pre_dedup_count = len(investigations)
        seen = {}
        for investigation in investigations:
            seen[investigation['normalized_name']] = investigation
        investigations = list(seen.values())
        if len(investigations) < pre_dedup_count:
            logger.info(f"[Investigation] Deduped {pre_dedup_count} -> {len(investigations)} investigations ({pre_dedup_count - len(investigations)} duplicates removed)")

        # Batch upsert
        successful = 0
        failed = len(errors)
        BATCH_SIZE = 500

        for i in range(0, len(investigations), BATCH_SIZE):
            batch = investigations[i:i + BATCH_SIZE]
            try:
                supabase.table('counsellor_investigations').upsert(
                    batch,
                    on_conflict='counsellor_id,normalized_name'
                ).execute()
                successful += len(batch)
            except Exception as e:
                # If batch fails, fall back to individual inserts for this batch
                logger.warning(f"[Investigation] Batch upsert failed, falling back to individual inserts: {e}")
                for investigation in batch:
                    try:
                        supabase.table('counsellor_investigations').upsert(
                            investigation,
                            on_conflict='counsellor_id,normalized_name'
                        ).execute()
                        successful += 1
                    except Exception as inner_e:
                        failed += 1
                        errors.append({
                            "row": "N/A",
                            "error": str(inner_e),
                            "data": investigation
                        })

        # Update upload record
        supabase.table('investigation_list_uploads').update({
            'status': 'completed',
            'row_count': len(investigations) + len(errors),
            'successful_imports': successful,
            'failed_imports': failed,
            'error_details': errors if errors else None,
            'processed_at': datetime.utcnow().isoformat()
        }).eq('id', upload_id).execute()

        logger.info(f"[Investigation] Uploaded {successful} investigations for counsellor {counsellor_id}")

        # Invalidate caches after successful upload
        from services.extraction_service import invalidate_list_cache
        invalidate_list_cache(counsellor_id)
        invalidate_counsellor_investigation_cache(counsellor_id)

        return {
            "upload_id": upload_id,
            "status": "completed",
            "total_rows": len(investigations) + len(errors),
            "successful": successful,
            "failed": failed,
            "errors": errors[:10] if errors else []
        }

    except Exception as e:
        if upload_id:
            supabase.table('investigation_list_uploads').update({
                'status': 'failed',
                'error_details': [{"error": str(e)}],
                'processed_at': datetime.utcnow().isoformat()
            }).eq('id', upload_id).execute()

        logger.error(f"[Investigation] Upload failed for counsellor {counsellor_id}: {e}")
        raise


def upload_investigation_list(
    counsellor_id: uuid.UUID,
    csv_content: str,
    filename: str,
    replace_existing: bool = False
) -> Dict[str, Any]:
    """Upload and process a CSV investigation list for a counsellor."""
    upload_record = supabase.table('investigation_list_uploads').insert({
        'counsellor_id': str(counsellor_id),
        'filename': filename,
        'file_size_bytes': len(csv_content.encode('utf-8')),
        'status': 'processing'
    }).execute()
    upload_id = upload_record.data[0]['id'] if upload_record.data else None

    investigations, errors = parse_csv_investigation_list(csv_content)
    return _upsert_investigation_records(counsellor_id, investigations, errors, replace_existing, upload_id)


def upload_investigation_list_json(
    counsellor_id: uuid.UUID,
    investigations: List[Dict[str, Any]],
    replace_existing: bool = False
) -> Dict[str, Any]:
    """Upload a JSON list of investigations for a counsellor."""
    upload_record = supabase.table('investigation_list_uploads').insert({
        'counsellor_id': str(counsellor_id),
        'filename': 'json_upload',
        'file_size_bytes': 0,
        'status': 'processing'
    }).execute()
    upload_id = upload_record.data[0]['id'] if upload_record.data else None

    enriched = []
    errors = []
    for idx, raw in enumerate(investigations):
        try:
            enriched.append(_enrich_investigation_record(raw))
        except Exception as e:
            errors.append({"row": idx + 1, "error": str(e), "data": raw})

    return _upsert_investigation_records(counsellor_id, enriched, errors, replace_existing, upload_id)


def upload_school_investigation_list(
    school_id: uuid.UUID,
    csv_content: str,
    filename: str,
    created_by: uuid.UUID,
    replace_existing: bool = False
) -> Dict[str, Any]:
    """
    Upload and process a CSV investigation list for a school.

    Args:
        school_id: School ID
        csv_content: CSV string content
        filename: Original filename
        created_by: Admin counsellor ID who uploaded
        replace_existing: If True, deactivate existing investigations first

    Returns:
        Upload result with statistics
    """
    # Create upload record
    upload_record = supabase.table('investigation_list_uploads').insert({
        'school_id': str(school_id),
        'filename': filename,
        'file_size_bytes': len(csv_content.encode('utf-8')),
        'status': 'processing'
    }).execute()

    upload_id = upload_record.data[0]['id'] if upload_record.data else None

    try:
        # Parse CSV
        investigations, errors = parse_csv_investigation_list(csv_content)

        # Deactivate existing if requested
        if replace_existing and investigations:
            supabase.table('school_investigation_lists').update({
                'is_active': False
            }).eq('school_id', str(school_id)).execute()

        # Insert investigations in batches (reduces N round-trips to N/500)
        successful = 0
        failed = len(errors)
        BATCH_SIZE = 500

        # Prepare all investigations with school_id, created_by, and is_active
        for investigation in investigations:
            investigation['school_id'] = str(school_id)
            investigation['created_by'] = str(created_by)
            investigation['is_active'] = True

        # Deduplicate by normalized_name (last occurrence wins) —
        # PostgreSQL ON CONFLICT cannot handle duplicate conflict keys in a single batch
        pre_dedup_count = len(investigations)
        seen = {}
        for investigation in investigations:
            seen[investigation['normalized_name']] = investigation
        investigations = list(seen.values())
        if len(investigations) < pre_dedup_count:
            logger.info(f"[Investigation] Deduped {pre_dedup_count} → {len(investigations)} school investigations ({pre_dedup_count - len(investigations)} duplicates removed)")

        # Batch upsert
        for i in range(0, len(investigations), BATCH_SIZE):
            batch = investigations[i:i + BATCH_SIZE]
            try:
                supabase.table('school_investigation_lists').upsert(
                    batch,
                    on_conflict='school_id,normalized_name'
                ).execute()
                successful += len(batch)
            except Exception as e:
                # If batch fails, fall back to individual inserts for this batch
                logger.warning(f"[Investigation] School batch upsert failed, falling back to individual inserts: {e}")
                for investigation in batch:
                    try:
                        supabase.table('school_investigation_lists').upsert(
                            investigation,
                            on_conflict='school_id,normalized_name'
                        ).execute()
                        successful += 1
                    except Exception as inner_e:
                        failed += 1
                        errors.append({
                            "row": "N/A",
                            "error": str(inner_e),
                            "data": investigation
                        })

        # Update upload record
        if upload_id:
            supabase.table('investigation_list_uploads').update({
                'status': 'completed',
                'row_count': len(investigations) + len(errors),
                'successful_imports': successful,
                'failed_imports': failed,
                'error_details': errors if errors else None,
                'processed_at': datetime.utcnow().isoformat()
            }).eq('id', upload_id).execute()

        logger.info(f"[Investigation] Uploaded {successful} school investigations for school {school_id}")

        # Invalidate caches after successful upload
        from services.extraction_service import invalidate_list_cache_by_school
        invalidate_list_cache_by_school(school_id)
        invalidate_school_investigation_cache(school_id)

        return {
            "upload_id": upload_id,
            "status": "completed",
            "total_rows": len(investigations) + len(errors),
            "successful": successful,
            "failed": failed,
            "errors": errors[:10] if errors else []
        }

    except Exception as e:
        # Update upload record with failure
        if upload_id:
            supabase.table('investigation_list_uploads').update({
                'status': 'failed',
                'error_details': [{"error": str(e)}],
                'processed_at': datetime.utcnow().isoformat()
            }).eq('id', upload_id).execute()

        logger.error(f"[Investigation] School upload failed: {e}")
        raise


# ============================================================================
# CRUD - Counsellor Investigations
# ============================================================================

def create_counsellor_investigation(
    counsellor_id: uuid.UUID,
    investigation_name: str,
    investigation_type: str,
    common_names: Optional[List[str]] = None,
    category: Optional[str] = None,
    normal_range: Optional[str] = None,
    loinc_code: Optional[str] = None,
    cpt_code: Optional[str] = None,
    external_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create a single investigation for a counsellor."""
    # Initialize common_names list
    if common_names is None:
        common_names = []
    else:
        common_names = list(common_names)  # Make a copy to avoid mutating the original

    # Auto-generate aliases from investigation name (augment existing common_names)
    auto_aliases = extract_investigation_aliases(investigation_name, common_names)
    for alias in auto_aliases:
        if alias.lower() not in {cn.lower() for cn in common_names}:
            common_names.append(alias)

    # Validate investigation_type
    if investigation_type not in ('laboratory', 'imaging', 'other'):
        investigation_type = classify_investigation_type(investigation_name)

    normalized = normalize_investigation_name(investigation_name)
    tokens = generate_search_tokens(investigation_name, common_names)

    # Enrich missing fields from school list
    enrichable_fields_missing = (
        not external_id or not category or not normal_range
        or not loinc_code or not cpt_code
    )
    if enrichable_fields_missing:
        try:
            from services.supabase_service import get_counsellor_school_id_cached
            school_id = get_counsellor_school_id_cached(counsellor_id)
            if school_id:
                school_match = supabase.table('school_investigation_lists')\
                    .select('external_id, investigation_type, category, normal_range, loinc_code, cpt_code, common_names')\
                    .eq('school_id', school_id)\
                    .eq('normalized_name', normalized)\
                    .eq('is_active', True)\
                    .limit(1)\
                    .execute()
                if school_match.data:
                    hi = school_match.data[0]
                    if not external_id:
                        external_id = hi.get('external_id')
                    if not category:
                        category = hi.get('category')
                    if not normal_range:
                        normal_range = hi.get('normal_range')
                    if not loinc_code:
                        loinc_code = hi.get('loinc_code')
                    if not cpt_code:
                        cpt_code = hi.get('cpt_code')
                    # Use school investigation_type if current is generic 'other'
                    if investigation_type == 'other' and hi.get('investigation_type'):
                        investigation_type = hi['investigation_type']
                    # Merge common_names (don't replace)
                    school_common = hi.get('common_names') or []
                    if school_common:
                        existing_lower = {n.lower() for n in common_names}
                        for name in school_common:
                            if name.lower() not in existing_lower:
                                common_names.append(name)
                    logger.debug(f"[Investigation] Enriched '{investigation_name}' from school list: external_id={external_id}")
        except Exception as e:
            logger.warning(f"[Investigation] School enrichment failed for '{investigation_name}': {e}")

    # Regenerate tokens after potential common_names enrichment
    tokens = generate_search_tokens(investigation_name, common_names)

    result = supabase.table('counsellor_investigations').insert({
        'counsellor_id': str(counsellor_id),
        'investigation_name': investigation_name,
        'investigation_type': investigation_type,
        'common_names': common_names,
        'category': category,
        'normal_range': normal_range,
        'loinc_code': loinc_code,
        'cpt_code': cpt_code,
        'external_id': external_id,
        'normalized_name': normalized,
        'search_tokens': tokens
    }).execute()

    # Invalidate caches for this counsellor
    from services.extraction_service import invalidate_list_cache
    invalidate_list_cache(counsellor_id)
    invalidate_counsellor_investigation_cache(counsellor_id)

    return result.data[0] if result.data else {}


def update_counsellor_investigation(investigation_id: uuid.UUID, **kwargs) -> Dict[str, Any]:
    """Update a counsellor's investigation."""
    update_data = {k: v for k, v in kwargs.items() if v is not None}

    # Regenerate normalized name and tokens if investigation_name or common_names changed
    if 'investigation_name' in update_data:
        update_data['normalized_name'] = normalize_investigation_name(update_data['investigation_name'])
        update_data['search_tokens'] = generate_search_tokens(
            update_data['investigation_name'],
            update_data.get('common_names')
        )
    elif 'common_names' in update_data:
        # Get current investigation_name
        current = supabase.table('counsellor_investigations').select('investigation_name').eq(
            'id', str(investigation_id)
        ).single().execute()
        if current.data:
            update_data['search_tokens'] = generate_search_tokens(
                current.data['investigation_name'],
                update_data['common_names']
            )

    result = supabase.table('counsellor_investigations').update(
        update_data
    ).eq('id', str(investigation_id)).execute()

    # Invalidate caches for this counsellor
    if result.data and result.data[0].get('counsellor_id'):
        from services.extraction_service import invalidate_list_cache
        counsellor_uuid = uuid.UUID(result.data[0]['counsellor_id'])
        invalidate_list_cache(counsellor_uuid)
        invalidate_counsellor_investigation_cache(counsellor_uuid)

    return result.data[0] if result.data else {}


def delete_counsellor_investigation(investigation_id: uuid.UUID) -> bool:
    """Soft delete a counsellor's investigation."""
    try:
        # Get counsellor_id before deleting for cache invalidation
        investigation = supabase.table('counsellor_investigations').select('counsellor_id').eq(
            'id', str(investigation_id)
        ).single().execute()
        counsellor_id = investigation.data.get('counsellor_id') if investigation.data else None

        supabase.table('counsellor_investigations').update({
            'is_active': False
        }).eq('id', str(investigation_id)).execute()

        # Invalidate caches for this counsellor
        if counsellor_id:
            from services.extraction_service import invalidate_list_cache
            counsellor_uuid = uuid.UUID(counsellor_id)
            invalidate_list_cache(counsellor_uuid)
            invalidate_counsellor_investigation_cache(counsellor_uuid)

        return True
    except Exception:
        return False


def has_investigation_lists(counsellor_id: uuid.UUID) -> Dict[str, Any]:
    """
    Check if counsellor or counsellor's school has any investigation lists.
    Uses COUNT query for efficiency - doesn't fetch actual data.

    Args:
        counsellor_id: Counsellor ID to check

    Returns:
        Dict with keys: has_doctor_list, has_hospital_list, has_any_list, school_id
    """
    try:
        # Get counsellor's school_id (cached - 10 min TTL)
        from services.supabase_service import get_counsellor_school_id_cached
        school_id = get_counsellor_school_id_cached(counsellor_id)

        # Check counsellor's list (count only, no data fetch)
        counsellor_result = supabase.table('counsellor_investigations').select(
            'id', count='exact', head=True
        ).eq('counsellor_id', str(counsellor_id)).eq('is_active', True).limit(1).execute()
        has_doctor_list = (counsellor_result.count or 0) > 0

        # Check school's list
        has_hospital_list = False
        if school_id:
            school_result = supabase.table('school_investigation_lists').select(
                'id', count='exact', head=True
            ).eq('school_id', str(school_id)).eq('is_active', True).limit(1).execute()
            has_hospital_list = (school_result.count or 0) > 0

        result = {
            "has_doctor_list": has_doctor_list,
            "has_hospital_list": has_hospital_list,
            "has_any_list": has_doctor_list or has_hospital_list,
            "school_id": school_id
        }

        logger.debug(f"[Investigation] has_investigation_lists for counsellor {counsellor_id}: {result}")
        return result

    except Exception as e:
        logger.error(f"[Investigation] Error checking investigation lists for counsellor {counsellor_id}: {e}")
        # Return True by default to avoid skipping lists on error
        return {
            "has_doctor_list": True,
            "has_hospital_list": True,
            "has_any_list": True,
            "school_id": None
        }


def list_counsellor_investigations(
    counsellor_id: uuid.UUID,
    investigation_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List all investigations for a counsellor.

    Uses in-memory cache (8-hour TTL) when no search filter is applied.
    Cache is invalidated when investigations are added/updated/deleted.
    """
    # Only use cache when no search filter (search results aren't cached)
    if not search:
        cached = get_cached_counsellor_investigations(counsellor_id, investigation_type, category)
        if cached is not None:
            return cached

    # Cache miss or search query - fetch from DB
    query = supabase.table('counsellor_investigations').select('*').eq(
        'counsellor_id', str(counsellor_id)
    ).eq('is_active', True)

    if investigation_type:
        query = query.eq('investigation_type', investigation_type)

    if category:
        query = query.eq('category', category)

    result = query.order('investigation_name').execute()
    investigations = result.data or []

    # Client-side search if needed
    if search:
        search_lower = search.lower()
        investigations = [
            inv for inv in investigations
            if search_lower in inv['investigation_name'].lower()
            or search_lower in inv['normalized_name']
            or any(search_lower in cn.lower() for cn in (inv['common_names'] or []))
        ]
    else:
        # Cache the result (only when no search filter)
        set_cached_counsellor_investigations(counsellor_id, investigations, investigation_type, category)

    return investigations


def copy_school_investigation_to_counsellor(
    school_investigation_id: uuid.UUID,
    counsellor_id: uuid.UUID
) -> Optional[Dict[str, Any]]:
    """Copy a school investigation to counsellor's personal list."""
    try:
        # Use RPC if available
        result = supabase.rpc(
            'copy_school_investigation_to_counsellor_rpc',
            {
                'p_school_investigation_id': str(school_investigation_id),
                'p_counsellor_id': str(counsellor_id)
            }
        ).execute()

        if result.data:
            return {"id": result.data, "message": "Copied successfully"}
        return None

    except Exception as e:
        logger.warning(f"[Investigation] RPC copy failed, using fallback: {e}")

        # Fallback to manual copy
        school_inv = supabase.table('school_investigation_lists').select(
            '*'
        ).eq('id', str(school_investigation_id)).single().execute()

        if not school_inv.data:
            return None

        hi = school_inv.data
        return create_counsellor_investigation(
            counsellor_id=counsellor_id,
            investigation_name=hi['investigation_name'],
            investigation_type=hi['investigation_type'],
            common_names=hi['common_names'],
            category=hi['category'],
            normal_range=hi['normal_range'],
            loinc_code=hi['loinc_code'],
            cpt_code=hi['cpt_code'],
            external_id=hi.get('external_id')
        )


# ============================================================================
# CRUD - School Investigations
# ============================================================================

def create_school_investigation(school_id: uuid.UUID, created_by: uuid.UUID, **kwargs) -> Dict[str, Any]:
    """Create a single investigation for a school."""
    investigation_name = kwargs.get('investigation_name', '')
    investigation_type = kwargs.get('investigation_type', '')
    common_names = list(kwargs.get('common_names', []))  # Make a copy to avoid mutating

    # Auto-generate aliases from investigation name (augment existing common_names)
    auto_aliases = extract_investigation_aliases(investigation_name, common_names)
    for alias in auto_aliases:
        if alias.lower() not in {cn.lower() for cn in common_names}:
            common_names.append(alias)

    # Validate investigation_type
    if investigation_type not in ('laboratory', 'imaging', 'other'):
        investigation_type = classify_investigation_type(investigation_name)

    normalized = normalize_investigation_name(investigation_name)
    tokens = generate_search_tokens(investigation_name, common_names)

    data = {
        'school_id': str(school_id),
        'created_by': str(created_by),
        'investigation_name': investigation_name,
        'investigation_type': investigation_type,
        'common_names': common_names,
        'category': kwargs.get('category'),
        'normal_range': kwargs.get('normal_range'),
        'loinc_code': kwargs.get('loinc_code'),
        'cpt_code': kwargs.get('cpt_code'),
        'normalized_name': normalized,
        'search_tokens': tokens
    }

    result = supabase.table('school_investigation_lists').insert(data).execute()

    # Invalidate caches (school-level change)
    from services.extraction_service import invalidate_list_cache_by_school
    invalidate_list_cache_by_school(school_id)
    invalidate_school_investigation_cache(school_id)

    return result.data[0] if result.data else {}


def list_school_investigations(
    school_id: uuid.UUID,
    investigation_type: Optional[str] = None,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List all investigations for a school.

    Uses in-memory cache (8-hour TTL) for faster repeated access.
    Cache is invalidated when school investigations are added/updated/deleted.
    """
    # Check cache first
    cached = get_cached_school_investigations(school_id, investigation_type, category)
    if cached is not None:
        return cached

    # Cache miss - fetch from DB
    query = supabase.table('school_investigation_lists').select('*').eq(
        'school_id', str(school_id)
    ).eq('is_active', True)

    if investigation_type:
        query = query.eq('investigation_type', investigation_type)

    if category:
        query = query.eq('category', category)

    result = query.order('investigation_name').execute()
    investigations = result.data or []

    # Cache the result
    set_cached_school_investigations(school_id, investigations, investigation_type, category)

    return investigations


def update_school_investigation(investigation_id: uuid.UUID, **kwargs) -> Dict[str, Any]:
    """Update a school investigation."""
    update_data = {k: v for k, v in kwargs.items() if v is not None}

    # Regenerate normalized name and tokens if investigation_name or common_names changed
    if 'investigation_name' in update_data:
        update_data['normalized_name'] = normalize_investigation_name(update_data['investigation_name'])
        update_data['search_tokens'] = generate_search_tokens(
            update_data['investigation_name'],
            update_data.get('common_names')
        )
    elif 'common_names' in update_data:
        # Get current investigation_name
        current = supabase.table('school_investigation_lists').select('investigation_name').eq(
            'id', str(investigation_id)
        ).single().execute()
        if current.data:
            update_data['search_tokens'] = generate_search_tokens(
                current.data['investigation_name'],
                update_data['common_names']
            )

    result = supabase.table('school_investigation_lists').update(
        update_data
    ).eq('id', str(investigation_id)).execute()

    # Invalidate caches (school-level change)
    if result.data and result.data[0].get('school_id'):
        from services.extraction_service import invalidate_list_cache_by_school
        school_uuid = uuid.UUID(result.data[0]['school_id'])
        invalidate_list_cache_by_school(school_uuid)
        invalidate_school_investigation_cache(school_uuid)

    return result.data[0] if result.data else {}


def delete_school_investigation(investigation_id: uuid.UUID) -> bool:
    """Soft delete a school investigation."""
    try:
        # Get school_id before deleting for cache invalidation
        investigation = supabase.table('school_investigation_lists').select('school_id').eq(
            'id', str(investigation_id)
        ).single().execute()
        school_id = investigation.data.get('school_id') if investigation.data else None

        supabase.table('school_investigation_lists').update({
            'is_active': False
        }).eq('id', str(investigation_id)).execute()

        # Invalidate caches (school-level change)
        if school_id:
            from services.extraction_service import invalidate_list_cache_by_school
            school_uuid = uuid.UUID(school_id)
            invalidate_list_cache_by_school(school_uuid)
            invalidate_school_investigation_cache(school_uuid)

        return True
    except Exception:
        return False


# ============================================================================
# Matching Functions
# ============================================================================

def _calculate_fuzzy_score(s1: str, s2: str) -> float:
    """Calculate fuzzy match score between two strings."""
    if RAPIDFUZZ_AVAILABLE:
        return fuzz.ratio(s1, s2) / 100.0
    else:
        # Basic Levenshtein-ish similarity
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        # Simple word overlap
        words1 = set(s1.lower().split())
        words2 = set(s2.lower().split())
        overlap = len(words1 & words2)
        total = len(words1 | words2)
        return overlap / total if total > 0 else 0.0


async def get_counsellor_feedback_for_investigation(
    counsellor_id: uuid.UUID,
    original_name: str
) -> Optional[Dict[str, Any]]:
    """
    Check if counsellor has previous feedback for this investigation name.

    Returns the most recent feedback record if found.
    """
    try:
        result = supabase.rpc(
            'get_investigation_feedback_history_rpc',
            {
                'p_counsellor_id': str(counsellor_id),
                'p_original_name': original_name
            }
        ).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception as e:
        logger.warning(f"[Investigation] Feedback lookup failed: {e}")

        # Fallback to direct query
        result = supabase.table('investigation_match_log').select(
            'matched_investigation_name, correct_investigation_name, feedback_status, match_confidence'
        ).eq('counsellor_id', str(counsellor_id)).ilike(
            'original_investigation_name', original_name
        ).not_.is_('feedback_status', 'null').order(
            'created_at', desc=True
        ).limit(1).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None


async def match_investigation_name(
    extracted_name: str,
    counsellor_id: uuid.UUID,
    investigation_type: Optional[str] = None,
    submission_id: str = "",
    threshold: float = MIN_FUZZY_THRESHOLD
) -> Dict[str, Any]:
    """
    Match extracted investigation name using 7-level matching algorithm.

    Matching Priority (Exact/Common first in BOTH lists, then Fuzzy):
    1. Feedback history (agreed/disagreed) → 95% confidence
    2. Counsellor list - exact match → 100% confidence
    3. Counsellor list - common name match → 98% confidence
    4. School list - exact match → 90% confidence
    5. School list - common name match → 88% confidence
    6. Counsellor list - fuzzy match (90%+ only) → typo correction
    7. School list - fuzzy match (90%+ only) → typo correction

    Args:
        extracted_name: Name extracted from transcript
        counsellor_id: Counsellor ID
        investigation_type: Filter by type (laboratory, imaging, other)
        submission_id: Submission ID for logging
        threshold: Minimum confidence threshold (default 0.90 for typo-only correction)

    Returns:
        Dict with: matched, original_name, matched_name, confidence, method, source
    """
    import time as time_module
    match_start = time_module.time()

    normalized_extracted = normalize_investigation_name(extracted_name)
    logger.info(f"[Investigation Match] Processing: '{extracted_name}' (normalized: '{normalized_extracted}')")

    # Level 1: Check feedback history (highest priority - counsellor's explicit preference)
    feedback_start = time_module.time()
    feedback = await get_counsellor_feedback_for_investigation(counsellor_id, extracted_name)
    feedback_duration = time_module.time() - feedback_start
    if feedback:
        if feedback['feedback_status'] == 'agreed':
            total_duration = time_module.time() - match_start
            logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': feedback_lookup={feedback_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (FEEDBACK_AGREED)")
            logger.info(f"[Investigation Match] ✓ FEEDBACK_AGREED: '{extracted_name}' → '{feedback['matched_investigation_name']}' (from previous feedback)")
            return {
                "matched": True,
                "original_name": extracted_name,
                "matched_name": feedback['matched_investigation_name'],
                "confidence": 0.95,
                "method": "feedback_agreed",
                "source": "feedback_history"
            }
        elif feedback['feedback_status'] == 'disagreed' and feedback['correct_investigation_name']:
            total_duration = time_module.time() - match_start
            logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': feedback_lookup={feedback_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (FEEDBACK_CORRECTED)")
            logger.info(f"[Investigation Match] ✓ FEEDBACK_CORRECTED: '{extracted_name}' → '{feedback['correct_investigation_name']}' (counsellor correction)")
            return {
                "matched": True,
                "original_name": extracted_name,
                "matched_name": feedback['correct_investigation_name'],
                "confidence": 0.95,
                "method": "feedback_corrected",
                "source": "feedback_history"
            }

    # Get counsellor's school_id for school list lookup (cached - 10 min TTL)
    from services.supabase_service import get_counsellor_school_id_cached
    school_id = get_counsellor_school_id_cached(counsellor_id)

    # Load both lists upfront
    list_load_start = time_module.time()
    counsellor_invs = list_counsellor_investigations(counsellor_id, investigation_type=investigation_type)
    school_invs = list_school_investigations(uuid.UUID(school_id), investigation_type=investigation_type) if school_id else []
    list_load_duration = time_module.time() - list_load_start

    # =========================================================================
    # PHASE 1: Exact and Common Name matches (check BOTH lists before fuzzy)
    # =========================================================================
    exact_match_start = time_module.time()

    # Level 2: Exact match in counsellor's list
    for inv in counsellor_invs:
        if inv['normalized_name'] == normalized_extracted:
            exact_match_duration = time_module.time() - exact_match_start
            total_duration = time_module.time() - match_start
            logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (EXACT_DOCTOR)")
            logger.info(f"[Investigation Match] ✓ EXACT_DOCTOR: '{extracted_name}' → '{inv['investigation_name']}' (100% confidence)")
            return {
                "matched": True,
                "original_name": extracted_name,
                "matched_name": inv['investigation_name'],
                "matched_investigation_id": inv['id'],
                "confidence": 1.0,
                "method": "exact",
                "source": "doctor_list",
                "investigation_type": inv.get('investigation_type'),
                "category": inv.get('category'),
                "external_id": inv.get('external_id'),
                "common_names": inv.get('common_names')
            }

    # Level 3: Common name match in counsellor's list
    for inv in counsellor_invs:
        for common in (inv.get('common_names') or []):
            if normalize_investigation_name(common) == normalized_extracted:
                exact_match_duration = time_module.time() - exact_match_start
                total_duration = time_module.time() - match_start
                logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (COMMON_NAME_DOCTOR)")
                logger.info(f"[Investigation Match] ✓ COMMON_NAME_DOCTOR: '{extracted_name}' → '{inv['investigation_name']}' (matched via common name '{common}')")
                return {
                    "matched": True,
                    "original_name": extracted_name,
                    "matched_name": inv['investigation_name'],
                    "matched_investigation_id": inv['id'],
                    "confidence": 0.98,
                    "method": "common_name",
                    "source": "doctor_list",
                    "investigation_type": inv.get('investigation_type'),
                    "category": inv.get('category'),
                    "external_id": inv.get('external_id'),
                    "common_names": inv.get('common_names')
                }

    # Level 4: Exact match in school list
    for inv in school_invs:
        if inv['normalized_name'] == normalized_extracted:
            exact_match_duration = time_module.time() - exact_match_start
            total_duration = time_module.time() - match_start
            logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (EXACT_HOSPITAL)")
            logger.info(f"[Investigation Match] ✓ EXACT_HOSPITAL: '{extracted_name}' → '{inv['investigation_name']}' (90% confidence)")
            return {
                "matched": True,
                "original_name": extracted_name,
                "matched_name": inv['investigation_name'],
                "matched_school_investigation_id": inv['id'],
                "confidence": 0.90,
                "method": "exact",
                "source": "hospital_list",
                "investigation_type": inv.get('investigation_type'),
                "category": inv.get('category'),
                "external_id": inv.get('external_id'),
                "common_names": inv.get('common_names')
            }

    # Level 5: Common name match in school list
    for inv in school_invs:
        for common in (inv.get('common_names') or []):
            if normalize_investigation_name(common) == normalized_extracted:
                exact_match_duration = time_module.time() - exact_match_start
                total_duration = time_module.time() - match_start
                logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (COMMON_NAME_HOSPITAL)")
                logger.info(f"[Investigation Match] ✓ COMMON_NAME_HOSPITAL: '{extracted_name}' → '{inv['investigation_name']}' (matched via common name '{common}')")
                return {
                    "matched": True,
                    "original_name": extracted_name,
                    "matched_name": inv['investigation_name'],
                    "matched_school_investigation_id": inv['id'],
                    "confidence": 0.88,
                    "method": "common_name",
                    "source": "hospital_list",
                    "investigation_type": inv.get('investigation_type'),
                    "category": inv.get('category'),
                    "external_id": inv.get('external_id'),
                    "common_names": inv.get('common_names')
                }

    exact_match_duration = time_module.time() - exact_match_start

    # =========================================================================
    # PHASE 2: Prefix/Substring match (handles Gemini truncating names)
    # If extracted name is a significant prefix (>= 60%) of an investigation name, match it
    # =========================================================================
    prefix_match_start = time_module.time()
    logger.info(f"[Investigation Match] No exact/common_name match, trying prefix match (coverage: {PREFIX_MATCH_COVERAGE*100:.0f}%)...")

    # Check if extracted name is a prefix of any investigation in counsellor's list
    for inv in counsellor_invs:
        inv_normalized = inv['normalized_name']
        # Check if extracted is a prefix of the investigation name
        if inv_normalized.startswith(normalized_extracted) and len(normalized_extracted) > 3:
            coverage = len(normalized_extracted) / len(inv_normalized)
            if coverage >= PREFIX_MATCH_COVERAGE:
                prefix_match_duration = time_module.time() - prefix_match_start
                total_duration = time_module.time() - match_start
                confidence = 0.95  # High confidence for prefix match
                logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact={exact_match_duration*1000:.1f}ms, prefix={prefix_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (PREFIX_DOCTOR)")
                logger.info(f"[Investigation Match] ✓ PREFIX_DOCTOR: '{extracted_name}' → '{inv['investigation_name']}' (coverage: {coverage*100:.1f}%)")
                return {
                    "matched": True,
                    "original_name": extracted_name,
                    "matched_name": inv['investigation_name'],
                    "matched_investigation_id": inv['id'],
                    "confidence": confidence,
                    "method": "prefix",
                    "source": "doctor_list",
                    "investigation_type": inv.get('investigation_type'),
                    "category": inv.get('category'),
                    "external_id": inv.get('external_id'),
                    "common_names": inv.get('common_names')
                }

    # Check if extracted name is a prefix of any investigation in school's list
    for inv in school_invs:
        inv_normalized = inv['normalized_name']
        # Check if extracted is a prefix of the investigation name
        if inv_normalized.startswith(normalized_extracted) and len(normalized_extracted) > 3:
            coverage = len(normalized_extracted) / len(inv_normalized)
            if coverage >= PREFIX_MATCH_COVERAGE:
                prefix_match_duration = time_module.time() - prefix_match_start
                total_duration = time_module.time() - match_start
                confidence = 0.92  # Slightly lower for school list
                logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact={exact_match_duration*1000:.1f}ms, prefix={prefix_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (PREFIX_HOSPITAL)")
                logger.info(f"[Investigation Match] ✓ PREFIX_HOSPITAL: '{extracted_name}' → '{inv['investigation_name']}' (coverage: {coverage*100:.1f}%)")
                return {
                    "matched": True,
                    "original_name": extracted_name,
                    "matched_name": inv['investigation_name'],
                    "matched_school_investigation_id": inv['id'],
                    "confidence": confidence,
                    "method": "prefix",
                    "source": "hospital_list",
                    "investigation_type": inv.get('investigation_type'),
                    "category": inv.get('category'),
                    "external_id": inv.get('external_id'),
                    "common_names": inv.get('common_names')
                }

    prefix_match_duration = time_module.time() - prefix_match_start

    # =========================================================================
    # PHASE 3: Fuzzy matches (for typo/transcription correction - 80%+ threshold)
    # =========================================================================
    fuzzy_match_start = time_module.time()
    logger.info(f"[Investigation Match] No exact/common_name/prefix match found, trying fuzzy (threshold: {threshold*100:.0f}%)...")

    # Level 6: Fuzzy match in counsellor's list
    best_counsellor_match = None
    best_counsellor_score = 0

    for inv in counsellor_invs:
        score = _calculate_fuzzy_score(normalized_extracted, inv['normalized_name'])
        if score > best_counsellor_score and score >= threshold:
            best_counsellor_score = score
            best_counsellor_match = inv

        # Also check common names for fuzzy
        for common in (inv.get('common_names') or []):
            common_score = _calculate_fuzzy_score(normalized_extracted, normalize_investigation_name(common))
            if common_score > best_counsellor_score and common_score >= threshold:
                best_counsellor_score = common_score
                best_counsellor_match = inv

    # Level 7: Fuzzy match in school list
    best_school_match = None
    best_school_score = 0

    for inv in school_invs:
        score = _calculate_fuzzy_score(normalized_extracted, inv['normalized_name'])
        if score > best_school_score and score >= threshold:
            best_school_score = score
            best_school_match = inv

        # Also check common names for fuzzy
        for common in (inv.get('common_names') or []):
            common_score = _calculate_fuzzy_score(normalized_extracted, normalize_investigation_name(common))
            if common_score > best_school_score and common_score >= threshold:
                best_school_score = common_score
                best_school_match = inv

    # Return best fuzzy match (prefer counsellor list if scores are equal)
    if best_counsellor_match and best_counsellor_score >= best_school_score:
        fuzzy_match_duration = time_module.time() - fuzzy_match_start
        total_duration = time_module.time() - match_start
        confidence = best_counsellor_score * 0.95  # Scale to 85-95% range
        logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, fuzzy_match={fuzzy_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (FUZZY_DOCTOR)")
        logger.info(f"[Investigation Match] ✓ FUZZY_DOCTOR: '{extracted_name}' → '{best_counsellor_match['investigation_name']}' (score: {best_counsellor_score*100:.1f}%)")
        return {
            "matched": True,
            "original_name": extracted_name,
            "matched_name": best_counsellor_match['investigation_name'],
            "matched_investigation_id": best_counsellor_match['id'],
            "confidence": confidence,
            "method": "fuzzy",
            "source": "doctor_list",
            "investigation_type": best_counsellor_match.get('investigation_type'),
            "category": best_counsellor_match.get('category'),
            "external_id": best_counsellor_match.get('external_id'),
            "common_names": best_counsellor_match.get('common_names')
        }

    if best_school_match:
        fuzzy_match_duration = time_module.time() - fuzzy_match_start
        total_duration = time_module.time() - match_start
        confidence = best_school_score * 0.90  # Scale to 81-90% range
        logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, fuzzy_match={fuzzy_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (FUZZY_HOSPITAL)")
        logger.info(f"[Investigation Match] ✓ FUZZY_HOSPITAL: '{extracted_name}' → '{best_school_match['investigation_name']}' (score: {best_school_score*100:.1f}%)")
        return {
            "matched": True,
            "original_name": extracted_name,
            "matched_name": best_school_match['investigation_name'],
            "matched_school_investigation_id": best_school_match['id'],
            "confidence": confidence,
            "method": "fuzzy",
            "source": "hospital_list",
            "investigation_type": best_school_match.get('investigation_type'),
            "category": best_school_match.get('category'),
            "external_id": best_school_match.get('external_id'),
            "common_names": best_school_match.get('common_names')
        }

    # No match found - trust Gemini's extraction
    fuzzy_match_duration = time_module.time() - fuzzy_match_start
    total_duration = time_module.time() - match_start
    logger.info(f"[TIMING_INVESTIGATION_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, fuzzy_match={fuzzy_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (NO_MATCH)")
    logger.info(f"[Investigation Match] ✗ NO_MATCH: '{extracted_name}' - keeping Gemini's original extraction")
    return {
        "matched": False,
        "original_name": extracted_name,
        "matched_name": extracted_name,  # Keep original
        "confidence": 0.0,
        "method": "no_match",
        "source": None,
        "external_id": None,
        "investigation_type": None,
        "common_names": None
    }


# ============================================================================
# Post-Processing
# ============================================================================

async def postprocess_investigations_extraction(
    extraction_data: Dict[str, Any],
    counsellor_id: uuid.UUID,
    extraction_id: uuid.UUID,
    submission_id: str,
    template_id: Optional[uuid.UUID] = None,
    log_matches: bool = True
) -> Dict[str, Any]:
    """
    Match all investigations in extraction and return updated extraction.

    Args:
        extraction_data: Full extraction result
        counsellor_id: Counsellor ID
        extraction_id: Extraction record ID
        submission_id: Submission ID for ground truth
        template_id: Template ID for adaptive learning
        log_matches: Whether to log matches

    Returns:
        Updated extraction data with matched investigations
    """
    # Find investigations data - check common field names
    investigations_fields = ['investigations', 'labs', 'tests', 'labTests']
    investigations_data = None

    # First check top-level keys (for templates with separate INVESTIGATIONS segment)
    for key in investigations_fields:
        if key in extraction_data:
            investigations_data = extraction_data[key]
            break

    # If not found at top level, check nested inside clinicalNotes/CLINICAL_NOTES
    # (CARDIO and other templates nest investigations inside the clinical notes segment)
    if not investigations_data:
        for parent_key in ['clinicalNotes', 'CLINICAL_NOTES']:
            parent = extraction_data.get(parent_key)
            if isinstance(parent, dict):
                for key in investigations_fields:
                    if key in parent:
                        investigations_data = parent[key]
                        break
            if investigations_data:
                break

    if not investigations_data:
        logger.debug(f"[Investigation] No investigations data found in extraction")
        return extraction_data

    all_tests = []

    # Handle list format (AOSTA format: [{Test_Name, Test_ShortName, Test_type, ...}])
    if isinstance(investigations_data, list):
        for test in investigations_data:
            if isinstance(test, dict):
                # Detect investigation type from Test_type (AOSTA) or type field
                test_type = (test.get('Test_type') or test.get('Type') or test.get('type') or '').lower()
                if test_type in ('laboratory', 'lab'):
                    test['_inv_type'] = 'laboratory'
                elif test_type in ('imaging', 'radiology'):
                    test['_inv_type'] = 'imaging'
                else:
                    test['_inv_type'] = 'other'
                all_tests.append(test)

    # Handle dict format with laboratory_tests, imaging_studies, other_tests
    elif isinstance(investigations_data, dict):
        # Process each investigation type
        inv_type_mapping = {
            'laboratory_tests': 'laboratory',
            'imaging_studies': 'imaging',
            'other_tests': 'other'
        }

        for field_key, inv_type in inv_type_mapping.items():
            if field_key in investigations_data and isinstance(investigations_data[field_key], list):
                for test in investigations_data[field_key]:
                    if isinstance(test, dict):
                        test['_inv_field_key'] = field_key
                        test['_inv_type'] = inv_type
                        all_tests.append(test)

    if not all_tests:
        logger.debug(f"[Investigation] No tests found to process in investigations data")
        return extraction_data

    # Log what Gemini originally extracted
    # Support multiple field name conventions: name (standard), Test_Name (AOSTA), test_name, study_name (legacy)
    gemini_tests = []
    for t in all_tests:
        for key in ['name', 'Test_Name', 'test_name', 'study_name']:
            if key in t and t[key]:
                gemini_tests.append(t[key])
                break
    logger.debug(f"[Investigation Post-Process] AI extracted {len(gemini_tests)} investigations: {gemini_tests}")

    # Match each investigation
    for test in all_tests:
        # Find test name field (standard: name, AOSTA: Test_Name, legacy: test_name, study_name)
        name_fields = ['name', 'Test_Name', 'test_name', 'study_name']
        original_name = None
        name_key = None

        for key in name_fields:
            if key in test and test[key]:
                original_name = test[key]
                name_key = key
                break

        if not original_name:
            continue

        # Match investigation
        match_result = await match_investigation_name(
            extracted_name=original_name,
            counsellor_id=counsellor_id,
            investigation_type=test.get('_inv_type'),
            submission_id=submission_id
        )

        # Update investigation name if matched
        if match_result['matched'] and match_result['matched_name'] != original_name:
            test[name_key] = match_result['matched_name']

        # Include additional fields for EHR integrations (even for exact matches)
        if match_result['matched']:
            if match_result.get('external_id'):
                # Update Test_id directly if it exists (AOSTA format), also add _external_id for other formatters
                if 'Test_id' in test:
                    test['Test_id'] = match_result['external_id']
                test['_external_id'] = match_result['external_id']
            if match_result.get('investigation_type'):
                test['_investigation_type'] = match_result['investigation_type']
            if match_result.get('common_names'):
                test['_common_names'] = match_result['common_names']
            if match_result.get('category'):
                test['_category'] = match_result['category']

        # Log match if requested
        if log_matches:
            try:
                # Separate IDs for doctor_list vs hospital_list matches
                matched_counsellor_inv_id = None
                matched_school_inv_id = None

                if match_result.get('source') == 'doctor_list':
                    matched_counsellor_inv_id = match_result.get('matched_investigation_id')
                elif match_result.get('source') == 'hospital_list':
                    matched_school_inv_id = match_result.get('matched_school_investigation_id')

                supabase.table('investigation_match_log').insert({
                    'extraction_id': str(extraction_id),
                    'submission_id': submission_id,
                    'counsellor_id': str(counsellor_id),
                    'original_investigation_name': original_name,
                    'investigation_type': test.get('_inv_type'),
                    'matched_investigation_id': matched_counsellor_inv_id,
                    'matched_school_investigation_id': matched_school_inv_id,
                    'matched_investigation_name': match_result['matched_name'],
                    'match_confidence': match_result['confidence'],
                    'match_method': match_result['method'],
                    'match_source': match_result['source']
                }).execute()
            except Exception as e:
                logger.warning(f"[Investigation] Failed to log match: {e}")

        # Clean up internal fields
        test.pop('_inv_field_key', None)
        test.pop('_inv_type', None)

    return extraction_data


# ============================================================================
# NEO Template Investigation Post-Processing
# ============================================================================

def _log_neo_investigation_match(
    extraction_id: uuid.UUID,
    submission_id: str,
    counsellor_id: uuid.UUID,
    original_name: str,
    match_result: Dict[str, Any]
) -> None:
    """Log a NEO investigation match to the investigation_match_log table."""
    try:
        matched_counsellor_inv_id = None
        matched_school_inv_id = None
        if match_result.get("source") == "doctor_list":
            matched_counsellor_inv_id = match_result.get("matched_investigation_id")
        elif match_result.get("source") == "hospital_list":
            matched_school_inv_id = match_result.get("matched_school_investigation_id")

        supabase.table("investigation_match_log").insert({
            "extraction_id": str(extraction_id),
            "submission_id": submission_id,
            "counsellor_id": str(counsellor_id),
            "original_investigation_name": original_name,
            "investigation_type": None,
            "matched_investigation_id": matched_counsellor_inv_id,
            "matched_school_investigation_id": matched_school_inv_id,
            "matched_investigation_name": match_result.get("matched_name", original_name),
            "match_confidence": match_result.get("confidence", 0),
            "match_method": match_result.get("method", "neo_postprocess"),
            "match_source": match_result.get("source", "neo_template"),
        }).execute()
    except Exception as e:
        logger.warning(f"[NEO Investigation Post-Process] Failed to log match for '{original_name}': {e}")


# ============================================================================
# Feedback Functions
# ============================================================================

def submit_investigation_feedback(
    match_log_id: uuid.UUID,
    feedback_status: str,  # 'agreed' or 'disagreed'
    correct_investigation_id: Optional[uuid.UUID] = None,
    correct_investigation_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit feedback for an investigation match.

    If agreed + school source → Auto-copy to counsellor's personal list.

    Args:
        match_log_id: Match log record ID
        feedback_status: 'agreed' or 'disagreed'
        correct_investigation_id: If disagreed, correct investigation ID
        correct_investigation_name: If disagreed, correct name (manual entry)

    Returns:
        Updated match log record
    """
    if feedback_status not in ('agreed', 'disagreed'):
        raise ValueError("feedback_status must be 'agreed' or 'disagreed'")

    # Get current match log
    match_log = supabase.table('investigation_match_log').select(
        '*'
    ).eq('id', str(match_log_id)).single().execute()

    if not match_log.data:
        raise ValueError("Match log not found")

    ml = match_log.data

    # Update feedback
    update_data = {
        'feedback_status': feedback_status,
        'feedback_at': datetime.utcnow().isoformat()
    }

    if feedback_status == 'disagreed':
        if correct_investigation_id:
            update_data['correct_investigation_id'] = str(correct_investigation_id)
        if correct_investigation_name:
            update_data['correct_investigation_name'] = correct_investigation_name

    result = supabase.table('investigation_match_log').update(
        update_data
    ).eq('id', str(match_log_id)).execute()

    counsellor_id = ml.get('counsellor_id')

    # Auto-copy to personal list if agreed with school match
    if feedback_status == 'agreed' and ml.get('match_source') == 'hospital_list':
        if ml.get('matched_school_investigation_id') and counsellor_id:
            try:
                copy_school_investigation_to_counsellor(
                    school_investigation_id=uuid.UUID(ml['matched_school_investigation_id']),
                    counsellor_id=uuid.UUID(counsellor_id)
                )
                logger.debug(f"[Investigation] Auto-copied school investigation to counsellor's list")
            except Exception as e:
                logger.warning(f"[Investigation] Auto-copy failed: {e}")

    # Auto-add to personal list if agreed with no_match (counsellor confirms original name is correct)
    if feedback_status == 'agreed' and ml.get('match_method') == 'no_match' and counsellor_id:
        original_name = ml.get('original_investigation_name', '')
        if original_name:
            try:
                # Check if already exists in counsellor's list
                existing = supabase.table('counsellor_investigations')\
                    .select('id')\
                    .eq('counsellor_id', str(counsellor_id))\
                    .eq('normalized_name', normalize_investigation_name(original_name))\
                    .limit(1)\
                    .execute()

                if not existing.data:
                    inv_type = ml.get('investigation_type') or classify_investigation_type(original_name)
                    # Add original name to counsellor's list
                    create_counsellor_investigation(
                        counsellor_id=uuid.UUID(counsellor_id),
                        investigation_name=original_name,
                        investigation_type=inv_type,
                        common_names=[],
                        category='Added from Feedback'
                    )
                    logger.debug(f"[Investigation] Added '{original_name}' to counsellor's list (from no_match feedback)")
            except Exception as e:
                logger.warning(f"[Investigation] Auto-add from no_match failed: {e}")

    # Auto-add correction to personal list if disagreed with correction provided
    if feedback_status == 'disagreed' and correct_investigation_name and counsellor_id:
        try:
            # Check if already exists in counsellor's list
            existing = supabase.table('counsellor_investigations')\
                .select('id, common_names')\
                .eq('counsellor_id', str(counsellor_id))\
                .eq('normalized_name', normalize_investigation_name(correct_investigation_name))\
                .limit(1)\
                .execute()

            original_name = ml.get('original_investigation_name', '')
            inv_type = ml.get('investigation_type') or classify_investigation_type(correct_investigation_name)

            if not existing.data:
                # Create new investigation entry with original name as common_name
                create_counsellor_investigation(
                    counsellor_id=uuid.UUID(counsellor_id),
                    investigation_name=correct_investigation_name,
                    investigation_type=inv_type,
                    common_names=[original_name] if original_name else [],
                    category='Corrections'
                )
                logger.debug(f"[Investigation] Added correction '{correct_investigation_name}' to counsellor's list")
            else:
                # Add original name as common_name if not already present
                existing_id = existing.data[0]['id']
                current_names = existing.data[0].get('common_names') or []
                if original_name and original_name.lower() not in [n.lower() for n in current_names]:
                    updated_names = current_names + [original_name]
                    supabase.table('counsellor_investigations')\
                        .update({'common_names': updated_names})\
                        .eq('id', existing_id)\
                        .execute()
                    logger.debug(f"[Investigation] Added '{original_name}' as common name for '{correct_investigation_name}'")
        except Exception as e:
            logger.warning(f"[Investigation] Auto-add correction failed: {e}")

    logger.info(f"[Investigation] Feedback submitted: {feedback_status} for match {match_log_id}")
    return result.data[0] if result.data else {}


def list_pending_investigation_feedback(
    counsellor_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
    include_exact_matches: bool = False
) -> List[Dict[str, Any]]:
    """
    Get match logs pending feedback for the dedicated review screen.

    By default, only returns matches that NEED counsellor action:
    - 'fuzzy' matches: System guessed a correction - counsellor should confirm/reject
    - 'no_match' matches: New investigation not in any list - counsellor should add/correct
    - 'doctor_edit' matches: FYI only (counsellor already corrected in UI)

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias
    - 'feedback_agreed'/'feedback_corrected': Already reviewed

    Args:
        counsellor_id: Counsellor ID
        limit: Max records to return
        offset: Records to skip
        include_exact_matches: If True, also include exact and common_name matches

    Returns:
        List of pending feedback records
    """
    # Query all pending feedback
    result = supabase.table('investigation_match_log').select(
        '*'
    ).eq('counsellor_id', str(counsellor_id)).is_(
        'feedback_status', 'null'
    ).order('created_at', desc=True).execute()

    records = result.data or []

    # Filter to only show matches that need review
    if not include_exact_matches:
        # Show matches that need counsellor action:
        # - 'fuzzy': System guessed a correction - counsellor should confirm/reject
        # - 'no_match': New investigation not in any list - counsellor should add/correct
        # - 'doctor_edit': FYI only (already agreed implicitly)
        #
        # Exclude (already correct, no action needed):
        # - 'exact': Gemini used exact name from list
        # - 'common_name': Gemini used a known alias
        # - 'feedback_agreed'/'feedback_corrected': Already reviewed
        filtered_records = [
            r for r in records
            if r.get('match_method') in ('fuzzy', 'no_match')
            or (r.get('match_method') or '').startswith('doctor_edit')
        ]
        records = filtered_records

    # Apply pagination after filtering
    paginated = records[offset:offset + limit]

    return paginated


def list_investigation_feedback_history(
    counsellor_id: uuid.UUID,
    feedback_status: Optional[str] = None,
    investigation_type: Optional[str] = None,
    confidence_min: Optional[float] = None,
    confidence_max: Optional[float] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    include_exact_matches: bool = False
) -> Dict[str, Any]:
    """
    Get feedback history with filters for the review screen.

    By default, only returns matches that NEED/NEEDED counsellor action:
    - 'fuzzy' matches: System guessed a correction
    - 'no_match' matches: New investigation not in any list
    - 'doctor_edit' matches: Counsellor corrected in UI

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Args:
        counsellor_id: Counsellor ID
        feedback_status: Filter by status ('agreed', 'disagreed', None for all)
        investigation_type: Filter by type ('laboratory', 'imaging', 'other')
        confidence_min: Minimum confidence
        confidence_max: Maximum confidence
        source: Filter by source ('doctor_list', 'hospital_list')
        search: Search in investigation names
        limit: Max records
        offset: Records to skip
        include_exact_matches: If True, also include exact and common_name matches

    Returns:
        Dict with records and total count
    """
    query = supabase.table('investigation_match_log').select(
        '*', count='exact'
    ).eq('counsellor_id', str(counsellor_id))

    if feedback_status:
        query = query.eq('feedback_status', feedback_status)

    if investigation_type:
        query = query.eq('investigation_type', investigation_type)

    if confidence_min is not None:
        query = query.gte('match_confidence', confidence_min)

    if confidence_max is not None:
        query = query.lte('match_confidence', confidence_max)

    if source:
        query = query.eq('match_source', source)

    result = query.order('created_at', desc=True).execute()

    records = result.data or []

    # Filter to only show matches that need/needed review (unless include_exact_matches)
    if not include_exact_matches:
        records = [
            r for r in records
            if r.get('match_method') in ('fuzzy', 'no_match')
            or (r.get('match_method') or '').startswith('doctor_edit')
        ]

    # Client-side search if needed
    if search:
        search_lower = search.lower()
        records = [
            r for r in records
            if search_lower in (r.get('original_investigation_name') or '').lower()
            or search_lower in (r.get('matched_investigation_name') or '').lower()
        ]

    # Apply pagination after filtering
    total = len(records)
    paginated = records[offset:offset + limit]

    return {
        "records": paginated,
        "total": total,
        "limit": limit,
        "offset": offset
    }


# ============================================================================
# Prompt Injection
# ============================================================================

def get_investigation_list_for_prompt(
    counsellor_id: uuid.UUID,
    school_id: Optional[uuid.UUID] = None,
    max_investigations: int = 100
) -> str:
    """
    Generate investigation list formatted for prompt injection.

    Args:
        counsellor_id: Counsellor ID
        school_id: School ID (optional, auto-detected if not provided)
        max_investigations: Maximum investigations to include

    Returns:
        Formatted string for injection into user prompt
    """
    # Get counsellor's school if not provided (cached - 10 min TTL)
    if not school_id:
        from services.supabase_service import get_counsellor_school_id_cached
        cached_school_id = get_counsellor_school_id_cached(counsellor_id)
        if cached_school_id:
            school_id = uuid.UUID(cached_school_id)

    # Get investigations
    counsellor_invs = list_counsellor_investigations(counsellor_id)
    school_invs = list_school_investigations(school_id) if school_id else []

    # Combine and deduplicate
    all_invs = {}
    for inv in counsellor_invs:
        all_invs[inv['normalized_name']] = inv

    for inv in school_invs:
        if inv['normalized_name'] not in all_invs:
            all_invs[inv['normalized_name']] = inv

    if not all_invs:
        return ""

    # Group by investigation type
    by_type = {
        "laboratory": [],
        "imaging": [],
        "other": []
    }

    for inv in list(all_invs.values())[:max_investigations]:
        inv_type = inv.get('investigation_type') or 'other'
        if inv_type not in by_type:
            inv_type = 'other'
        by_type[inv_type].append(inv)

    # Format for prompt
    lines = ["**COUNSELLOR'S INVESTIGATION LIST (Use these exact names when extracting investigations):**", ""]

    type_titles = {
        "laboratory": "Laboratory Tests:",
        "imaging": "Imaging Studies:",
        "other": "Other Investigations:"
    }

    for inv_type, title in type_titles.items():
        invs = by_type[inv_type]
        if invs:
            lines.append(title)
            for inv in invs:
                common_str = ""
                if inv.get('common_names'):
                    common_str = f" (also: {', '.join(inv['common_names'])})"
                lines.append(f"  - {inv['investigation_name']}{common_str}")
            lines.append("")

    return "\n".join(lines)


# ============================================================================
# Investigation Edit Feedback - Compare original vs edited extractions
# ============================================================================

EDIT_SIMILARITY_THRESHOLD = 0.60
EDIT_DISSIMILARITY_THRESHOLD = 0.40


def _is_valid_investigation_edit(original: str, edited: str) -> Tuple[bool, float, str]:
    """
    Determine if the edit represents a valid investigation correction.

    Returns:
        Tuple of (is_valid_edit, similarity_score, edit_type)
    """
    if not original or not edited:
        return False, 0.0, 'invalid'

    norm_original = normalize_investigation_name(original)
    norm_edited = normalize_investigation_name(edited)

    if norm_original == norm_edited:
        return False, 1.0, 'formatting_only'

    if RAPIDFUZZ_AVAILABLE:
        similarity = fuzz.token_sort_ratio(norm_original, norm_edited) / 100.0
    else:
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, norm_original, norm_edited).ratio()

    if similarity < EDIT_DISSIMILARITY_THRESHOLD:
        return False, similarity, 'different_investigation'

    if similarity >= EDIT_SIMILARITY_THRESHOLD:
        return True, similarity, 'name_standardization'

    return False, similarity, 'different_investigation'


async def process_investigation_edit_feedback(
    extraction_id: uuid.UUID,
    counsellor_id: uuid.UUID,
    original_extraction: Dict[str, Any],
    edited_extraction: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare original vs edited extraction and log investigation name changes as feedback.

    Args:
        extraction_id: extraction UUID
        counsellor_id: Counsellor UUID who made edits
        original_extraction: AI-generated extraction JSON
        edited_extraction: Counsellor-edited extraction JSON

    Returns:
        Summary of processed investigation edits
    """
    results = {
        "processed": 0,
        "logged": 0,
        "added_to_list": 0,
        "skipped_different_investigation": 0,
        "skipped_no_match": 0,
        "errors": []
    }

    # Get submission_id from extraction for logging
    try:
        ext_result = supabase.table("extractions")\
            .select("session_id")\
            .eq("id", str(extraction_id))\
            .limit(1)\
            .execute()

        session_id = ext_result.data[0]["session_id"] if ext_result.data else None
        submission_id = None
        if session_id:
            job_result = supabase.table("processing_jobs")\
                .select("submission_id")\
                .eq("session_id", session_id)\
                .limit(1)\
                .execute()
            if job_result.data:
                submission_id = job_result.data[0]["submission_id"]
    except Exception as e:
        logger.warning(f"[InvestigationEditFeedback] Failed to get session/submission IDs: {e}")
        submission_id = None

    # Extract investigations from both versions
    investigations_fields = ['investigations', 'labs', 'tests']

    def extract_all_tests(data: Dict) -> List[Tuple[str, str, Dict]]:
        """Extract all tests with their names, types, and full data."""
        all_tests = []

        def _process_inv_data(inv_data):
            """Process investigation data (dict or list format)."""
            if isinstance(inv_data, dict):
                # Legacy nested format
                for field_key in ['laboratory_tests', 'imaging_studies', 'other_tests']:
                    if field_key in inv_data and isinstance(inv_data[field_key], list):
                        for test in inv_data[field_key]:
                            if isinstance(test, dict):
                                for name_key in ['name', 'test_name', 'study_name']:
                                    if name_key in test and test[name_key]:
                                        all_tests.append((test[name_key], field_key, test))
                                        break
            elif isinstance(inv_data, list):
                # Flat array format: [{name, type, date}, ...]
                for test in inv_data:
                    if isinstance(test, dict):
                        for name_key in ['name', 'Test_Name', 'test_name', 'study_name']:
                            if name_key in test and test[name_key]:
                                inv_type = test.get('type', 'Other') or 'Other'
                                all_tests.append((test[name_key], inv_type, test))
                                break

        # Check top-level keys
        for key in investigations_fields:
            if key in data:
                _process_inv_data(data[key])

        # Also check nested inside clinicalNotes/CLINICAL_NOTES
        if not all_tests:
            for parent_key in ['clinicalNotes', 'CLINICAL_NOTES']:
                parent = data.get(parent_key)
                if isinstance(parent, dict):
                    for key in investigations_fields:
                        if key in parent:
                            _process_inv_data(parent[key])

        return all_tests

    original_tests = extract_all_tests(original_extraction)
    edited_tests = extract_all_tests(edited_extraction)

    if not original_tests or not edited_tests:
        return results

    # Match and process
    used_edited_indices = set()

    for orig_name, orig_type, orig_test in original_tests:
        best_match = None
        best_similarity = 0.0
        best_idx = -1

        for idx, (edit_name, edit_type, edit_test) in enumerate(edited_tests):
            if idx in used_edited_indices:
                continue

            if RAPIDFUZZ_AVAILABLE:
                similarity = fuzz.token_sort_ratio(
                    normalize_investigation_name(orig_name),
                    normalize_investigation_name(edit_name)
                ) / 100.0
            else:
                from difflib import SequenceMatcher
                similarity = SequenceMatcher(
                    None,
                    normalize_investigation_name(orig_name),
                    normalize_investigation_name(edit_name)
                ).ratio()

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = (edit_name, edit_type, edit_test)
                best_idx = idx

        if best_match and best_similarity >= EDIT_SIMILARITY_THRESHOLD:
            used_edited_indices.add(best_idx)
            results["processed"] += 1

            is_valid, _, edit_type = _is_valid_investigation_edit(orig_name, best_match[0])

            if not is_valid:
                if edit_type == 'formatting_only':
                    continue
                results["skipped_different_investigation"] += 1
                continue

            try:
                supabase.table('investigation_match_log').insert({
                    'extraction_id': str(extraction_id),
                    'submission_id': submission_id,
                    'counsellor_id': str(counsellor_id),
                    'original_investigation_name': orig_name,
                    'matched_investigation_name': best_match[0],
                    'match_confidence': best_similarity,
                    'match_method': 'doctor_edit',
                    'match_source': 'doctor_correction',
                    'feedback_status': 'agreed',
                    'feedback_at': datetime.utcnow().isoformat()
                }).execute()
                results["logged"] += 1
            except Exception as e:
                results["errors"].append(f"Log failed: {str(e)}")

            # Auto-add to list
            try:
                existing = supabase.table('counsellor_investigations')\
                    .select('id')\
                    .eq('counsellor_id', str(counsellor_id))\
                    .eq('normalized_name', normalize_investigation_name(best_match[0]))\
                    .limit(1)\
                    .execute()

                if not existing.data:
                    # Check school list first for enriched data
                    added_via_school = False
                    try:
                        from services.supabase_service import get_counsellor_school_id_cached
                        school_id = get_counsellor_school_id_cached(counsellor_id)
                        if school_id:
                            school_match = supabase.table('school_investigation_lists')\
                                .select('id')\
                                .eq('school_id', str(school_id))\
                                .eq('normalized_name', normalize_investigation_name(best_match[0]))\
                                .eq('is_active', True)\
                                .limit(1).execute()
                            if school_match.data:
                                copy_result = copy_school_investigation_to_counsellor(
                                    school_investigation_id=uuid.UUID(school_match.data[0]['id']),
                                    counsellor_id=counsellor_id
                                )
                                if copy_result:
                                    added_via_school = True
                                    logger.debug(f"[InvestigationEditFeedback] Added '{best_match[0]}' from school list (enriched)")
                                    # Add orig_name as common_name on the new counsellor record
                                    if orig_name.lower() != best_match[0].lower():
                                        new_rec = supabase.table('counsellor_investigations')\
                                            .select('id, common_names')\
                                            .eq('counsellor_id', str(counsellor_id))\
                                            .eq('normalized_name', normalize_investigation_name(best_match[0]))\
                                            .limit(1).execute()
                                        if new_rec.data:
                                            names = new_rec.data[0].get('common_names') or []
                                            if orig_name.lower() not in [n.lower() for n in names]:
                                                supabase.table('counsellor_investigations')\
                                                    .update({'common_names': names + [orig_name]})\
                                                    .eq('id', new_rec.data[0]['id']).execute()
                    except Exception as e:
                        logger.warning(f"[InvestigationEditFeedback] School list check failed: {e}")

                    if not added_via_school:
                        # Fallback: add bare entry without school enrichment
                        inv_type = classify_investigation_type(best_match[0])
                        create_counsellor_investigation(
                            counsellor_id=counsellor_id,
                            investigation_name=best_match[0],
                            investigation_type=inv_type,
                            common_names=[orig_name] if orig_name.lower() != best_match[0].lower() else []
                        )
                        logger.debug(f"[InvestigationEditFeedback] Added '{best_match[0]}' (bare)")
                    results["added_to_list"] += 1
            except Exception as e:
                results["errors"].append(f"Add to list failed: {str(e)}")
        else:
            results["skipped_no_match"] += 1

    logger.debug(f"[InvestigationEditFeedback] Completed: {results}")
    return results


# ============================================================================
# Backfill - Enrich counsellor investigations from school list
# ============================================================================

def backfill_counsellor_investigations_from_school(
    counsellor_id: uuid.UUID,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Backfill counsellor investigation entries that have no external_id by matching
    against the school investigation list and copying enrichment fields.

    Fields updated: external_id, category, normal_range, loinc_code,
    cpt_code, investigation_type, common_names (merged).
    """
    from services.supabase_service import get_counsellor_school_id_cached

    result = {
        "counsellor_id": str(counsellor_id),
        "dry_run": dry_run,
        "total_doctor_investigations": 0,
        "missing_external_id": 0,
        "matched": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "details": []
    }

    school_id = get_counsellor_school_id_cached(counsellor_id)
    if not school_id:
        result["errors"].append("Counsellor has no associated school")
        return result

    # Get counsellor investigations missing external_id
    counsellor_invs = supabase.table('counsellor_investigations')\
        .select('id, investigation_name, normalized_name, common_names, external_id')\
        .eq('counsellor_id', str(counsellor_id))\
        .eq('is_active', True)\
        .execute()

    if not counsellor_invs.data:
        return result

    result["total_doctor_investigations"] = len(counsellor_invs.data)
    missing = [inv for inv in counsellor_invs.data if not inv.get('external_id')]
    result["missing_external_id"] = len(missing)

    if not missing:
        return result

    # Build school lookup by normalized_name
    school_invs = supabase.table('school_investigation_lists')\
        .select('id, investigation_name, normalized_name, common_names, external_id, category, normal_range, loinc_code, cpt_code, investigation_type')\
        .eq('school_id', str(school_id))\
        .eq('is_active', True)\
        .execute()

    school_lookup = {}
    for hi in (school_invs.data or []):
        norm = hi.get('normalized_name', '')
        if norm:
            school_lookup[norm] = hi

    for di in missing:
        norm_name = di.get('normalized_name', '')
        hi = school_lookup.get(norm_name)

        if not hi:
            result["skipped"] += 1
            continue

        result["matched"] += 1

        # Merge common_names
        counsellor_names = di.get('common_names') or []
        school_names = hi.get('common_names') or []
        existing_lower = {n.lower() for n in counsellor_names}
        merged_names = list(counsellor_names)
        for name in school_names:
            if name.lower() not in existing_lower:
                merged_names.append(name)
                existing_lower.add(name.lower())

        update_data = {
            'external_id': hi.get('external_id'),
            'category': hi.get('category'),
            'normal_range': hi.get('normal_range'),
            'loinc_code': hi.get('loinc_code'),
            'cpt_code': hi.get('cpt_code'),
            'investigation_type': hi.get('investigation_type'),
            'common_names': merged_names
        }
        # Only include non-None fields (don't overwrite with None)
        update_data = {k: v for k, v in update_data.items() if v is not None}

        detail = {
            "doctor_investigation_id": di['id'],
            "investigation_name": di['investigation_name'],
            "hospital_external_id": hi.get('external_id'),
            "fields_to_update": list(update_data.keys())
        }

        if dry_run:
            result["details"].append(detail)
        else:
            try:
                supabase.table('counsellor_investigations')\
                    .update(update_data)\
                    .eq('id', di['id'])\
                    .execute()
                result["updated"] += 1
                result["details"].append({**detail, "status": "updated"})
            except Exception as e:
                result["errors"].append(f"Update failed for {di['investigation_name']}: {str(e)}")
                result["details"].append({**detail, "status": "error", "error": str(e)})

    logger.info(f"[InvestigationBackfill] counsellor={counsellor_id} dry_run={dry_run} "
                f"total={result['total_doctor_investigations']} missing={result['missing_external_id']} "
                f"matched={result['matched']} updated={result['updated']}")
    return result

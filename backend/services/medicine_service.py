"""
Medicine Service - Doctor Medicine List Management and Matching

This module handles:
- CSV parsing and medicine list upload
- Medicine normalization and tokenization
- 5-level matching algorithm with feedback learning
- Post-processing for prescription extraction
- Adaptive learning via segment definition updates

Matching Priority (5 levels):
1. Doctor's previous feedback (agreed/disagreed) → 95% confidence
2. Doctor's personal list - exact match → 100% confidence
3. Doctor's personal list - fuzzy match → 70-95% confidence
4. Hospital list - exact match → 90% confidence
5. Hospital list - fuzzy match → 60-85% confidence

Diagnosis Context Boost: +10% confidence when diagnosis matches medicine category
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
# MEDICINE LIST DATA CACHE (with TTL and invalidation)
# ============================================================================
# Caches actual medicine list data to avoid 718ms DB load per extraction
# Separate from extraction_service's _list_availability_cache (which only caches existence check)

_doctor_medicines_cache: Dict[str, Dict[str, Any]] = {}
_hospital_medicines_cache: Dict[str, Dict[str, Any]] = {}
_MEDICINE_CACHE_TTL_SECONDS = 31536000  # 1 year (effectively infinite - invalidated on list updates, cleared on server restart)

def _get_doctor_cache_key(doctor_id: uuid.UUID, category: Optional[str] = None) -> str:
    """Generate cache key for doctor medicine list."""
    return f"doc_med_{doctor_id}_{category or 'all'}"

def _get_hospital_cache_key(hospital_id: uuid.UUID, category: Optional[str] = None) -> str:
    """Generate cache key for hospital medicine list."""
    return f"hosp_med_{hospital_id}_{category or 'all'}"

def get_cached_doctor_medicines(doctor_id: uuid.UUID, category: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """Get cached doctor medicine list if not expired."""
    cache_key = _get_doctor_cache_key(doctor_id, category)
    if cache_key in _doctor_medicines_cache:
        entry = _doctor_medicines_cache[cache_key]
        if datetime.now() < entry["expires_at"]:
            logger.info(f"[TIMING_MEDICINE_LIST] ♻️ Cache HIT for doctor {str(doctor_id)[:8]}... ({len(entry['data'])} medicines)")
            return entry["data"]
        else:
            del _doctor_medicines_cache[cache_key]
    return None

def get_cached_hospital_medicines(hospital_id: uuid.UUID, category: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """Get cached hospital medicine list if not expired."""
    cache_key = _get_hospital_cache_key(hospital_id, category)
    if cache_key in _hospital_medicines_cache:
        entry = _hospital_medicines_cache[cache_key]
        if datetime.now() < entry["expires_at"]:
            logger.info(f"[TIMING_MEDICINE_LIST] ♻️ Cache HIT for hospital {str(hospital_id)[:8]}... ({len(entry['data'])} medicines)")
            return entry["data"]
        else:
            del _hospital_medicines_cache[cache_key]
    return None

def set_cached_doctor_medicines(doctor_id: uuid.UUID, data: List[Dict[str, Any]], category: Optional[str] = None) -> None:
    """Cache doctor medicine list with TTL."""
    cache_key = _get_doctor_cache_key(doctor_id, category)
    _doctor_medicines_cache[cache_key] = {
        "data": data,
        "expires_at": datetime.now() + timedelta(seconds=_MEDICINE_CACHE_TTL_SECONDS),
        "cached_at": datetime.now()
    }
    logger.debug(f"[MEDICINE_CACHE] 💾 Cached {len(data)} medicines for doctor {str(doctor_id)[:8]}... (TTL: ∞, invalidated on update)")

def set_cached_hospital_medicines(hospital_id: uuid.UUID, data: List[Dict[str, Any]], category: Optional[str] = None) -> None:
    """Cache hospital medicine list with TTL."""
    cache_key = _get_hospital_cache_key(hospital_id, category)
    _hospital_medicines_cache[cache_key] = {
        "data": data,
        "expires_at": datetime.now() + timedelta(seconds=_MEDICINE_CACHE_TTL_SECONDS),
        "cached_at": datetime.now()
    }
    logger.debug(f"[MEDICINE_CACHE] 💾 Cached {len(data)} medicines for hospital {str(hospital_id)[:8]}... (TTL: ∞, invalidated on update)")

def invalidate_doctor_medicine_cache(doctor_id: uuid.UUID) -> int:
    """Invalidate all medicine list cache entries for a doctor."""
    keys_to_delete = [k for k in _doctor_medicines_cache.keys() if str(doctor_id) in k]
    for key in keys_to_delete:
        del _doctor_medicines_cache[key]
    if keys_to_delete:
        logger.debug(f"[MEDICINE_CACHE] 🗑️ Invalidated {len(keys_to_delete)} cache entries for doctor {str(doctor_id)[:8]}...")
    return len(keys_to_delete)

def invalidate_hospital_medicine_cache(hospital_id: uuid.UUID) -> int:
    """Invalidate all medicine list cache entries for a hospital."""
    keys_to_delete = [k for k in _hospital_medicines_cache.keys() if str(hospital_id) in k]
    for key in keys_to_delete:
        del _hospital_medicines_cache[key]
    if keys_to_delete:
        logger.debug(f"[MEDICINE_CACHE] 🗑️ Invalidated {len(keys_to_delete)} cache entries for hospital {str(hospital_id)[:8]}...")
    return len(keys_to_delete)

def invalidate_all_hospital_medicine_caches() -> int:
    """Invalidate ALL hospital medicine caches. Used when hospital-level changes affect all."""
    count = len(_hospital_medicines_cache)
    _hospital_medicines_cache.clear()
    if count:
        logger.debug(f"[MEDICINE_CACHE] 🗑️ Invalidated ALL hospital medicine caches ({count} entries)")
    return count

def invalidate_all_doctor_medicine_caches() -> int:
    """Invalidate ALL doctor medicine caches. Used for global cache refresh."""
    count = len(_doctor_medicines_cache)
    _doctor_medicines_cache.clear()
    if count:
        logger.debug(f"[MEDICINE_CACHE] 🗑️ Invalidated ALL doctor medicine caches ({count} entries)")
    return count

# ============================================================================
# Configuration
# ============================================================================

ADAPTIVE_LEARNING_THRESHOLD = 0.85  # Threshold for auto-updating segment definitions
DIAGNOSIS_CONTEXT_BOOST = 0.10  # +10% confidence boost for diagnosis match
MIN_FUZZY_THRESHOLD = 0.85  # Threshold for fuzzy matching - higher threshold to avoid false matches like "Crocin" → "CALRITIN"
PREFIX_MATCH_COVERAGE = 0.60  # Minimum coverage for prefix/substring matching (60% of full name)

# Medicine category to diagnosis keyword mapping
CATEGORY_DIAGNOSIS_MAP = {
    "antihypertensive": ["hypertension", "high blood pressure", "bp", "htn"],
    "antidiabetic": ["diabetes", "dm", "blood sugar", "hyperglycemia"],
    "antibiotic": ["infection", "fever", "sepsis", "bacterial"],
    "analgesic": ["pain", "headache", "ache", "arthritis"],
    "antipyretic": ["fever", "pyrexia", "temperature"],
    "antihistamine": ["allergy", "allergic", "rhinitis", "urticaria"],
    "bronchodilator": ["asthma", "copd", "wheeze", "dyspnea"],
    "antacid": ["acid", "gerd", "gastritis", "reflux"],
    "statin": ["cholesterol", "hyperlipidemia", "lipid"],
    "diuretic": ["edema", "fluid", "heart failure"],
}

# Prefixes to remove during normalization
MEDICINE_PREFIXES = [
    "TAB.", "TAB ", "TABLET ", "TABLETS ",
    "CAP.", "CAP ", "CAPSULE ", "CAPSULES ",
    "SYR.", "SYR ", "SYRUP ",
    "INJ.", "INJ ", "INJECTION ",
    "CR.", "CR ",
    "SR.", "SR ",
    "XR.", "XR ",
    "ER.", "ER ",
    "DR.", "DR ",
]

# Medicine form keywords for auto-detection from name
# Order matters - more specific keywords should come first
MEDICINE_FORM_KEYWORDS = {
    "Tablet": ["tablet", "tablets", "tab ", "tab.", " tab"],
    "Capsule": ["capsule", "capsules", "cap ", "cap.", " cap"],
    "Syrup": ["syrup", "syrups", "syr ", "syr.", " syr", "syp ", "syp.", " syp", "liquid", "oral solution", "suspension"],
    "Injection": ["injection", "injections", "inj ", "inj.", " inj", "injectable", "vial", "ampoule", "ampule"],
    "Drops": ["drops", "drop ", "eye drop", "ear drop", "nasal drop"],
    "Cream": ["cream", "creams"],
    "Ointment": ["ointment", "ointments", "gel ", " gel", "topical"],
    "Inhaler": ["inhaler", "inhalers", "rotacap", "respule", "nebulizer", "puff"],
    "Patch": ["patch", "patches", "transdermal"],
    "Suppository": ["suppository", "suppositories", "rectal", "vaginal"],
    "Powder": ["powder", "powders", "sachet"],
    "Granules": ["granules", "granule"],
    "Vaccine": ["vaccine", "vaccines"],
    "Penfill": ["penfill", "pen ", " pen", "flexpen", "cartridge"],
    "Spray": ["spray", "sprays", "nasal spray", "oral spray"],
    "Oil": ["oil", "oils"],
    "Soap": ["soap", "soaps", "wash", "cleanser"],
    "Lotion": ["lotion", "lotions"],
    "Paste": ["paste", "pastes", " past"],
    "Jelly": ["jelly", "jellies"],
    "Enema": ["enema", "enemas"],
    "Bandage": ["bandage", "bandages"],
}


# Column mapping for alternate CSV formats (maps alternate column names to internal names)
# Keys are lowercase for case-insensitive matching
MEDICINE_COLUMN_MAP = {
    # Brand Name -> name (primary medicine name)
    "brand name": "name",
    "brandname": "name",
    "brand_name": "name",
    # Generic Name -> formulary_name
    "generic name": "formulary_name",
    "genericname": "formulary_name",
    "generic_name": "formulary_name",
    # BrandID -> external_id
    "brandid": "external_id",
    "brand_id": "external_id",
    "brand id": "external_id",
    # ProductCode -> product_code
    "productcode": "product_code",
    "product_code": "product_code",
    "product code": "product_code",
    # Dosage -> typical_dosage
    "dosage": "typical_dosage",
}


# ============================================================================
# Medicine Alias Extraction
# ============================================================================
# Common abbreviations for medicine names - used to auto-generate common_names
# for better Gemini recognition when CSV contains complex names like "T - CALPOL 650MG TAB Kg TABLET"

MEDICINE_ABBREVIATIONS = {
    # Painkillers / Antipyretics
    "paracetamol": ["PARA", "PCM", "CROCIN"],
    "acetaminophen": ["APAP"],
    "ibuprofen": ["IBU"],
    "diclofenac": ["DICLO"],
    "aspirin": ["ASA"],
    # Antibiotics — General
    "amoxicillin": ["AMOX"],
    "azithromycin": ["AZITH", "AZEE"],
    "ciprofloxacin": ["CIPRO"],
    "metronidazole": ["METRO", "FLAGYL"],
    "cefixime": ["CEF"],
    "cephalexin": ["CEPH"],
    "doxycycline": ["DOXY"],
    "levofloxacin": ["LEVO"],
    # Antibiotics — Neonatal / ICU
    "gentamicin": ["GENTA"],
    "ampicillin": ["AMPI"],
    "vancomycin": ["VANCO"],
    "meropenem": ["MERO"],
    "ceftriaxone": ["CEFTRI"],
    "piperacillin": ["PIPZO", "PIP-TAZ"],
    "amikacin": ["AMIKA"],
    "cefotaxime": ["CEFOTA"],
    "linezolid": ["LINE"],
    "colistin": ["COLI"],
    "fluconazole": ["FLUCO"],
    "acyclovir": ["ACYCLO"],
    # Cardiovascular
    "amlodipine": ["AMLO"],
    "atenolol": ["ATEN"],
    "metoprolol": ["METO"],
    "losartan": ["LOSAR"],
    "telmisartan": ["TELMI"],
    "enalapril": ["ENAL"],
    # Diabetes
    "metformin": ["MET"],
    "glimepiride": ["GLIM"],
    "sitagliptin": ["SITA"],
    # GI
    "omeprazole": ["OME", "OMEZ"],
    "pantoprazole": ["PANTO", "PAN"],
    "ranitidine": ["RANI"],
    "domperidone": ["DOM"],
    "ondansetron": ["ONDAN"],
    # Neonatal — Respiratory / Cardiac
    "caffeine citrate": ["CAFFEINE"],
    "surfactant": ["SURFA"],
    "dopamine": ["DOPA"],
    "dobutamine": ["DOBU"],
    "milrinone": ["MILRI"],
    "sildenafil": ["SILDE"],
    # Neonatal — Neuro / Anticonvulsants
    "phenobarbitone": ["PHENOBARB", "PB"],
    "levetiracetam": ["LEVETI", "KEPPRA"],
    # Steroids / Anti-inflammatory
    "prednisolone": ["PRED"],
    "methylprednisolone": ["MPRED"],
    "dexamethasone": ["DEXA"],
    "hydrocortisone": ["HC"],
    # Sedatives / Analgesics — ICU
    "fentanyl": ["FENTA"],
    "midazolam": ["MIDA"],
    "morphine": ["MORPH"],
    # Diuretics
    "furosemide": ["FURO", "LASIX"],
    # Antihistamines / Respiratory
    "cetirizine": ["CTZ", "CETRIZ"],
    "montelukast": ["MONTE", "MONTAIR"],
    "salbutamol": ["SALBU"],
}

# Noise patterns to remove from complex medicine names (from Aosta format)
MEDICINE_NOISE_PATTERNS = [
    # Units and packaging
    r'\s+Kg\s+',           # " Kg "
    r'\s+kg\s+',           # " kg "
    r'\s+GM\s*$',          # trailing " GM"
    r'\s+ML\s*$',          # trailing " ML"
    r'\s+MG\s+TABLET\s*$', # " MG TABLET" at end
    r'\s+TABLET\s*$',      # trailing " TABLET"
    r'\s+TABLETS\s*$',     # trailing " TABLETS"
    r'\s+TAB\s*$',         # trailing " TAB"
    r'\s+CAPSULE\s*$',     # trailing " CAPSULE"
    r'\s+CAPSULES\s*$',    # trailing " CAPSULES"
    r'\s+CAP\s*$',         # trailing " CAP"
    r'\s+SYRUP\s*$',       # trailing " SYRUP"
    r'\s+LIQUID\s*$',      # trailing " LIQUID"
    r'\s+INJECTION\s*$',   # trailing " INJECTION"
    r'\s+INJ\s*$',         # trailing " INJ"
]

# Prefix patterns to remove (like "T - ", "CAP - ", etc.)
MEDICINE_PREFIX_PATTERNS = [
    r'^T\s*-\s*',          # "T - " or "T-"
    r'^TAB\s*-\s*',        # "TAB - "
    r'^CAP\s*-\s*',        # "CAP - "
    r'^SYR\s*-\s*',        # "SYR - "
    r'^INJ\s*-\s*',        # "INJ - "
    r'^TABLET\s*-\s*',     # "TABLET - "
    r'^CAPSULE\s*-\s*',    # "CAPSULE - "
]


def extract_medicine_aliases(medicine_name: str, existing_common_names: Optional[List[str]] = None) -> List[str]:
    """
    Extract short recognizable aliases from complex medicine names.

    This helps Gemini recognize medicines when the hospital list has complex names like:
    "T - CALPOL 650MG TAB Kg TABLET" -> aliases: ["CALPOL", "CALPOL 650", "CALPOL TABLET"]

    IMPORTANT: When there are two medicines with same base name but different forms
    (e.g., CALPOL TABLET vs CALPOL SYRUP), the form-based aliases help distinguish them.

    Args:
        medicine_name: The full medicine name (e.g., "T - CALPOL 650MG TAB Kg TABLET")
        existing_common_names: Existing common names to avoid duplicates

    Returns:
        List of unique aliases not already in existing_common_names

    Examples:
        >>> extract_medicine_aliases("T - CALPOL 650MG TAB Kg TABLET")
        ['CALPOL', 'CALPOL 650', 'CALPOL TABLET', 'CALPOL 650 TABLET']
        >>> extract_medicine_aliases("CALPOL SYRUP 125MG/5ML")
        ['CALPOL', 'CALPOL 125', 'CALPOL SYRUP', 'CALPOL 125 SYRUP']
        >>> extract_medicine_aliases("AMLODIPINE 5MG TABLET")
        ['AMLODIPINE', 'AMLO', 'AMLODIPINE 5', 'AMLODIPINE TABLET']
    """
    if not medicine_name:
        return []

    existing_set = set()
    if existing_common_names:
        existing_set = {cn.lower().strip() for cn in existing_common_names if cn}

    # Also add the original name to avoid returning it as an alias
    existing_set.add(medicine_name.lower().strip())

    aliases = []

    # Work with uppercase for pattern matching
    name_upper = medicine_name.upper().strip()

    # Step 1: Detect form BEFORE cleaning (so we can use it later)
    detected_form = detect_medicine_form(medicine_name)
    # Map detected form to short versions for aliases
    form_short_map = {
        "Tablet": "TABLET",
        "Capsule": "CAPSULE",
        "Syrup": "SYRUP",
        "Injection": "INJECTION",
        "Drops": "DROPS",
        "Cream": "CREAM",
        "Ointment": "OINTMENT",
        "Inhaler": "INHALER",
        "Patch": "PATCH",
        "Suppository": "SUPPOSITORY",
        "Powder": "POWDER",
        "Vaccine": "VACCINE",
        "Penfill": "PENFILL",
        "Spray": "SPRAY",
        "Oil": "OIL",
        "Soap": "SOAP",
    }
    form_suffix = form_short_map.get(detected_form) if detected_form else None

    # Step 2: Remove prefix patterns (T -, TAB -, etc.)
    cleaned = name_upper
    for pattern in MEDICINE_PREFIX_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Step 3: Remove noise patterns (Kg, TABLET at end, etc.)
    for pattern in MEDICINE_NOISE_PATTERNS:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)

    # Clean up extra spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if not cleaned:
        return []

    # Step 4: Extract core name (first word, typically the brand name)
    parts = cleaned.split()
    dosage_match = None
    dosage_num = None

    if parts:
        core_name = parts[0]

        # Add core name as alias if not already in existing
        if core_name.lower() not in existing_set:
            aliases.append(core_name)
            existing_set.add(core_name.lower())

        # Step 5: Extract dosage (look for number+unit pattern like 650MG, 5MG, etc.)
        dosage_match = re.search(r'(\d+(?:\.\d+)?)\s*(MG|MCG|G|ML|IU)\b', cleaned, re.IGNORECASE)
        if dosage_match:
            dosage_num = dosage_match.group(1)
            # Create "CORENAME DOSAGE" alias (e.g., "CALPOL 650", "AMLODIPINE 5")
            name_with_dosage = f"{core_name} {dosage_num}"
            if name_with_dosage.lower() not in existing_set:
                aliases.append(name_with_dosage)
                existing_set.add(name_with_dosage.lower())

        # Step 6: Add form-based aliases (helps distinguish CALPOL TABLET from CALPOL SYRUP)
        if form_suffix:
            # "CORENAME FORM" (e.g., "CALPOL TABLET", "CALPOL SYRUP")
            name_with_form = f"{core_name} {form_suffix}"
            if name_with_form.lower() not in existing_set:
                aliases.append(name_with_form)
                existing_set.add(name_with_form.lower())

            # "CORENAME DOSAGE FORM" (e.g., "CALPOL 650 TABLET")
            if dosage_num:
                name_with_dosage_form = f"{core_name} {dosage_num} {form_suffix}"
                if name_with_dosage_form.lower() not in existing_set:
                    aliases.append(name_with_dosage_form)
                    existing_set.add(name_with_dosage_form.lower())

    # Step 7: Check for known abbreviations
    # Look for any known medicine name in the cleaned string
    cleaned_lower = cleaned.lower()
    for generic_name, abbrevs in MEDICINE_ABBREVIATIONS.items():
        if generic_name in cleaned_lower:
            # Found a known medicine - add its abbreviations
            for abbrev in abbrevs:
                if abbrev.lower() not in existing_set:
                    aliases.append(abbrev)
                    existing_set.add(abbrev.lower())

                    # Also create abbreviation + dosage if we found a dosage
                    if dosage_num:
                        abbrev_with_dosage = f"{abbrev} {dosage_num}"
                        if abbrev_with_dosage.lower() not in existing_set:
                            aliases.append(abbrev_with_dosage)
                            existing_set.add(abbrev_with_dosage.lower())

                    # Also create abbreviation + form if we have a form
                    if form_suffix:
                        abbrev_with_form = f"{abbrev} {form_suffix}"
                        if abbrev_with_form.lower() not in existing_set:
                            aliases.append(abbrev_with_form)
                            existing_set.add(abbrev_with_form.lower())

    return aliases


# ============================================================================
# Normalization Functions
# ============================================================================

def normalize_medicine_name(name: str) -> str:
    """
    Normalize medicine name for matching.

    - Remove prefixes (TAB., CAP., SYR., INJ., etc.)
    - Lowercase
    - Collapse multiple spaces
    - Strip leading/trailing whitespace

    Args:
        name: Raw medicine name

    Returns:
        Normalized name
    """
    if not name:
        return ""

    result = name.strip().upper()

    # Remove known prefixes
    for prefix in MEDICINE_PREFIXES:
        if result.startswith(prefix):
            result = result[len(prefix):]
            break

    # Lowercase and clean up spaces
    result = result.lower().strip()
    result = re.sub(r'\s+', ' ', result)

    return result


def generate_search_tokens(medicine_name: str, common_names: Optional[List[str]] = None) -> List[str]:
    """
    Generate search tokens for GIN index search.

    Args:
        medicine_name: Primary medicine name
        common_names: List of alternative names

    Returns:
        List of search tokens
    """
    tokens = set()

    # Tokenize main name
    normalized = normalize_medicine_name(medicine_name)
    tokens.update(normalized.split())

    # Tokenize common names
    if common_names:
        for name in common_names:
            if name:
                tokens.update(normalize_medicine_name(name).split())

    # Remove very short tokens (less than 2 chars)
    tokens = {t for t in tokens if len(t) >= 2}

    return sorted(list(tokens))


def detect_medicine_form(name: str) -> Optional[str]:
    """
    Auto-detect medicine form/dosage type from name.

    Args:
        name: Medicine name to analyze

    Returns:
        Detected form (Tablet, Capsule, etc.) or None if not detected
    """
    if not name:
        return None

    # Trailing space ensures abbreviations like "inj ", "syr " match at end of name
    name_lower = name.lower() + " "

    # Check each form's keywords
    for form, keywords in MEDICINE_FORM_KEYWORDS.items():
        for keyword in keywords:
            if keyword in name_lower:
                return form

    return None


# Form pairs that are NEVER interchangeable
INCOMPATIBLE_FORM_PAIRS = {
    frozenset({"tablet", "syrup"}),
    frozenset({"tablet", "injection"}),
    frozenset({"tablet", "drops"}),
    frozenset({"tablet", "cream"}),
    frozenset({"tablet", "ointment"}),
    frozenset({"tablet", "inhaler"}),
    frozenset({"tablet", "spray"}),
    frozenset({"capsule", "syrup"}),
    frozenset({"capsule", "injection"}),
    frozenset({"capsule", "drops"}),
    frozenset({"capsule", "cream"}),
    frozenset({"syrup", "injection"}),
    frozenset({"syrup", "drops"}),
    frozenset({"syrup", "cream"}),
    frozenset({"syrup", "ointment"}),
    frozenset({"cream", "injection"}),
    frozenset({"ointment", "injection"}),
    frozenset({"suppository", "tablet"}),
    frozenset({"suppository", "syrup"}),
}


def _is_form_mismatch(form1: str, form2: str) -> bool:
    """Check if two medicine forms are incompatible (never interchangeable)."""
    pair = frozenset({form1.lower(), form2.lower()})
    return pair in INCOMPATIBLE_FORM_PAIRS


# ============================================================================
# Shared Enrichment (used by both CSV and JSON upload paths)
# ============================================================================

def _enrich_medicine_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply all enrichment logic to a raw medicine dict (alias generation,
    normalization, form detection, type validation). Used by both CSV and JSON paths.

    Expected input keys: medicine_name (required), common_names (list), category,
    typical_dosage, form, snomed_code, formulary_name, medicine_type, external_id.
    """
    name = raw["medicine_name"]
    common_names = list(raw.get("common_names") or [])

    # Auto-generate aliases from complex medicine names
    auto_aliases = extract_medicine_aliases(name, common_names)
    for alias in auto_aliases:
        if alias.lower() not in {cn.lower() for cn in common_names}:
            common_names.append(alias)

    # Auto-add formulary_name (generic name) to common_names for matching
    formulary_name = raw.get("formulary_name") or None
    if formulary_name and formulary_name.lower() not in {cn.lower() for cn in common_names}:
        common_names.append(formulary_name)

    # Extract abbreviations from formulary_name
    if formulary_name:
        formulary_aliases = extract_medicine_aliases(formulary_name, common_names)
        for alias in formulary_aliases:
            if alias.lower() not in {cn.lower() for cn in common_names}:
                common_names.append(alias)

    medicine = {
        "medicine_name": name,
        "common_names": common_names,
        "category": raw.get("category") or None,
        "typical_dosage": raw.get("typical_dosage") or None,
        "form": raw.get("form") or None,
        "snomed_code": raw.get("snomed_code") or None,
        "formulary_name": formulary_name,
        "medicine_type": (raw.get("medicine_type") or "").lower() or None,
        "external_id": raw.get("external_id") or None,
        "product_code": raw.get("product_code") or None,
        "normalized_name": normalize_medicine_name(name),
        "search_tokens": generate_search_tokens(name, common_names),
    }

    # Validate medicine_type
    if medicine["medicine_type"] and medicine["medicine_type"] not in ("generic", "branded"):
        medicine["medicine_type"] = None

    # Auto-detect form from name if not explicitly provided
    if not medicine["form"]:
        medicine["form"] = detect_medicine_form(name)

    return medicine


# ============================================================================
# CSV Parsing
# ============================================================================

def parse_csv_medicine_list(csv_content: str) -> Tuple[List[Dict], List[Dict]]:
    """
    Parse CSV content into medicine records.

    Expected columns: name, common_name, category, typical_dosage, form, snomed_code, formulary_name, type, external_id
    Alternate columns supported: Brand Name, Generic Name, BrandID (auto-mapped)
    Minimum required: name (or Brand Name)

    Args:
        csv_content: CSV string content

    Returns:
        Tuple of (valid_medicines, errors)
    """
    valid_medicines = []
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
                mapped_field = MEDICINE_COLUMN_MAP.get(field, field)
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

                # Parse common_names (comma-separated in CSV)
                common_names_str = row.get('common_name', '') or row.get('common_names', '')
                common_names = []
                if common_names_str:
                    common_names = [n.strip() for n in common_names_str.split(',') if n.strip()]

                # Build raw record and enrich via shared function
                raw = {
                    "medicine_name": name,
                    "common_names": common_names,
                    "category": row.get('category', '').strip() or None,
                    "typical_dosage": row.get('typical_dosage', '').strip() or None,
                    "form": row.get('form', '').strip() or None,
                    "snomed_code": row.get('snomed_code', '').strip() or None,
                    "formulary_name": row.get('formulary_name', '').strip() or None,
                    "medicine_type": row.get('type', '').strip().lower() or None,
                    "external_id": external_id,
                    "product_code": row.get('product_code', '').strip() or None,
                }

                valid_medicines.append(_enrich_medicine_record(raw))

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

    return valid_medicines, errors


# ============================================================================
# Upload Functions (shared pipeline + thin wrappers)
# ============================================================================

def _upsert_medicine_records(
    doctor_id: uuid.UUID,
    medicines: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    replace_existing: bool,
    upload_id: str,
) -> Dict[str, Any]:
    """
    Shared upload pipeline used by both CSV and JSON upload paths.
    Handles: replace_existing deactivation, dedup, batch upsert,
    upload record update, cache invalidation, result formatting.

    Args:
        doctor_id: Doctor ID
        medicines: List of enriched medicine dicts (already passed through _enrich_medicine_record)
        errors: List of errors from parsing phase (will be extended with upsert errors)
        replace_existing: If True, deactivate existing medicines first
        upload_id: Upload tracking record ID

    Returns:
        Upload result with statistics
    """
    try:
        # Deactivate existing if requested
        if replace_existing and medicines:
            supabase.table('doctor_medicines').update({
                'is_active': False
            }).eq('doctor_id', str(doctor_id)).execute()

        # Prepare all medicines with doctor_id and is_active
        for medicine in medicines:
            medicine['doctor_id'] = str(doctor_id)
            medicine['is_active'] = True

        # Deduplicate by normalized_name (last occurrence wins) —
        # PostgreSQL ON CONFLICT cannot handle duplicate conflict keys in a single batch
        pre_dedup_count = len(medicines)
        seen = {}
        for medicine in medicines:
            seen[medicine['normalized_name']] = medicine
        medicines = list(seen.values())
        if len(medicines) < pre_dedup_count:
            logger.info(f"[Medicine] Deduped {pre_dedup_count} -> {len(medicines)} medicines ({pre_dedup_count - len(medicines)} duplicates removed)")

        # Batch upsert
        successful = 0
        failed = len(errors)
        BATCH_SIZE = 500

        for i in range(0, len(medicines), BATCH_SIZE):
            batch = medicines[i:i + BATCH_SIZE]
            try:
                supabase.table('doctor_medicines').upsert(
                    batch,
                    on_conflict='doctor_id,normalized_name'
                ).execute()
                successful += len(batch)
            except Exception as e:
                # If batch fails, fall back to individual inserts for this batch
                logger.warning(f"[Medicine] Batch upsert failed, falling back to individual inserts: {e}")
                for medicine in batch:
                    try:
                        supabase.table('doctor_medicines').upsert(
                            medicine,
                            on_conflict='doctor_id,normalized_name'
                        ).execute()
                        successful += 1
                    except Exception as inner_e:
                        failed += 1
                        errors.append({
                            "row": "N/A",
                            "error": str(inner_e),
                            "data": medicine
                        })

        # Update upload record
        supabase.table('medicine_list_uploads').update({
            'status': 'completed',
            'row_count': len(medicines) + len(errors),
            'successful_imports': successful,
            'failed_imports': failed,
            'error_details': errors if errors else None,
            'processed_at': datetime.utcnow().isoformat()
        }).eq('id', upload_id).execute()

        logger.info(f"[Medicine] Uploaded {successful} medicines for doctor {doctor_id}")

        # Invalidate caches after successful upload
        from services.extraction_service import invalidate_list_cache
        invalidate_list_cache(doctor_id)
        invalidate_doctor_medicine_cache(doctor_id)

        return {
            "upload_id": upload_id,
            "status": "completed",
            "total_rows": len(medicines) + len(errors),
            "successful": successful,
            "failed": failed,
            "errors": errors[:10] if errors else []
        }

    except Exception as e:
        if upload_id:
            supabase.table('medicine_list_uploads').update({
                'status': 'failed',
                'error_details': [{"error": str(e)}],
                'processed_at': datetime.utcnow().isoformat()
            }).eq('id', upload_id).execute()

        logger.error(f"[Medicine] Upload failed for doctor {doctor_id}: {e}")
        raise


def upload_medicine_list(
    doctor_id: uuid.UUID,
    csv_content: str,
    filename: str,
    replace_existing: bool = False
) -> Dict[str, Any]:
    """Upload and process a CSV medicine list for a doctor."""
    upload_record = supabase.table('medicine_list_uploads').insert({
        'doctor_id': str(doctor_id),
        'filename': filename,
        'file_size_bytes': len(csv_content.encode('utf-8')),
        'status': 'processing'
    }).execute()
    upload_id = upload_record.data[0]['id'] if upload_record.data else None

    medicines, errors = parse_csv_medicine_list(csv_content)
    return _upsert_medicine_records(doctor_id, medicines, errors, replace_existing, upload_id)


def upload_medicine_list_json(
    doctor_id: uuid.UUID,
    medicines: List[Dict[str, Any]],
    replace_existing: bool = False
) -> Dict[str, Any]:
    """Upload a JSON list of medicines for a doctor."""
    upload_record = supabase.table('medicine_list_uploads').insert({
        'doctor_id': str(doctor_id),
        'filename': 'json_upload',
        'file_size_bytes': 0,
        'status': 'processing'
    }).execute()
    upload_id = upload_record.data[0]['id'] if upload_record.data else None

    enriched = []
    errors = []
    for idx, raw in enumerate(medicines):
        try:
            enriched.append(_enrich_medicine_record(raw))
        except Exception as e:
            errors.append({"row": idx + 1, "error": str(e), "data": raw})

    return _upsert_medicine_records(doctor_id, enriched, errors, replace_existing, upload_id)


def upload_hospital_medicine_list(
    hospital_id: uuid.UUID,
    csv_content: str,
    filename: str,
    created_by: uuid.UUID,
    replace_existing: bool = False
) -> Dict[str, Any]:
    """
    Upload and process a CSV medicine list for a hospital.

    Args:
        hospital_id: Hospital ID
        csv_content: CSV string content
        filename: Original filename
        created_by: Admin doctor ID who uploaded
        replace_existing: If True, deactivate existing medicines first

    Returns:
        Upload result with statistics
    """
    try:
        # Parse CSV
        medicines, errors = parse_csv_medicine_list(csv_content)

        # Deactivate existing if requested
        if replace_existing and medicines:
            supabase.table('hospital_medicine_lists').update({
                'is_active': False
            }).eq('hospital_id', str(hospital_id)).execute()

        # Insert medicines in batches (reduces N round-trips to N/500)
        successful = 0
        failed = len(errors)
        BATCH_SIZE = 500

        # Prepare all medicines with hospital_id, created_by, and is_active
        for medicine in medicines:
            medicine['hospital_id'] = str(hospital_id)
            medicine['created_by'] = str(created_by)
            medicine['is_active'] = True

        # Deduplicate by normalized_name (last occurrence wins)
        pre_dedup_count = len(medicines)
        seen = {}
        for medicine in medicines:
            seen[medicine['normalized_name']] = medicine
        medicines = list(seen.values())
        if len(medicines) < pre_dedup_count:
            logger.info(f"[Medicine] Hospital deduped {pre_dedup_count} → {len(medicines)} medicines ({pre_dedup_count - len(medicines)} duplicates removed)")

        # Batch upsert
        for i in range(0, len(medicines), BATCH_SIZE):
            batch = medicines[i:i + BATCH_SIZE]
            try:
                supabase.table('hospital_medicine_lists').upsert(
                    batch,
                    on_conflict='hospital_id,normalized_name'
                ).execute()
                successful += len(batch)
            except Exception as e:
                # If batch fails, fall back to individual inserts for this batch
                logger.warning(f"[Medicine] Hospital batch upsert failed, falling back to individual inserts: {e}")
                for medicine in batch:
                    try:
                        supabase.table('hospital_medicine_lists').upsert(
                            medicine,
                            on_conflict='hospital_id,normalized_name'
                        ).execute()
                        successful += 1
                    except Exception as inner_e:
                        failed += 1
                        errors.append({
                            "row": "N/A",
                            "error": str(inner_e),
                            "data": medicine
                        })

        logger.info(f"[Medicine] Uploaded {successful} hospital medicines for hospital {hospital_id}")

        # Invalidate caches after successful upload
        from services.extraction_service import invalidate_list_cache_by_hospital
        invalidate_list_cache_by_hospital(hospital_id)
        invalidate_hospital_medicine_cache(hospital_id)

        return {
            "status": "completed",
            "total_rows": len(medicines) + len(errors),
            "successful": successful,
            "failed": failed,
            "errors": errors[:10] if errors else []
        }

    except Exception as e:
        logger.error(f"[Medicine] Hospital upload failed: {e}")
        raise


# ============================================================================
# CRUD - Doctor Medicines
# ============================================================================

def create_doctor_medicine(
    doctor_id: uuid.UUID,
    medicine_name: str,
    common_names: Optional[List[str]] = None,
    category: Optional[str] = None,
    typical_dosage: Optional[str] = None,
    form: Optional[str] = None,
    snomed_code: Optional[str] = None,
    formulary_name: Optional[str] = None,
    medicine_type: Optional[str] = None,
    external_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create a single medicine for a doctor."""
    # Initialize common_names list
    if common_names is None:
        common_names = []
    else:
        common_names = list(common_names)  # Make a copy to avoid mutating the original

    # Auto-generate aliases from medicine name (augment existing common_names)
    auto_aliases = extract_medicine_aliases(medicine_name, common_names)
    for alias in auto_aliases:
        if alias.lower() not in {cn.lower() for cn in common_names}:
            common_names.append(alias)

    # Also extract abbreviations from formulary_name (generic name) if provided
    if formulary_name:
        formulary_aliases = extract_medicine_aliases(formulary_name, common_names)
        for alias in formulary_aliases:
            if alias.lower() not in {cn.lower() for cn in common_names}:
                common_names.append(alias)

    normalized = normalize_medicine_name(medicine_name)
    tokens = generate_search_tokens(medicine_name, common_names)

    # Enrich missing fields from hospital list
    enrichable_fields_missing = (
        not external_id or not formulary_name or not category
        or not typical_dosage or not form or not snomed_code or not medicine_type
    )
    if enrichable_fields_missing:
        try:
            from services.supabase_service import get_doctor_hospital_id_cached
            hospital_id = get_doctor_hospital_id_cached(doctor_id)
            if hospital_id:
                hospital_match = supabase.table('hospital_medicine_lists')\
                    .select('external_id, formulary_name, category, typical_dosage, form, snomed_code, medicine_type, common_names')\
                    .eq('hospital_id', hospital_id)\
                    .eq('normalized_name', normalized)\
                    .eq('is_active', True)\
                    .limit(1)\
                    .execute()
                if hospital_match.data:
                    hm = hospital_match.data[0]
                    if not external_id:
                        external_id = hm.get('external_id')
                    if not formulary_name:
                        formulary_name = hm.get('formulary_name')
                    if not category:
                        category = hm.get('category')
                    if not typical_dosage:
                        typical_dosage = hm.get('typical_dosage')
                    if not form:
                        form = hm.get('form')
                    if not snomed_code:
                        snomed_code = hm.get('snomed_code')
                    if not medicine_type:
                        medicine_type = hm.get('medicine_type')
                    # Merge common_names (don't replace)
                    hospital_common = hm.get('common_names') or []
                    if hospital_common:
                        existing_lower = {n.lower() for n in common_names}
                        for name in hospital_common:
                            if name.lower() not in existing_lower:
                                common_names.append(name)
                    logger.debug(f"[Medicine] Enriched '{medicine_name}' from hospital list: external_id={external_id}")
        except Exception as e:
            logger.warning(f"[Medicine] Hospital enrichment failed for '{medicine_name}': {e}")

    # Regenerate tokens after potential common_names enrichment
    tokens = generate_search_tokens(medicine_name, common_names)

    result = supabase.table('doctor_medicines').insert({
        'doctor_id': str(doctor_id),
        'medicine_name': medicine_name,
        'common_names': common_names,
        'category': category,
        'typical_dosage': typical_dosage,
        'form': form,
        'snomed_code': snomed_code,
        'formulary_name': formulary_name,
        'medicine_type': medicine_type,
        'external_id': external_id,
        'normalized_name': normalized,
        'search_tokens': tokens
    }).execute()

    # Invalidate list availability cache for this doctor
    from services.extraction_service import invalidate_list_cache
    invalidate_list_cache(doctor_id)

    # Invalidate medicine list data cache
    invalidate_doctor_medicine_cache(doctor_id)

    return result.data[0] if result.data else {}


def update_doctor_medicine(medicine_id: uuid.UUID, **kwargs) -> Dict[str, Any]:
    """Update a doctor's medicine."""
    update_data = {k: v for k, v in kwargs.items() if v is not None}

    # Regenerate normalized name and tokens if medicine_name or common_names changed
    if 'medicine_name' in update_data:
        update_data['normalized_name'] = normalize_medicine_name(update_data['medicine_name'])
        update_data['search_tokens'] = generate_search_tokens(
            update_data['medicine_name'],
            update_data.get('common_names')
        )
    elif 'common_names' in update_data:
        # Get current medicine_name
        current = supabase.table('doctor_medicines').select('medicine_name').eq(
            'id', str(medicine_id)
        ).single().execute()
        if current.data:
            update_data['search_tokens'] = generate_search_tokens(
                current.data['medicine_name'],
                update_data['common_names']
            )

    result = supabase.table('doctor_medicines').update(
        update_data
    ).eq('id', str(medicine_id)).execute()

    # Invalidate list availability cache for this doctor
    if result.data and result.data[0].get('doctor_id'):
        from services.extraction_service import invalidate_list_cache
        doctor_uuid = uuid.UUID(result.data[0]['doctor_id'])
        invalidate_list_cache(doctor_uuid)
        # Invalidate medicine list data cache
        invalidate_doctor_medicine_cache(doctor_uuid)

    return result.data[0] if result.data else {}


def delete_doctor_medicine(medicine_id: uuid.UUID) -> bool:
    """Soft delete a doctor's medicine."""
    try:
        # Get doctor_id before deleting for cache invalidation
        medicine = supabase.table('doctor_medicines').select('doctor_id').eq(
            'id', str(medicine_id)
        ).single().execute()
        doctor_id = medicine.data.get('doctor_id') if medicine.data else None

        supabase.table('doctor_medicines').update({
            'is_active': False
        }).eq('id', str(medicine_id)).execute()

        # Invalidate list availability cache for this doctor
        if doctor_id:
            from services.extraction_service import invalidate_list_cache
            doctor_uuid = uuid.UUID(doctor_id)
            invalidate_list_cache(doctor_uuid)
            # Invalidate medicine list data cache
            invalidate_doctor_medicine_cache(doctor_uuid)

        return True
    except Exception:
        return False


def has_medicine_lists(doctor_id: uuid.UUID) -> Dict[str, Any]:
    """
    Check if doctor or doctor's hospital has any medicine lists.
    Uses COUNT query for efficiency - doesn't fetch actual data.

    Args:
        doctor_id: Doctor ID to check

    Returns:
        Dict with keys: has_doctor_list, has_hospital_list, has_any_list, hospital_id
    """
    try:
        # Get doctor's hospital_id (cached - 10 min TTL)
        from services.supabase_service import get_doctor_hospital_id_cached
        hospital_id = get_doctor_hospital_id_cached(doctor_id)

        # Check doctor's list (count only, no data fetch)
        doctor_result = supabase.table('doctor_medicines').select(
            'id', count='exact', head=True
        ).eq('doctor_id', str(doctor_id)).eq('is_active', True).limit(1).execute()
        has_doctor_list = (doctor_result.count or 0) > 0

        # Check hospital's list
        has_hospital_list = False
        if hospital_id:
            hospital_result = supabase.table('hospital_medicine_lists').select(
                'id', count='exact', head=True
            ).eq('hospital_id', str(hospital_id)).eq('is_active', True).limit(1).execute()
            has_hospital_list = (hospital_result.count or 0) > 0

        result = {
            "has_doctor_list": has_doctor_list,
            "has_hospital_list": has_hospital_list,
            "has_any_list": has_doctor_list or has_hospital_list,
            "hospital_id": hospital_id
        }

        logger.debug(f"[Medicine] has_medicine_lists for doctor {doctor_id}: {result}")
        return result

    except Exception as e:
        logger.error(f"[Medicine] Error checking medicine lists for doctor {doctor_id}: {e}")
        # Return True by default to avoid skipping lists on error
        return {
            "has_doctor_list": True,
            "has_hospital_list": True,
            "has_any_list": True,
            "hospital_id": None
        }


def list_doctor_medicines(
    doctor_id: uuid.UUID,
    category: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List all medicines for a doctor.

    Uses in-memory cache (8-hour TTL) when no search filter is applied.
    Cache is invalidated when medicines are added/updated/deleted.
    """
    # Only use cache when no search filter (search results aren't cached)
    if not search:
        cached = get_cached_doctor_medicines(doctor_id, category)
        if cached is not None:
            return cached

    # Cache miss or search query - fetch from DB with pagination safety net
    # PostgREST max_rows may truncate large lists; paginate to get all rows
    PAGE_SIZE = 1000
    medicines = []
    offset = 0
    while True:
        query = supabase.table('doctor_medicines').select('*').eq(
            'doctor_id', str(doctor_id)
        ).eq('is_active', True)
        if category:
            query = query.eq('category', category)
        result = query.order('medicine_name').range(offset, offset + PAGE_SIZE - 1).execute()
        page = result.data or []
        medicines.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    if offset > 0:
        logger.info(f"[MEDICINE_LIST] Paginated fetch for doctor {str(doctor_id)[:8]}...: {len(medicines)} total medicines across {offset // PAGE_SIZE + 1} pages")

    # Cache the result if no search filter
    if not search:
        set_cached_doctor_medicines(doctor_id, medicines, category)

    # Client-side search if needed
    if search:
        search_lower = search.lower()
        medicines = [
            m for m in medicines
            if search_lower in m['medicine_name'].lower()
            or search_lower in m['normalized_name']
            or any(search_lower in cn.lower() for cn in (m['common_names'] or []))
        ]

    return medicines


def copy_hospital_medicine_to_doctor(
    hospital_medicine_id: uuid.UUID,
    doctor_id: uuid.UUID
) -> Optional[Dict[str, Any]]:
    """Copy a hospital medicine to doctor's personal list."""
    try:
        # Use RPC if available
        result = supabase.rpc(
            'copy_hospital_medicine_to_doctor_rpc',
            {
                'p_hospital_medicine_id': str(hospital_medicine_id),
                'p_doctor_id': str(doctor_id)
            }
        ).execute()

        if result.data:
            return {"id": result.data, "message": "Copied successfully"}
        return None

    except Exception as e:
        logger.warning(f"[Medicine] RPC copy failed, using fallback: {e}")

        # Fallback to manual copy
        hospital_med = supabase.table('hospital_medicine_lists').select(
            '*'
        ).eq('id', str(hospital_medicine_id)).single().execute()

        if not hospital_med.data:
            return None

        hm = hospital_med.data
        return create_doctor_medicine(
            doctor_id=doctor_id,
            medicine_name=hm['medicine_name'],
            common_names=hm['common_names'],
            category=hm['category'],
            typical_dosage=hm['typical_dosage'],
            form=hm['form'],
            snomed_code=hm['snomed_code'],
            formulary_name=hm['formulary_name'],
            medicine_type=hm['medicine_type'],
            external_id=hm.get('external_id')
        )


# ============================================================================
# CRUD - Hospital Medicines
# ============================================================================

def create_hospital_medicine(hospital_id: uuid.UUID, created_by: uuid.UUID, **kwargs) -> Dict[str, Any]:
    """Create a single medicine for a hospital."""
    medicine_name = kwargs.get('medicine_name', '')
    common_names = list(kwargs.get('common_names', []))  # Make a copy to avoid mutating

    # Auto-generate aliases from medicine name (augment existing common_names)
    auto_aliases = extract_medicine_aliases(medicine_name, common_names)
    for alias in auto_aliases:
        if alias.lower() not in {cn.lower() for cn in common_names}:
            common_names.append(alias)

    # Also extract abbreviations from formulary_name (generic name) if provided
    formulary_name = kwargs.get('formulary_name')
    if formulary_name:
        formulary_aliases = extract_medicine_aliases(formulary_name, common_names)
        for alias in formulary_aliases:
            if alias.lower() not in {cn.lower() for cn in common_names}:
                common_names.append(alias)

    normalized = normalize_medicine_name(medicine_name)
    tokens = generate_search_tokens(medicine_name, common_names)

    data = {
        'hospital_id': str(hospital_id),
        'created_by': str(created_by),
        'medicine_name': medicine_name,
        'common_names': common_names,
        'category': kwargs.get('category'),
        'typical_dosage': kwargs.get('typical_dosage'),
        'form': kwargs.get('form'),
        'snomed_code': kwargs.get('snomed_code'),
        'formulary_name': kwargs.get('formulary_name'),
        'medicine_type': kwargs.get('medicine_type'),
        'normalized_name': normalized,
        'search_tokens': tokens
    }

    result = supabase.table('hospital_medicine_lists').insert(data).execute()

    # Invalidate list availability cache for all doctors (hospital-level change)
    from services.extraction_service import invalidate_list_cache_by_hospital
    invalidate_list_cache_by_hospital(hospital_id)

    # Invalidate hospital medicine list data cache
    invalidate_hospital_medicine_cache(hospital_id)

    return result.data[0] if result.data else {}


def list_hospital_medicines(
    hospital_id: uuid.UUID,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List all medicines for a hospital.

    Uses in-memory cache (8-hour TTL) for faster repeated access.
    Cache is invalidated when hospital medicines are added/updated/deleted.
    """
    # Check cache first
    cached = get_cached_hospital_medicines(hospital_id, category)
    if cached is not None:
        return cached

    # Cache miss - fetch from DB with pagination safety net
    PAGE_SIZE = 1000
    medicines = []
    offset = 0
    while True:
        query = supabase.table('hospital_medicine_lists').select('*').eq(
            'hospital_id', str(hospital_id)
        ).eq('is_active', True)
        if category:
            query = query.eq('category', category)
        result = query.order('medicine_name').range(offset, offset + PAGE_SIZE - 1).execute()
        page = result.data or []
        medicines.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    if offset > 0:
        logger.info(f"[MEDICINE_LIST] Paginated fetch for hospital {str(hospital_id)[:8]}...: {len(medicines)} total medicines across {offset // PAGE_SIZE + 1} pages")

    # Cache the result
    set_cached_hospital_medicines(hospital_id, medicines, category)

    return medicines


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


def _check_diagnosis_context_match(category: Optional[str], diagnosis: str) -> bool:
    """Check if medicine category matches diagnosis context."""
    if not category or not diagnosis:
        return False

    category_lower = category.lower()
    diagnosis_lower = diagnosis.lower()

    # Check direct category match
    if category_lower in CATEGORY_DIAGNOSIS_MAP:
        keywords = CATEGORY_DIAGNOSIS_MAP[category_lower]
        return any(kw in diagnosis_lower for kw in keywords)

    # Check if category name appears in diagnosis
    return category_lower in diagnosis_lower


async def get_doctor_feedback_for_medicine(
    doctor_id: uuid.UUID,
    original_name: str
) -> Optional[Dict[str, Any]]:
    """
    Check if doctor has previous feedback for this medicine name.

    Returns the most recent feedback record if found.
    """
    try:
        result = supabase.rpc(
            'get_medicine_feedback_history_rpc',
            {
                'p_doctor_id': str(doctor_id),
                'p_original_name': original_name
            }
        ).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception as e:
        logger.warning(f"[Medicine] Feedback lookup failed: {e}")

        # Fallback to direct query
        result = supabase.table('medicine_match_log').select(
            'matched_medicine_name, correct_medicine_name, feedback_status, match_confidence'
        ).eq('doctor_id', str(doctor_id)).ilike(
            'original_medicine_name', original_name
        ).not_.is_('feedback_status', 'null').order(
            'created_at', desc=True
        ).limit(1).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None


async def match_medicine_name(
    extracted_name: str,
    doctor_id: uuid.UUID,
    diagnosis: str = "",
    submission_id: str = "",
    threshold: float = MIN_FUZZY_THRESHOLD
) -> Dict[str, Any]:
    """
    Match extracted medicine name using improved matching algorithm.

    Since Gemini already has the medicine list via prompt injection, post-processing
    should prioritize exact/common_name matches and only use fuzzy for typo correction.

    Matching Priority (Exact/Common first in BOTH lists, then Fuzzy):
    1. Feedback history (agreed/disagreed) → 95% confidence
    2. Doctor list - exact match → 100% confidence
    3. Doctor list - common name match → 98% confidence
    4. Hospital list - exact match → 90% confidence
    5. Hospital list - common name match → 88% confidence
    6. Doctor list - fuzzy match (90%+ only) → typo correction
    7. Hospital list - fuzzy match (90%+ only) → typo correction

    Args:
        extracted_name: Name extracted from transcript
        doctor_id: Doctor ID
        diagnosis: Diagnosis context for confidence boost
        submission_id: Submission ID for logging
        threshold: Minimum confidence threshold (default 0.90 for typo-only correction)

    Returns:
        Dict with: matched, original_name, matched_name, confidence, method, source, formulary_name
    """
    import time as time_module
    match_start = time_module.time()

    normalized_extracted = normalize_medicine_name(extracted_name)
    logger.info(f"[Medicine Match] Processing: '{extracted_name}' (normalized: '{normalized_extracted}')")

    # Level 1: Check feedback history (highest priority - doctor's explicit preference)
    feedback_start = time_module.time()
    feedback = await get_doctor_feedback_for_medicine(doctor_id, extracted_name)
    feedback_duration = time_module.time() - feedback_start
    if feedback:
        if feedback['feedback_status'] == 'agreed':
            total_duration = time_module.time() - match_start
            logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': feedback_lookup={feedback_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (FEEDBACK_AGREED)")
            logger.info(f"[Medicine Match] ✓ FEEDBACK_AGREED: '{extracted_name}' → '{feedback['matched_medicine_name']}' (from previous feedback)")
            return {
                "matched": True,
                "original_name": extracted_name,
                "matched_name": feedback['matched_medicine_name'],
                "confidence": 0.95,
                "method": "feedback_agreed",
                "source": "feedback_history",
                "formulary_name": None,  # Not available from feedback history
                "form": None
            }
        elif feedback['feedback_status'] == 'disagreed' and feedback['correct_medicine_name']:
            total_duration = time_module.time() - match_start
            logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': feedback_lookup={feedback_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (FEEDBACK_CORRECTED)")
            logger.info(f"[Medicine Match] ✓ FEEDBACK_CORRECTED: '{extracted_name}' → '{feedback['correct_medicine_name']}' (doctor correction)")
            return {
                "matched": True,
                "original_name": extracted_name,
                "matched_name": feedback['correct_medicine_name'],
                "confidence": 0.95,
                "method": "feedback_corrected",
                "source": "feedback_history",
                "formulary_name": None,  # Not available from feedback history
                "form": None
            }

    # Get doctor's hospital_id for hospital list lookup (cached - 10 min TTL)
    from services.supabase_service import get_doctor_hospital_id_cached
    hospital_id = get_doctor_hospital_id_cached(doctor_id)

    # Load both lists upfront
    list_load_start = time_module.time()
    doctor_meds = list_doctor_medicines(doctor_id)
    hospital_meds = list_hospital_medicines(uuid.UUID(hospital_id)) if hospital_id else []
    list_load_duration = time_module.time() - list_load_start

    # Build hospital external_id lookup by normalized name for fallback enrichment
    # When a medicine matches on doctor_list (which may lack external_id),
    # we fall back to the hospital list to get external_id for billing
    _hospital_ext_id_lookup = {}
    for hmed in hospital_meds:
        if hmed.get('external_id'):
            _hospital_ext_id_lookup[hmed['normalized_name']] = hmed['external_id']

    def _enrich_external_id(result: Dict[str, Any]) -> Dict[str, Any]:
        """If doctor_list match has no external_id, try hospital list by normalized name."""
        if result.get('source') == 'doctor_list' and not result.get('external_id'):
            matched_normalized = normalize_medicine_name(result['matched_name'])
            hospital_ext_id = _hospital_ext_id_lookup.get(matched_normalized)
            if hospital_ext_id:
                result['external_id'] = hospital_ext_id
        return result

    # =========================================================================
    # PHASE 1: Exact and Common Name matches (check BOTH lists before fuzzy)
    # =========================================================================
    exact_match_start = time_module.time()

    # Level 2: Exact match in doctor's list
    for med in doctor_meds:
        if med['normalized_name'] == normalized_extracted:
            confidence = 1.0
            if _check_diagnosis_context_match(med.get('category'), diagnosis):
                confidence = min(1.0, confidence + DIAGNOSIS_CONTEXT_BOOST)

            exact_match_duration = time_module.time() - exact_match_start
            total_duration = time_module.time() - match_start
            logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (EXACT_DOCTOR)")
            logger.info(f"[Medicine Match] ✓ EXACT_DOCTOR: '{extracted_name}' → '{med['medicine_name']}' (100% confidence)")
            return _enrich_external_id({
                "matched": True,
                "original_name": extracted_name,
                "matched_name": med['medicine_name'],
                "matched_medicine_id": med['id'],
                "confidence": confidence,
                "method": "exact",
                "source": "doctor_list",
                "category": med.get('category'),
                "formulary_name": med.get('formulary_name'),
                "external_id": med.get('external_id'),
                "form": med.get('form'),
                "product_code": med.get('product_code')
            })

    # Level 3: Common name match in doctor's list
    for med in doctor_meds:
        for common in (med.get('common_names') or []):
            if normalize_medicine_name(common) == normalized_extracted:
                confidence = 0.98
                if _check_diagnosis_context_match(med.get('category'), diagnosis):
                    confidence = min(1.0, confidence + DIAGNOSIS_CONTEXT_BOOST)

                exact_match_duration = time_module.time() - exact_match_start
                total_duration = time_module.time() - match_start
                logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (COMMON_NAME_DOCTOR)")
                logger.info(f"[Medicine Match] ✓ COMMON_NAME_DOCTOR: '{extracted_name}' → '{med['medicine_name']}' (matched via common name '{common}')")
                return _enrich_external_id({
                    "matched": True,
                    "original_name": extracted_name,
                    "matched_name": med['medicine_name'],
                    "matched_medicine_id": med['id'],
                    "confidence": confidence,
                    "method": "common_name",
                    "source": "doctor_list",
                    "category": med.get('category'),
                    "formulary_name": med.get('formulary_name'),
                    "external_id": med.get('external_id'),
                    "form": med.get('form')
                })

    # Level 4: Exact match in hospital list
    for med in hospital_meds:
        if med['normalized_name'] == normalized_extracted:
            confidence = 0.90
            if _check_diagnosis_context_match(med.get('category'), diagnosis):
                confidence = min(1.0, confidence + DIAGNOSIS_CONTEXT_BOOST)

            exact_match_duration = time_module.time() - exact_match_start
            total_duration = time_module.time() - match_start
            logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (EXACT_HOSPITAL)")
            logger.info(f"[Medicine Match] ✓ EXACT_HOSPITAL: '{extracted_name}' → '{med['medicine_name']}' (90% confidence)")
            return {
                "matched": True,
                "original_name": extracted_name,
                "matched_name": med['medicine_name'],
                "matched_hospital_medicine_id": med['id'],
                "confidence": confidence,
                "method": "exact",
                "source": "hospital_list",
                "category": med.get('category'),
                "formulary_name": med.get('formulary_name'),
                "external_id": med.get('external_id'),
                "form": med.get('form'),
                "product_code": med.get('product_code')
            }

    # Level 5: Common name match in hospital list
    for med in hospital_meds:
        for common in (med.get('common_names') or []):
            if normalize_medicine_name(common) == normalized_extracted:
                confidence = 0.88
                if _check_diagnosis_context_match(med.get('category'), diagnosis):
                    confidence = min(0.98, confidence + DIAGNOSIS_CONTEXT_BOOST)

                exact_match_duration = time_module.time() - exact_match_start
                total_duration = time_module.time() - match_start
                logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact_match={exact_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (COMMON_NAME_HOSPITAL)")
                logger.info(f"[Medicine Match] ✓ COMMON_NAME_HOSPITAL: '{extracted_name}' → '{med['medicine_name']}' (matched via common name '{common}')")
                return {
                    "matched": True,
                    "original_name": extracted_name,
                    "matched_name": med['medicine_name'],
                    "matched_hospital_medicine_id": med['id'],
                    "confidence": confidence,
                    "method": "common_name",
                    "source": "hospital_list",
                    "category": med.get('category'),
                    "formulary_name": med.get('formulary_name'),
                    "external_id": med.get('external_id'),
                    "form": med.get('form')
                }

    exact_match_duration = time_module.time() - exact_match_start

    # =========================================================================
    # PHASE 2: Prefix/Substring match (handles Gemini truncating names)
    # Example: Gemini outputs "T - CALPOL 650MG TAB" but DB has "T - CALPOL 650MG TAB  Kg TABLET"
    # If extracted name is a significant prefix (>= 60%) of a medicine name, match it
    # =========================================================================
    prefix_match_start = time_module.time()
    logger.info(f"[Medicine Match] No exact/common_name match, trying prefix match (coverage: {PREFIX_MATCH_COVERAGE*100:.0f}%)...")

    # Check if extracted name is a prefix of any medicine in doctor's list
    for med in doctor_meds:
        med_normalized = med['normalized_name']
        # Check if extracted is a prefix of the medicine name
        if med_normalized.startswith(normalized_extracted) and len(normalized_extracted) > 3:
            coverage = len(normalized_extracted) / len(med_normalized)
            if coverage >= PREFIX_MATCH_COVERAGE:
                confidence = 0.95  # High confidence for prefix match
                if _check_diagnosis_context_match(med.get('category'), diagnosis):
                    confidence = min(0.99, confidence + DIAGNOSIS_CONTEXT_BOOST)

                prefix_match_duration = time_module.time() - prefix_match_start
                total_duration = time_module.time() - match_start
                logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact={exact_match_duration*1000:.1f}ms, prefix={prefix_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (PREFIX_DOCTOR)")
                logger.info(f"[Medicine Match] ✓ PREFIX_DOCTOR: '{extracted_name}' → '{med['medicine_name']}' (coverage: {coverage*100:.1f}%)")
                return _enrich_external_id({
                    "matched": True,
                    "original_name": extracted_name,
                    "matched_name": med['medicine_name'],
                    "matched_medicine_id": med['id'],
                    "confidence": confidence,
                    "method": "prefix",
                    "source": "doctor_list",
                    "category": med.get('category'),
                    "formulary_name": med.get('formulary_name'),
                    "external_id": med.get('external_id'),
                    "form": med.get('form')
                })

    # Check if extracted name is a prefix of any medicine in hospital's list
    for med in hospital_meds:
        med_normalized = med['normalized_name']
        # Check if extracted is a prefix of the medicine name
        if med_normalized.startswith(normalized_extracted) and len(normalized_extracted) > 3:
            coverage = len(normalized_extracted) / len(med_normalized)
            if coverage >= PREFIX_MATCH_COVERAGE:
                confidence = 0.92  # Slightly lower for hospital list
                if _check_diagnosis_context_match(med.get('category'), diagnosis):
                    confidence = min(0.97, confidence + DIAGNOSIS_CONTEXT_BOOST)

                prefix_match_duration = time_module.time() - prefix_match_start
                total_duration = time_module.time() - match_start
                logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact={exact_match_duration*1000:.1f}ms, prefix={prefix_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (PREFIX_HOSPITAL)")
                logger.info(f"[Medicine Match] ✓ PREFIX_HOSPITAL: '{extracted_name}' → '{med['medicine_name']}' (coverage: {coverage*100:.1f}%)")
                return {
                    "matched": True,
                    "original_name": extracted_name,
                    "matched_name": med['medicine_name'],
                    "matched_hospital_medicine_id": med['id'],
                    "confidence": confidence,
                    "method": "prefix",
                    "source": "hospital_list",
                    "category": med.get('category'),
                    "formulary_name": med.get('formulary_name'),
                    "external_id": med.get('external_id'),
                    "form": med.get('form')
                }

    prefix_match_duration = time_module.time() - prefix_match_start

    # =========================================================================
    # PHASE 3: Fuzzy matches (for typo/transcription correction - 80%+ threshold)
    # Only reach here if Gemini's extraction didn't match any exact/common/prefix
    # =========================================================================
    fuzzy_match_start = time_module.time()
    logger.info(f"[Medicine Match] No exact/common_name/prefix match found, trying fuzzy (threshold: {threshold*100:.0f}%)...")

    # Level 6: Fuzzy match in doctor's list
    best_doctor_match = None
    best_doctor_score = 0

    for med in doctor_meds:
        score = _calculate_fuzzy_score(normalized_extracted, med['normalized_name'])
        if score > best_doctor_score and score >= threshold:
            best_doctor_score = score
            best_doctor_match = med

        # Also check common names for fuzzy
        for common in (med.get('common_names') or []):
            common_score = _calculate_fuzzy_score(normalized_extracted, normalize_medicine_name(common))
            if common_score > best_doctor_score and common_score >= threshold:
                best_doctor_score = common_score
                best_doctor_match = med

    # Level 7: Fuzzy match in hospital list
    best_hospital_match = None
    best_hospital_score = 0

    for med in hospital_meds:
        score = _calculate_fuzzy_score(normalized_extracted, med['normalized_name'])
        if score > best_hospital_score and score >= threshold:
            best_hospital_score = score
            best_hospital_match = med

        # Also check common names for fuzzy
        for common in (med.get('common_names') or []):
            common_score = _calculate_fuzzy_score(normalized_extracted, normalize_medicine_name(common))
            if common_score > best_hospital_score and common_score >= threshold:
                best_hospital_score = common_score
                best_hospital_match = med

    fuzzy_match_duration = time_module.time() - fuzzy_match_start

    # Return best fuzzy match (prefer doctor list if scores are equal)
    if best_doctor_match and best_doctor_score >= best_hospital_score:
        confidence = best_doctor_score * 0.95  # Scale to 85-95% range
        if _check_diagnosis_context_match(best_doctor_match.get('category'), diagnosis):
            confidence = min(0.99, confidence + DIAGNOSIS_CONTEXT_BOOST)

        total_duration = time_module.time() - match_start
        logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact={exact_match_duration*1000:.1f}ms, fuzzy={fuzzy_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (FUZZY_DOCTOR)")
        logger.info(f"[Medicine Match] ✓ FUZZY_DOCTOR: '{extracted_name}' → '{best_doctor_match['medicine_name']}' (score: {best_doctor_score*100:.1f}%)")
        return _enrich_external_id({
            "matched": True,
            "original_name": extracted_name,
            "matched_name": best_doctor_match['medicine_name'],
            "matched_medicine_id": best_doctor_match['id'],
            "confidence": confidence,
            "method": "fuzzy",
            "source": "doctor_list",
            "category": best_doctor_match.get('category'),
            "formulary_name": best_doctor_match.get('formulary_name'),
            "external_id": best_doctor_match.get('external_id'),
            "form": best_doctor_match.get('form')
        })

    if best_hospital_match:
        confidence = best_hospital_score * 0.90  # Scale to 81-90% range
        if _check_diagnosis_context_match(best_hospital_match.get('category'), diagnosis):
            confidence = min(0.95, confidence + DIAGNOSIS_CONTEXT_BOOST)

        total_duration = time_module.time() - match_start
        logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact={exact_match_duration*1000:.1f}ms, fuzzy={fuzzy_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (FUZZY_HOSPITAL)")
        logger.info(f"[Medicine Match] ✓ FUZZY_HOSPITAL: '{extracted_name}' → '{best_hospital_match['medicine_name']}' (score: {best_hospital_score*100:.1f}%)")
        return {
            "matched": True,
            "original_name": extracted_name,
            "matched_name": best_hospital_match['medicine_name'],
            "matched_hospital_medicine_id": best_hospital_match['id'],
            "confidence": confidence,
            "method": "fuzzy",
            "source": "hospital_list",
            "category": best_hospital_match.get('category'),
            "formulary_name": best_hospital_match.get('formulary_name'),
            "external_id": best_hospital_match.get('external_id'),
            "form": best_hospital_match.get('form')
        }

    # No match found - trust Gemini's extraction
    total_duration = time_module.time() - match_start
    logger.info(f"[TIMING_MEDICINE_MATCH] '{extracted_name}': list_load={list_load_duration*1000:.1f}ms, exact={exact_match_duration*1000:.1f}ms, fuzzy={fuzzy_match_duration*1000:.1f}ms, total={total_duration*1000:.1f}ms (NO_MATCH)")
    logger.info(f"[Medicine Match] ✗ NO_MATCH: '{extracted_name}' - keeping Gemini's original extraction")
    return {
        "matched": False,
        "original_name": extracted_name,
        "matched_name": extracted_name,  # Keep original
        "confidence": 0.0,
        "method": "no_match",
        "source": None,
        "formulary_name": None,
        "external_id": None,
        "form": None
    }


# ============================================================================
# Post-Processing
# ============================================================================

async def postprocess_prescription_extraction(
    extraction_data: Dict[str, Any],
    doctor_id: uuid.UUID,
    extraction_id: uuid.UUID,
    submission_id: str,
    diagnosis: str = "",
    template_id: Optional[uuid.UUID] = None,
    log_matches: bool = True
) -> Dict[str, Any]:
    """
    Match all medicines in extraction and return updated extraction.

    MUST complete before webhook/UI display.

    Args:
        extraction_data: Full extraction result
        doctor_id: Doctor ID
        extraction_id: Extraction record ID
        submission_id: Submission ID for ground truth
        diagnosis: Diagnosis context
        template_id: Template ID for adaptive learning
        log_matches: Whether to log matches

    Returns:
        Updated extraction data with matched medicines
    """
    # Find prescription data - check common field names
    prescription_fields = ['prescription', 'medications', 'drugs', 'prescribedMedicines']
    prescription_data = None
    prescription_key = None

    for key in prescription_fields:
        if key in extraction_data:
            prescription_data = extraction_data[key]
            prescription_key = key
            break

    if not prescription_data:
        logger.debug(f"[Medicine] No prescription data found in extraction")
        return extraction_data

    # Handle both list and dict formats (supports flat and nested structures)
    def extract_meds_list(data: Any) -> list:
        """Extract medication list from various data structures."""
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Check for nested keys: 'prescription', 'medications', 'drugs', 'items'
            for nested_key in ['prescription', 'medications', 'drugs', 'items']:
                if nested_key in data:
                    nested_data = data[nested_key]
                    if isinstance(nested_data, list):
                        return nested_data
            # Single medication object
            return [data]
        return []

    medications = extract_meds_list(prescription_data)

    if not medications:
        return extraction_data

    # Log what Gemini originally extracted
    gemini_medicines = []
    for m in medications:
        if isinstance(m, dict):
            for key in ['name', 'medicine_name', 'drugName', 'medication']:
                if key in m and m[key]:
                    gemini_medicines.append(m[key])
                    break
    logger.debug(f"[Medicine Post-Process] AI extracted {len(gemini_medicines)} medicines: {gemini_medicines}")

    # Match each medication
    for med in medications:
        if not isinstance(med, dict):
            continue

        # Find medicine name field
        name_fields = ['name', 'medicine_name', 'drugName', 'medication']
        original_name = None
        name_key = None

        for key in name_fields:
            if key in med and med[key]:
                original_name = med[key]
                name_key = key
                break

        if not original_name:
            continue

        # Strip [Form] tag if Gemini accidentally included it in output
        # e.g., "DOLO 650 [Tablet]" → "DOLO 650"
        form_tag_match = re.search(r'\s*\[(Tablet|Capsule|Syrup|Injection|Drops|Cream|Ointment|Inhaler|Patch|Suppository|Powder|Vaccine|Penfill|Spray|Oil|Soap)\]\s*$', original_name, re.IGNORECASE)
        if form_tag_match:
            original_name = original_name[:form_tag_match.start()].strip()
            med[name_key] = original_name

        # Match medicine
        match_result = await match_medicine_name(
            extracted_name=original_name,
            doctor_id=doctor_id,
            diagnosis=diagnosis,
            submission_id=submission_id
        )

        # --- Form Guard: detect mismatches between spoken form and matched form ---
        if match_result['matched'] and match_result.get('form'):
            matched_form = match_result['form'].lower()

            # Priority 1: dosage_form from extraction (what doctor SAID)
            # Priority 2: detect form from original_name (only useful if Gemini output differs from list)
            extracted_dosage_form = (med.get('dosage_form') or med.get('drug_type') or '').strip().lower()
            name_detected_form = (detect_medicine_form(original_name) or '').lower()

            # Use dosage_form (ground truth) if available, else fall back to name detection
            spoken_form = extracted_dosage_form or name_detected_form

            if spoken_form and matched_form and _is_form_mismatch(spoken_form, matched_form):
                logger.warning(
                    f"[Medicine Form Guard] MISMATCH: '{original_name}' "
                    f"(spoken_form={spoken_form}) matched to '{match_result['matched_name']}' "
                    f"(matched_form={matched_form}) — reverting to original name"
                )
                # Revert: don't apply this match
                match_result = {
                    "matched": False,
                    "matched_name": original_name,
                    "confidence": 0.0,
                    "method": "form_mismatch_reverted",
                    "source": None,
                    "formulary_name": None,
                    "external_id": None,
                    "form": None
                }

        # Update medicine name if matched (name was corrected)
        if match_result['matched'] and match_result['matched_name'] != original_name:
            med[name_key] = match_result['matched_name']

        # Include formulary name if available from the matched medicine (even for exact matches)
        if match_result['matched'] and match_result.get('formulary_name'):
            med['_formulary_name'] = match_result['formulary_name']

        # Include external_id if available from the matched medicine
        if match_result['matched'] and match_result.get('external_id'):
            med['_external_id'] = match_result['external_id']

        # Include form if available from the matched medicine (used by AOSTA for drug_type detection)
        if match_result['matched'] and match_result.get('form'):
            med['_form'] = match_result['form']

        # Include product_code if available (used by Raster New OP for productCode field)
        if match_result['matched'] and match_result.get('product_code'):
            med['_product_code'] = match_result['product_code']

        # Log match if requested
        if log_matches:
            try:
                # Separate IDs for doctor_list vs hospital_list matches (different FK constraints)
                matched_doctor_med_id = None
                matched_hospital_med_id = None

                if match_result.get('source') == 'doctor_list':
                    matched_doctor_med_id = match_result.get('matched_medicine_id')
                elif match_result.get('source') == 'hospital_list':
                    matched_hospital_med_id = match_result.get('matched_hospital_medicine_id')

                supabase.table('medicine_match_log').insert({
                    'extraction_id': str(extraction_id),
                    'submission_id': submission_id,
                    'doctor_id': str(doctor_id),
                    'original_medicine_name': original_name,
                    'matched_medicine_id': matched_doctor_med_id,
                    'matched_hospital_medicine_id': matched_hospital_med_id,
                    'matched_medicine_name': match_result['matched_name'],
                    'match_confidence': match_result['confidence'],
                    'match_method': match_result['method'],
                    'match_source': match_result['source'],
                    'diagnosis_context': diagnosis[:500] if diagnosis else None
                }).execute()
            except Exception as e:
                logger.warning(f"[Medicine] Failed to log match: {e}")

        # Trigger adaptive learning if confidence exceeds threshold
        if template_id and match_result['confidence'] >= ADAPTIVE_LEARNING_THRESHOLD:
            try:
                await update_segment_definition_for_medicine_learning(
                    doctor_id=doctor_id,
                    template_id=template_id,
                    extracted_name=original_name,
                    matched_name=match_result['matched_name'],
                    diagnosis_context=diagnosis
                )
            except Exception as e:
                logger.warning(f"[Medicine] Adaptive learning failed: {e}")

    return extraction_data


# ============================================================================
# Adaptive Learning
# ============================================================================

async def update_segment_definition_for_medicine_learning(
    doctor_id: uuid.UUID,
    template_id: uuid.UUID,
    extracted_name: str,
    matched_name: str,
    diagnosis_context: str
) -> None:
    """
    Auto-update prescription segment definition with learned medicine mapping.

    This adds an instruction to the segment's prompt text to help future extractions.

    Args:
        doctor_id: Doctor ID
        template_id: Template ID
        extracted_name: What was extracted
        matched_name: What it was matched to
        diagnosis_context: Diagnosis for context
    """
    # This is a placeholder for future implementation
    # The actual implementation would update the segment_definitions table
    # to add learned mappings to the prompt text
    logger.debug(f"[Medicine] Adaptive learning: '{extracted_name}' -> '{matched_name}' for doctor {doctor_id}")

    # TODO: Implement segment definition update
    # This would involve:
    # 1. Finding the prescription segment for this template
    # 2. Adding a learned mapping instruction to the prompt
    # 3. Storing the mapping in a way that can be included in future prompts


# ============================================================================
# Feedback Functions
# ============================================================================

def submit_medicine_feedback(
    match_log_id: uuid.UUID,
    feedback_status: str,  # 'agreed' or 'disagreed'
    correct_medicine_id: Optional[uuid.UUID] = None,
    correct_medicine_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit feedback for a medicine match.

    If agreed + hospital source → Auto-copy to doctor's personal list.

    Args:
        match_log_id: Match log record ID
        feedback_status: 'agreed' or 'disagreed'
        correct_medicine_id: If disagreed, correct medicine ID
        correct_medicine_name: If disagreed, correct name (manual entry)

    Returns:
        Updated match log record
    """
    if feedback_status not in ('agreed', 'disagreed'):
        raise ValueError("feedback_status must be 'agreed' or 'disagreed'")

    # Get current match log
    match_log = supabase.table('medicine_match_log').select(
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
        if correct_medicine_id:
            update_data['correct_medicine_id'] = str(correct_medicine_id)
        if correct_medicine_name:
            update_data['correct_medicine_name'] = correct_medicine_name

    result = supabase.table('medicine_match_log').update(
        update_data
    ).eq('id', str(match_log_id)).execute()

    doctor_id = ml.get('doctor_id')

    # Auto-copy to personal list if agreed with hospital match
    if feedback_status == 'agreed' and ml.get('match_source') == 'hospital_list':
        if ml.get('matched_medicine_id') and doctor_id:
            try:
                copy_hospital_medicine_to_doctor(
                    hospital_medicine_id=uuid.UUID(ml['matched_medicine_id']),
                    doctor_id=uuid.UUID(doctor_id)
                )
                logger.debug(f"[Medicine] Auto-copied hospital medicine to doctor's list")
            except Exception as e:
                logger.warning(f"[Medicine] Auto-copy failed: {e}")

    # Auto-add to personal list if agreed with no_match (doctor confirms original name is correct)
    if feedback_status == 'agreed' and ml.get('match_method') == 'no_match' and doctor_id:
        original_name = ml.get('original_medicine_name', '')
        if original_name:
            try:
                # Check if already exists in doctor's list
                existing = supabase.table('doctor_medicines')\
                    .select('id')\
                    .eq('doctor_id', str(doctor_id))\
                    .eq('normalized_name', normalize_medicine_name(original_name))\
                    .limit(1)\
                    .execute()

                if not existing.data:
                    # Add original name to doctor's list
                    create_doctor_medicine(
                        doctor_id=uuid.UUID(doctor_id),
                        medicine_name=original_name,
                        common_names=[],
                        category='Added from Feedback'
                    )
                    logger.debug(f"[Medicine] Added '{original_name}' to doctor's list (from no_match feedback)")
            except Exception as e:
                logger.warning(f"[Medicine] Auto-add from no_match failed: {e}")

    # Auto-add correction to personal list if disagreed with correction provided
    if feedback_status == 'disagreed' and correct_medicine_name and doctor_id:
        try:
            # Check if already exists in doctor's list
            existing = supabase.table('doctor_medicines')\
                .select('id, common_names')\
                .eq('doctor_id', str(doctor_id))\
                .eq('normalized_name', normalize_medicine_name(correct_medicine_name))\
                .limit(1)\
                .execute()

            original_name = ml.get('original_medicine_name', '')

            if not existing.data:
                # Create new medicine entry with original name as common_name
                create_doctor_medicine(
                    doctor_id=uuid.UUID(doctor_id),
                    medicine_name=correct_medicine_name,
                    common_names=[original_name] if original_name else [],
                    category='Corrections'
                )
                logger.debug(f"[Medicine] Added correction '{correct_medicine_name}' to doctor's list")
            else:
                # Add original name as common_name if not already present
                existing_id = existing.data[0]['id']
                current_names = existing.data[0].get('common_names') or []
                if original_name and original_name.lower() not in [n.lower() for n in current_names]:
                    updated_names = current_names + [original_name]
                    supabase.table('doctor_medicines')\
                        .update({'common_names': updated_names})\
                        .eq('id', existing_id)\
                        .execute()
                    logger.debug(f"[Medicine] Added '{original_name}' as common name for '{correct_medicine_name}'")
        except Exception as e:
            logger.warning(f"[Medicine] Auto-add correction failed: {e}")

    logger.info(f"[Medicine] Feedback submitted: {feedback_status} for match {match_log_id}")
    return result.data[0] if result.data else {}


def list_pending_feedback(
    doctor_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
    include_exact_matches: bool = False
) -> List[Dict[str, Any]]:
    """
    Get match logs pending feedback for the dedicated review screen.

    By default, only returns matches that NEED doctor action:
    - 'fuzzy' matches: System guessed a correction - doctor should confirm/reject
    - 'no_match' matches: New medicine not in any list - doctor should add/correct
    - 'doctor_edit_*' matches: FYI only (doctor already corrected in UI)

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias
    - 'feedback_agreed'/'feedback_corrected': Already reviewed

    Args:
        doctor_id: Doctor ID
        limit: Max records to return
        offset: Records to skip
        include_exact_matches: If True, also include exact and common_name matches

    Returns:
        List of pending feedback records
    """
    # Query all pending feedback
    result = supabase.table('medicine_match_log').select(
        '*'
    ).eq('doctor_id', str(doctor_id)).is_(
        'feedback_status', 'null'
    ).order('created_at', desc=True).execute()

    records = result.data or []

    # Filter to only show matches that need review
    if not include_exact_matches:
        # Show matches that need doctor action:
        # - 'fuzzy': System guessed a correction - doctor should confirm/reject
        # - 'no_match': New medicine not in any list - doctor should add/correct
        # - 'doctor_edit_*': FYI only (already agreed implicitly)
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


def list_feedback_history(
    doctor_id: uuid.UUID,
    feedback_status: Optional[str] = None,
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

    By default, only returns matches that NEED/NEEDED doctor action:
    - 'fuzzy' matches: System guessed a correction
    - 'no_match' matches: New medicine not in any list
    - 'doctor_edit_*' matches: Doctor corrected in UI

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Args:
        doctor_id: Doctor ID
        feedback_status: Filter by status ('agreed', 'disagreed', None for all)
        confidence_min: Minimum confidence
        confidence_max: Maximum confidence
        source: Filter by source ('doctor_list', 'hospital_list')
        search: Search in medicine names
        limit: Max records
        offset: Records to skip
        include_exact_matches: If True, also include exact and common_name matches

    Returns:
        Dict with records and total count
    """
    query = supabase.table('medicine_match_log').select(
        '*', count='exact'
    ).eq('doctor_id', str(doctor_id))

    if feedback_status:
        query = query.eq('feedback_status', feedback_status)

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
            if search_lower in (r.get('original_medicine_name') or '').lower()
            or search_lower in (r.get('matched_medicine_name') or '').lower()
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

def get_medicine_list_for_prompt(
    doctor_id: uuid.UUID,
    hospital_id: Optional[uuid.UUID] = None,
    max_medicines: int = 3500,
    transcript_text: str = ""
) -> str:
    """
    Generate medicine list formatted for prompt injection.

    Args:
        doctor_id: Doctor ID
        hospital_id: Hospital ID (optional, auto-detected if not provided)
        max_medicines: Maximum medicines to include
        transcript_text: Optional transcript for form-based prioritization.
            When provided, detected dosage forms (tablet, syrup, etc.) are
            shown first with a "(mentioned)" hint to leverage LLM primacy bias.

    Returns:
        Formatted string for injection into user prompt
    """
    # Get doctor's hospital if not provided (cached - 10 min TTL)
    if not hospital_id:
        from services.supabase_service import get_doctor_hospital_id_cached
        cached_hospital_id = get_doctor_hospital_id_cached(doctor_id)
        if cached_hospital_id:
            hospital_id = uuid.UUID(cached_hospital_id)

    # Get medicines
    doctor_meds = list_doctor_medicines(doctor_id)
    hospital_meds = list_hospital_medicines(hospital_id) if hospital_id else []

    # Combine and deduplicate
    all_meds = {}
    for med in doctor_meds:
        all_meds[med['normalized_name']] = med

    for med in hospital_meds:
        if med['normalized_name'] not in all_meds:
            all_meds[med['normalized_name']] = med

    if not all_meds:
        return ""

    # Detect mentioned forms from transcript (microsecond operation)
    detected_forms: set = set()
    if transcript_text:
        transcript_lower = transcript_text.lower()
        for form, keywords in MEDICINE_FORM_KEYWORDS.items():
            if any(kw in transcript_lower for kw in keywords):
                detected_forms.add(form)

    # Group by form (primary), then by category (secondary)
    # This makes it visually easier for LLMs to disambiguate forms in large lists
    FORM_SORT_ORDER = [
        'Tablet', 'Capsule', 'Syrup', 'Injection', 'Drops', 'Cream',
        'Ointment', 'Inhaler', 'Spray', 'Suppository', 'Patch',
        'Powder', 'Granules', 'Vaccine', 'Penfill', 'Oil', 'Soap',
        'Lotion', 'Paste', 'Jelly', 'Enema', 'Bandage'
    ]
    form_order_map = {f.lower(): i for i, f in enumerate(FORM_SORT_ORDER)}

    by_form_category = {}  # {form: {category: [meds]}}
    for med in list(all_meds.values())[:max_medicines]:
        form = med.get('form') or detect_medicine_form(med.get('medicine_name', '')) or 'Other'
        category = med.get('category') or 'Other'
        if form not in by_form_category:
            by_form_category[form] = {}
        if category not in by_form_category[form]:
            by_form_category[form][category] = []
        by_form_category[form][category].append(med)

    # Sort forms: detected forms first (primacy bias), then standard order
    def form_sort_key(form_name):
        lower = form_name.lower()
        is_detected = form_name in detected_forms
        if lower == 'other':
            return (2, 0, 0, form_name)
        idx = form_order_map.get(lower, 99)
        # detected_forms get priority bucket 0, others get bucket 1
        priority = 0 if is_detected else 1
        return (priority, 0, idx, form_name)

    sorted_forms = sorted(by_form_category.keys(), key=form_sort_key)

    # Format for prompt
    lines = ["**DOCTOR'S MEDICINE LIST (Use these exact names when extracting prescriptions):**", ""]

    for form in sorted_forms:
        form_plural = f"{form}s" if not form.endswith('s') else form
        mentioned_hint = " (mentioned)" if detected_forms and form in detected_forms else ""
        lines.append(f"**--- {form_plural}{mentioned_hint} ---**")
        categories = by_form_category[form]
        for category in sorted(categories.keys()):
            meds = categories[category]
            lines.append(f"  {category}:")
            for med in meds:
                common_str = ""
                if med.get('common_names'):
                    common_str = f" (also: {', '.join(med['common_names'])})"
                # Add [Form] tag for explicit disambiguation (e.g., [Tablet], [Syrup])
                med_form = med.get('form') or detect_medicine_form(med.get('medicine_name', '')) or ''
                form_tag = f" [{med_form}]" if med_form else ""
                lines.append(f"    - {med['medicine_name']}{form_tag}{common_str}")
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# Medicine Edit Feedback - Compare original vs edited extractions
# ============================================================================

# Threshold for considering two medicine names as "same medicine with different spelling"
EDIT_SIMILARITY_THRESHOLD = 0.60  # Lower threshold to catch spelling corrections
EDIT_DISSIMILARITY_THRESHOLD = 0.40  # Below this, it's a completely different medicine


def _is_valid_medicine_edit(original: str, edited: str) -> Tuple[bool, float, str]:
    """
    Determine if the edit represents a valid medicine correction that should be logged.

    Valid edits include:
    - Name standardization (e.g., "amlo" → "AMLODIPINE")
    - Spelling correction (e.g., "Tolo 650" → "Dolo 650")
    - Dosage correction (e.g., "metformin 500" → "metformin 1000")

    Invalid edits (skipped):
    - Completely different medicines (e.g., "amlodipine" → "telmisartan")
    - Just case/formatting changes (e.g., "Dolo 650" → "DOLO 650")

    Returns:
        Tuple of (is_valid_edit, similarity_score, edit_type)
        edit_type: 'name_standardization', 'spelling_correction', 'dosage_correction',
                   'different_medicine', 'formatting_only'

    Examples:
        ("amlo 5mg", "AMLODIPINE 5MG") → True, 0.75, 'name_standardization'
        ("Tolo 650", "Dolo 650") → True, 0.88, 'spelling_correction'
        ("metformin 500", "metformin 1000") → True, 0.90, 'dosage_correction'
        ("amlodipine", "telmisartan") → False, 0.20, 'different_medicine'
        ("Dolo 650", "DOLO 650") → False, 1.0, 'formatting_only'
    """
    if not original or not edited:
        return False, 0.0, 'invalid'

    # Normalize both names
    norm_original = normalize_medicine_name(original)
    norm_edited = normalize_medicine_name(edited)

    # If normalized names are identical, it's just case/formatting change - not interesting
    if norm_original == norm_edited:
        return False, 1.0, 'formatting_only'

    # Calculate overall similarity
    if RAPIDFUZZ_AVAILABLE:
        # Use token_sort_ratio for better handling of word order differences
        similarity = fuzz.token_sort_ratio(norm_original, norm_edited) / 100.0
    else:
        # Basic fallback
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, norm_original, norm_edited).ratio()

    # Completely different medicine - skip
    if similarity < EDIT_DISSIMILARITY_THRESHOLD:
        return False, similarity, 'different_medicine'

    # Check if it's primarily a dosage difference
    # Extract base name (remove numbers and units)
    def extract_base_name(name: str) -> str:
        # Remove dosage patterns like "5mg", "500", "10MG", etc.
        base = re.sub(r'\d+\s*(mg|mcg|ml|g|iu|units?)?', '', name, flags=re.IGNORECASE)
        return re.sub(r'\s+', ' ', base).strip()

    base_original = extract_base_name(norm_original)
    base_edited = extract_base_name(norm_edited)

    # Calculate base name similarity
    if RAPIDFUZZ_AVAILABLE:
        base_similarity = fuzz.ratio(base_original, base_edited) / 100.0
    else:
        from difflib import SequenceMatcher
        base_similarity = SequenceMatcher(None, base_original, base_edited).ratio()

    # Determine edit type
    if base_similarity > 0.95:
        # Base names almost identical - this is a dosage correction
        # e.g., "metformin 500" → "metformin 1000"
        return True, similarity, 'dosage_correction'
    elif base_similarity > 0.70:
        # Base names similar but not identical - spelling correction
        # e.g., "Tolo 650" → "Dolo 650"
        return True, similarity, 'spelling_correction'
    elif similarity >= EDIT_SIMILARITY_THRESHOLD:
        # Overall similar but base names differ - name standardization
        # e.g., "amlo 5mg" → "AMLODIPINE 5MG"
        return True, similarity, 'name_standardization'

    return False, similarity, 'different_medicine'


async def process_medicine_edit_feedback(
    extraction_id: uuid.UUID,
    doctor_id: uuid.UUID,
    original_extraction: Dict[str, Any],
    edited_extraction: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare original vs edited extraction and log medicine name changes as feedback.

    This function:
    1. Extracts prescription data from both versions
    2. Matches medicines by fuzzy name similarity
    3. Identifies name standardizations (not dosage changes or different medicines)
    4. Logs to medicine_match_log with feedback_status='agreed'
    5. Auto-adds corrected medicines to doctor's personal list

    Args:
        extraction_id: Medical extraction UUID
        doctor_id: Doctor UUID who made edits
        original_extraction: AI-generated extraction JSON
        edited_extraction: Doctor-edited extraction JSON

    Returns:
        Summary of processed medicine edits
    """
    results = {
        "processed": 0,
        "logged": 0,
        "logged_name_standardization": 0,
        "logged_spelling_correction": 0,
        "logged_dosage_correction": 0,
        "added_to_list": 0,
        "skipped_different_medicine": 0,
        "skipped_no_match": 0,
        "errors": []
    }

    # Get submission_id from extraction for logging
    try:
        ext_result = supabase.table("medical_extractions")\
            .select("session_id")\
            .eq("id", str(extraction_id))\
            .limit(1)\
            .execute()

        session_id = ext_result.data[0]["session_id"] if ext_result.data else None

        # Get submission_id from processing_jobs
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
        logger.warning(f"[MedicineEditFeedback] Failed to get session/submission IDs: {e}")
        submission_id = None

    # Extract prescription data from both versions
    # Supports multiple field names and nested structures like:
    # - {"prescription": [{...}]} (direct array)
    # - {"prescription": {"prescription": [{...}]}} (nested object with 'prescription' key)
    # - {"prescription": {"medications": [{...}]}} (nested object with 'medications' key)
    prescription_fields = ['prescription', 'medications', 'drugs', 'prescribedMedicines']

    def extract_meds_from_data(data: Any) -> list:
        """Extract medication list from various data structures."""
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Check for nested keys: 'prescription', 'medications', 'drugs', 'items'
            for nested_key in ['prescription', 'medications', 'drugs', 'items']:
                if nested_key in data:
                    nested_data = data[nested_key]
                    if isinstance(nested_data, list):
                        return nested_data
        return []

    original_meds = []
    edited_meds = []

    for key in prescription_fields:
        if key in original_extraction:
            original_meds = extract_meds_from_data(original_extraction[key])
            if original_meds:
                break

    for key in prescription_fields:
        if key in edited_extraction:
            edited_meds = extract_meds_from_data(edited_extraction[key])
            if edited_meds:
                break

    if not original_meds or not edited_meds:
        logger.debug(
            f"[MedicineEditFeedback] No prescription data to compare for extraction {extraction_id}. "
            f"original_meds={len(original_meds)}, edited_meds={len(edited_meds)}, "
            f"original_keys={list(original_extraction.keys())}, edited_keys={list(edited_extraction.keys())}"
        )
        return results

    logger.debug(
        f"[MedicineEditFeedback] Found prescription data: "
        f"original={len(original_meds)} meds, edited={len(edited_meds)} meds"
    )

    # Extract medicine names from each list
    name_fields = ['name', 'medicine_name', 'drugName', 'medication']

    def get_med_name(med: Dict) -> Optional[str]:
        if not isinstance(med, dict):
            return None
        for key in name_fields:
            if key in med and med[key]:
                return med[key]
        return None

    original_names = [(get_med_name(m), m) for m in original_meds if get_med_name(m)]
    edited_names = [(get_med_name(m), m) for m in edited_meds if get_med_name(m)]

    # Match original to edited by similarity
    # For each original medicine, find the best matching edited medicine
    matched_pairs = []
    used_edited_indices = set()

    for orig_name, orig_med in original_names:
        best_match = None
        best_similarity = 0.0
        best_idx = -1

        for idx, (edit_name, edit_med) in enumerate(edited_names):
            if idx in used_edited_indices:
                continue

            # Calculate similarity
            if RAPIDFUZZ_AVAILABLE:
                similarity = fuzz.token_sort_ratio(
                    normalize_medicine_name(orig_name),
                    normalize_medicine_name(edit_name)
                ) / 100.0
            else:
                from difflib import SequenceMatcher
                similarity = SequenceMatcher(
                    None,
                    normalize_medicine_name(orig_name),
                    normalize_medicine_name(edit_name)
                ).ratio()

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = (edit_name, edit_med)
                best_idx = idx

        if best_match and best_similarity >= EDIT_SIMILARITY_THRESHOLD:
            matched_pairs.append((orig_name, best_match[0], best_similarity))
            used_edited_indices.add(best_idx)
        else:
            # No good match found - could be removed medicine
            results["skipped_no_match"] += 1

    # Process matched pairs
    for orig_name, edit_name, similarity in matched_pairs:
        results["processed"] += 1

        # Check if this is a valid medicine edit
        is_valid, _, edit_type = _is_valid_medicine_edit(orig_name, edit_name)

        if not is_valid:
            if edit_type == 'formatting_only':
                # Just case/formatting - skip silently
                continue
            elif edit_type == 'different_medicine':
                results["skipped_different_medicine"] += 1
                continue
            else:
                # Unknown skip reason
                continue

        # Valid edit - log as feedback
        # edit_type is one of: 'name_standardization', 'spelling_correction', 'dosage_correction'
        try:
            # Log to medicine_match_log
            supabase.table('medicine_match_log').insert({
                'extraction_id': str(extraction_id),
                'submission_id': submission_id,
                'doctor_id': str(doctor_id),
                'original_medicine_name': orig_name,
                'matched_medicine_name': edit_name,
                'match_confidence': similarity,
                'match_method': f'doctor_edit_{edit_type}',  # e.g., 'doctor_edit_spelling_correction'
                'match_source': 'doctor_correction',
                'feedback_status': 'agreed',
                'feedback_at': datetime.utcnow().isoformat()
            }).execute()

            results["logged"] += 1
            results[f"logged_{edit_type}"] = results.get(f"logged_{edit_type}", 0) + 1
            logger.debug(f"[MedicineEditFeedback] Logged ({edit_type}): '{orig_name}' → '{edit_name}' (similarity: {similarity:.2f})")

        except Exception as e:
            logger.warning(f"[MedicineEditFeedback] Failed to log feedback: {e}")
            results["errors"].append(f"Log failed for {orig_name}: {str(e)}")

        # Auto-add to doctor's medicine list
        try:
            # Check if already exists
            existing = supabase.table('doctor_medicines')\
                .select('id')\
                .eq('doctor_id', str(doctor_id))\
                .eq('normalized_name', normalize_medicine_name(edit_name))\
                .limit(1)\
                .execute()

            if not existing.data:
                # Check hospital list first for enriched data
                added_via_hospital = False
                try:
                    from services.supabase_service import get_doctor_hospital_id_cached
                    hospital_id = get_doctor_hospital_id_cached(doctor_id)
                    if hospital_id:
                        hospital_match = supabase.table('hospital_medicine_lists')\
                            .select('id')\
                            .eq('hospital_id', str(hospital_id))\
                            .eq('normalized_name', normalize_medicine_name(edit_name))\
                            .eq('is_active', True)\
                            .limit(1).execute()
                        if hospital_match.data:
                            copy_result = copy_hospital_medicine_to_doctor(
                                hospital_medicine_id=uuid.UUID(hospital_match.data[0]['id']),
                                doctor_id=doctor_id
                            )
                            if copy_result:
                                added_via_hospital = True
                                logger.debug(f"[MedicineEditFeedback] Added '{edit_name}' from hospital list (enriched)")
                                # Add orig_name as common_name on the new doctor record
                                if orig_name.lower() != edit_name.lower():
                                    new_rec = supabase.table('doctor_medicines')\
                                        .select('id, common_names')\
                                        .eq('doctor_id', str(doctor_id))\
                                        .eq('normalized_name', normalize_medicine_name(edit_name))\
                                        .limit(1).execute()
                                    if new_rec.data:
                                        names = new_rec.data[0].get('common_names') or []
                                        if orig_name.lower() not in [n.lower() for n in names]:
                                            supabase.table('doctor_medicines')\
                                                .update({'common_names': names + [orig_name]})\
                                                .eq('id', new_rec.data[0]['id']).execute()
                except Exception as e:
                    logger.warning(f"[MedicineEditFeedback] Hospital list check failed: {e}")

                if not added_via_hospital:
                    # Fallback: add bare entry without hospital enrichment
                    create_doctor_medicine(
                        doctor_id=doctor_id,
                        medicine_name=edit_name,
                        common_names=[orig_name] if orig_name.lower() != edit_name.lower() else [],
                        category=None,
                        typical_dosage=None,
                        form=None,
                        snomed_code=None,
                        formulary_name=None,
                        medicine_type='generic'
                    )
                    logger.debug(f"[MedicineEditFeedback] Added '{edit_name}' to doctor's medicine list (bare)")
                results["added_to_list"] += 1
            else:
                # Update common_names to include the original name
                existing_id = existing.data[0]['id']
                current = supabase.table('doctor_medicines')\
                    .select('common_names')\
                    .eq('id', existing_id)\
                    .limit(1)\
                    .execute()

                if current.data:
                    current_names = current.data[0].get('common_names') or []
                    if orig_name.lower() not in [n.lower() for n in current_names]:
                        updated_names = current_names + [orig_name]
                        supabase.table('doctor_medicines')\
                            .update({'common_names': updated_names})\
                            .eq('id', existing_id)\
                            .execute()
                        logger.debug(f"[MedicineEditFeedback] Added '{orig_name}' as common name for '{edit_name}'")

        except Exception as e:
            logger.warning(f"[MedicineEditFeedback] Failed to add to doctor's list: {e}")
            results["errors"].append(f"Add to list failed for {edit_name}: {str(e)}")

    logger.debug(f"[MedicineEditFeedback] Completed: {results}")
    return results


# ============================================================================
# Backfill - Enrich doctor medicines from hospital list
# ============================================================================

def backfill_medicine_abbreviations(
    doctor_id: uuid.UUID,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Backfill existing doctor medicines with enriched common_names from
    the expanded MEDICINE_ABBREVIATIONS dictionary.

    For each medicine, runs extract_medicine_aliases() and adds any new
    aliases not already in common_names. Also regenerates search_tokens.

    Args:
        doctor_id: Doctor UUID
        dry_run: If True, only report what would change without updating

    Returns:
        Summary dict with updated/skipped counts and details
    """
    medicines = list_doctor_medicines(doctor_id)
    updated = []
    skipped = 0

    for med in medicines:
        med_id = med.get('id')
        med_name = med.get('medicine_name', '')
        existing_common = med.get('common_names') or []

        # Also check formulary_name for abbreviation matches
        formulary = med.get('formulary_name') or ''
        new_aliases = extract_medicine_aliases(med_name, existing_common)
        if formulary:
            formulary_aliases = extract_medicine_aliases(formulary, existing_common + new_aliases)
            new_aliases.extend(formulary_aliases)

        if not new_aliases:
            skipped += 1
            continue

        enriched_common = existing_common + new_aliases
        enriched_tokens = generate_search_tokens(med_name, enriched_common)

        if dry_run:
            updated.append({
                "id": med_id,
                "medicine_name": med_name,
                "existing_common_names": existing_common,
                "new_aliases": new_aliases,
                "enriched_common_names": enriched_common,
            })
        else:
            try:
                supabase.table('doctor_medicines').update({
                    'common_names': enriched_common,
                    'search_tokens': enriched_tokens,
                }).eq('id', str(med_id)).execute()
                updated.append({
                    "id": med_id,
                    "medicine_name": med_name,
                    "new_aliases": new_aliases,
                })
            except Exception as e:
                logger.warning(f"[BACKFILL_ABBREV] Failed to update {med_id}: {e}")

    if not dry_run and updated:
        invalidate_doctor_medicine_cache(doctor_id)

    return {
        "doctor_id": str(doctor_id),
        "dry_run": dry_run,
        "total_medicines": len(medicines),
        "updated_count": len(updated),
        "skipped_count": skipped,
        "updates": updated,
    }


def backfill_doctor_medicines_from_hospital(
    doctor_id: uuid.UUID,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Backfill doctor medicine entries that have no external_id by matching
    against the hospital medicine list and copying enrichment fields.

    Fields updated: external_id, form, category, typical_dosage,
    snomed_code, formulary_name, medicine_type, common_names (merged).
    """
    from services.supabase_service import get_doctor_hospital_id_cached

    result = {
        "doctor_id": str(doctor_id),
        "dry_run": dry_run,
        "total_doctor_medicines": 0,
        "missing_external_id": 0,
        "matched": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "details": []
    }

    hospital_id = get_doctor_hospital_id_cached(doctor_id)
    if not hospital_id:
        result["errors"].append("Doctor has no associated hospital")
        return result

    # Get doctor medicines missing external_id
    doctor_meds = supabase.table('doctor_medicines')\
        .select('id, medicine_name, normalized_name, common_names, external_id')\
        .eq('doctor_id', str(doctor_id))\
        .eq('is_active', True)\
        .execute()

    if not doctor_meds.data:
        return result

    result["total_doctor_medicines"] = len(doctor_meds.data)
    missing = [m for m in doctor_meds.data if not m.get('external_id')]
    result["missing_external_id"] = len(missing)

    if not missing:
        return result

    # Build hospital lookup by normalized_name
    hospital_meds = supabase.table('hospital_medicine_lists')\
        .select('id, medicine_name, normalized_name, common_names, external_id, form, category, typical_dosage, snomed_code, formulary_name, medicine_type')\
        .eq('hospital_id', str(hospital_id))\
        .eq('is_active', True)\
        .execute()

    hospital_lookup = {}
    for hm in (hospital_meds.data or []):
        norm = hm.get('normalized_name', '')
        if norm:
            hospital_lookup[norm] = hm

    for dm in missing:
        norm_name = dm.get('normalized_name', '')
        hm = hospital_lookup.get(norm_name)

        if not hm:
            result["skipped"] += 1
            continue

        result["matched"] += 1

        # Merge common_names
        doctor_names = dm.get('common_names') or []
        hospital_names = hm.get('common_names') or []
        existing_lower = {n.lower() for n in doctor_names}
        merged_names = list(doctor_names)
        for name in hospital_names:
            if name.lower() not in existing_lower:
                merged_names.append(name)
                existing_lower.add(name.lower())

        update_data = {
            'external_id': hm.get('external_id'),
            'form': hm.get('form'),
            'category': hm.get('category'),
            'typical_dosage': hm.get('typical_dosage'),
            'snomed_code': hm.get('snomed_code'),
            'formulary_name': hm.get('formulary_name'),
            'medicine_type': hm.get('medicine_type'),
            'common_names': merged_names
        }
        # Only include non-None fields (don't overwrite with None)
        update_data = {k: v for k, v in update_data.items() if v is not None}

        detail = {
            "doctor_medicine_id": dm['id'],
            "medicine_name": dm['medicine_name'],
            "hospital_external_id": hm.get('external_id'),
            "fields_to_update": list(update_data.keys())
        }

        if dry_run:
            result["details"].append(detail)
        else:
            try:
                supabase.table('doctor_medicines')\
                    .update(update_data)\
                    .eq('id', dm['id'])\
                    .execute()
                result["updated"] += 1
                result["details"].append({**detail, "status": "updated"})
            except Exception as e:
                result["errors"].append(f"Update failed for {dm['medicine_name']}: {str(e)}")
                result["details"].append({**detail, "status": "error", "error": str(e)})

    logger.info(f"[MedicineBackfill] doctor={doctor_id} dry_run={dry_run} "
                f"total={result['total_doctor_medicines']} missing={result['missing_external_id']} "
                f"matched={result['matched']} updated={result['updated']}")
    return result


# ============================================================================
# NEO-Specific Medicine Post-Processing
# ============================================================================

async def postprocess_neo_prescription_extraction(
    extraction_data: Dict[str, Any],
    doctor_id: uuid.UUID,
    extraction_id: uuid.UUID,
    submission_id: str,
    consultation_type_code: str,
    log_matches: bool = True
) -> Dict[str, Any]:
    """
    Post-process NEO template medication fields against doctor's medicine list.

    Handles all NEO medication structures:
    A. Object arrays: NEO_DAILY antibiotics_list [{drugId, drugName, dose, frequency, route}]
    B. Parallel arrays: medications_drugIds[], medication_drugIds[] (pre-formatting flat keys)
    C. String arrays: NEO_ADMISSION procedures_ivAntibioticIds[], NEO_PROFORMA maternalAntibioticsArray[]
    D. Nested medications: NEO_OP top-level medications[], NEO_DISCHARGE discharge.medications[]
       (post-formatting nested objects — formatters run inside gemini_service before this)

    For each drug name, uses match_medicine_name() (7-level matching) to resolve
    against the doctor's/hospital's list. If matched, updates the name and attaches
    _external_id for downstream EHR formatters.

    Args:
        extraction_data: Full extraction result (will be modified in-place)
        doctor_id: Doctor UUID
        extraction_id: Extraction record UUID (for match logging)
        submission_id: Submission/session ID (for match logging)
        consultation_type_code: e.g. NEONATAL_DAILY, NEONATAL_DISCHARGE, etc.
        log_matches: Whether to log each match to medicine_match_log

    Returns:
        Updated extraction_data with matched medicine names and _external_id attached
    """
    import time as time_module

    ct = (consultation_type_code or "").upper()
    postprocess_start = time_module.time()
    total_matched = 0
    total_processed = 0

    logger.info(f"[NEO Medicine Post-Process] Starting for {ct}, doctor={str(doctor_id)[:8]}...")

    try:
        # =====================================================================
        # A. Object arrays: NEO_DAILY antibiotics_list
        # Structure: [{drugId, drugName, dose, frequency, route}, ...]
        # =====================================================================
        antibiotics_list = extraction_data.get("antibiotics_list", [])
        if not antibiotics_list and isinstance(extraction_data.get("antibiotics"), list):
            # Formatter may have already restructured to top-level "antibiotics"
            antibiotics_list = extraction_data.get("antibiotics", [])

        if antibiotics_list and isinstance(antibiotics_list, list):
            for antibiotic in antibiotics_list:
                if not isinstance(antibiotic, dict):
                    continue
                drug_name = antibiotic.get("drugName", "")
                if not drug_name:
                    continue

                total_processed += 1
                match_result = await match_medicine_name(
                    extracted_name=drug_name,
                    doctor_id=doctor_id,
                    submission_id=submission_id
                )

                if match_result["matched"]:
                    total_matched += 1
                    if match_result["matched_name"] != drug_name:
                        antibiotic["drugName"] = match_result["matched_name"]
                    if match_result.get("external_id"):
                        try:
                            antibiotic["_external_id"] = int(match_result["external_id"])
                        except (ValueError, TypeError):
                            antibiotic["_external_id"] = match_result["external_id"]
                else:
                    # Fallback: try static drug_lookups
                    try:
                        from services.drug_lookups import lookup_drug_id_fuzzy
                        static_id = lookup_drug_id_fuzzy(drug_name)
                        if static_id:
                            antibiotic["_external_id"] = static_id
                    except Exception:
                        pass

                if log_matches:
                    _log_neo_medicine_match(extraction_id, submission_id, doctor_id, drug_name, match_result)

        # =====================================================================
        # B. Parallel arrays: NEO_DISCHARGE medications_drugIds[], NEO_OP medication_drugIds[]
        # Structure: ["name1", "name2"] with parallel doses[], routes[], etc.
        # =====================================================================
        for drug_ids_key in ["medications_drugIds", "medication_drugIds"]:
            drug_ids_arr = extraction_data.get(drug_ids_key)
            if not drug_ids_arr or not isinstance(drug_ids_arr, list):
                continue

            resolved_ids = []
            updated_names = []
            for drug_entry in drug_ids_arr:
                drug_name = str(drug_entry).strip() if drug_entry else ""
                if not drug_name:
                    resolved_ids.append(None)
                    updated_names.append(drug_name)
                    continue

                total_processed += 1
                match_result = await match_medicine_name(
                    extracted_name=drug_name,
                    doctor_id=doctor_id,
                    submission_id=submission_id
                )

                if match_result["matched"]:
                    total_matched += 1
                    updated_names.append(match_result["matched_name"])
                    ext_id = match_result.get("external_id")
                    if ext_id:
                        try:
                            resolved_ids.append(int(ext_id))
                        except (ValueError, TypeError):
                            resolved_ids.append(ext_id)
                    else:
                        resolved_ids.append(None)
                else:
                    updated_names.append(drug_name)
                    # Fallback: try static drug_lookups
                    try:
                        from services.drug_lookups import lookup_drug_id_fuzzy
                        static_id = lookup_drug_id_fuzzy(drug_name)
                        resolved_ids.append(static_id)
                    except Exception:
                        resolved_ids.append(None)

                if log_matches:
                    _log_neo_medicine_match(extraction_id, submission_id, doctor_id, drug_name, match_result)

            # Update the extraction data
            extraction_data[drug_ids_key] = updated_names
            extraction_data[f"_resolved_{drug_ids_key}"] = resolved_ids

        # =====================================================================
        # C. String arrays: NEO_ADMISSION procedures_ivAntibioticIds[],
        #    NEO_PROFORMA maternalAntibioticsArray[]
        # Structure: ["Ampicillin", "Gentamicin"]
        # =====================================================================
        for arr_key in ["procedures_ivAntibioticIds", "procedures_ivAntibiotics",
                        "maternalAntibioticsArray"]:
            str_arr = extraction_data.get(arr_key)
            if not str_arr or not isinstance(str_arr, list):
                continue

            updated_arr = []
            resolved_ids = []
            for drug_name in str_arr:
                drug_name = str(drug_name).strip() if drug_name else ""
                if not drug_name:
                    updated_arr.append(drug_name)
                    resolved_ids.append(None)
                    continue

                total_processed += 1
                match_result = await match_medicine_name(
                    extracted_name=drug_name,
                    doctor_id=doctor_id,
                    submission_id=submission_id
                )

                if match_result["matched"]:
                    total_matched += 1
                    updated_arr.append(match_result["matched_name"])
                    ext_id = match_result.get("external_id")
                    if ext_id:
                        try:
                            resolved_ids.append(int(ext_id))
                        except (ValueError, TypeError):
                            resolved_ids.append(ext_id)
                    else:
                        resolved_ids.append(None)
                else:
                    updated_arr.append(drug_name)
                    # Fallback: try static drug_lookups
                    try:
                        from services.drug_lookups import lookup_drug_id_fuzzy
                        static_id = lookup_drug_id_fuzzy(drug_name)
                        resolved_ids.append(static_id)
                    except Exception:
                        resolved_ids.append(None)

                if log_matches:
                    _log_neo_medicine_match(extraction_id, submission_id, doctor_id, drug_name, match_result)

            extraction_data[arr_key] = updated_arr
            extraction_data[f"_resolved_{arr_key}"] = resolved_ids

        # =====================================================================
        # D. Nested medications array: NEO_OP (top-level), NEO_DISCHARGE (under discharge)
        # After formatting inside gemini_service, the flat medication_drugIds
        # arrays have been converted to nested objects. This section resolves
        # drug names to external IDs in the already-formatted structure.
        # Structure: [{"drugId": "drug name", "route": "1", "dosage": [...]}]
        # =====================================================================
        medications_locations = []
        # NEO_OP: top-level medications
        top_meds = extraction_data.get("medications")
        if isinstance(top_meds, list) and top_meds:
            medications_locations.append(top_meds)
        # NEO_DISCHARGE: discharge.medications
        discharge_obj = extraction_data.get("discharge")
        if isinstance(discharge_obj, dict):
            discharge_meds = discharge_obj.get("medications")
            if isinstance(discharge_meds, list) and discharge_meds:
                medications_locations.append(discharge_meds)

        for medications_list in medications_locations:
            for med in medications_list:
                if not isinstance(med, dict):
                    continue
                # Support both drugId (structured NEO) and drugName (free-text NEO)
                is_free_text = "drugName" in med and "drugId" not in med
                drug_name = med.get("drugId", "") or med.get("drugName", "")
                if not drug_name or not isinstance(drug_name, str):
                    continue
                # Skip if already a numeric ID
                if drug_name.strip().isdigit():
                    continue

                total_processed += 1
                match_result = await match_medicine_name(
                    extracted_name=drug_name,
                    doctor_id=doctor_id,
                    submission_id=submission_id
                )

                if match_result["matched"]:
                    total_matched += 1
                    ext_id = match_result.get("external_id")
                    if is_free_text:
                        # Free-text templates: update drugName (not drugId)
                        if ext_id:
                            med["drugName"] = match_result["matched_name"]
                        elif match_result["matched_name"] != drug_name:
                            med["drugName"] = match_result["matched_name"]
                    else:
                        # Structured templates: update drugId
                        if ext_id:
                            try:
                                med["drugId"] = str(int(ext_id))
                            except (ValueError, TypeError):
                                med["drugId"] = str(ext_id)
                        elif match_result["matched_name"] != drug_name:
                            med["drugId"] = match_result["matched_name"]
                else:
                    # Fallback: try static drug_lookups
                    try:
                        from services.drug_lookups import lookup_drug_id_fuzzy
                        static_id = lookup_drug_id_fuzzy(drug_name)
                        if static_id:
                            if is_free_text:
                                pass  # Name already set
                            else:
                                med["drugId"] = str(static_id)
                    except Exception:
                        pass

                if log_matches:
                    _log_neo_medicine_match(extraction_id, submission_id, doctor_id, drug_name, match_result)

    except Exception as e:
        logger.warning(f"[NEO Medicine Post-Process] Error (non-fatal): {e}")

    duration = time_module.time() - postprocess_start
    logger.info(
        f"[NEO Medicine Post-Process] Done for {ct}: "
        f"{total_processed} processed, {total_matched} matched, {duration:.3f}s"
    )

    return extraction_data


def _log_neo_medicine_match(
    extraction_id: uuid.UUID,
    submission_id: str,
    doctor_id: uuid.UUID,
    original_name: str,
    match_result: Dict[str, Any]
) -> None:
    """Log a NEO medicine match to the medicine_match_log table."""
    try:
        matched_doctor_med_id = None
        matched_hospital_med_id = None
        if match_result.get("source") == "doctor_list":
            matched_doctor_med_id = match_result.get("matched_medicine_id")
        elif match_result.get("source") == "hospital_list":
            matched_hospital_med_id = match_result.get("matched_hospital_medicine_id")

        supabase.table("medicine_match_log").insert({
            "extraction_id": str(extraction_id),
            "submission_id": submission_id,
            "doctor_id": str(doctor_id),
            "original_medicine_name": original_name,
            "matched_medicine_id": matched_doctor_med_id,
            "matched_hospital_medicine_id": matched_hospital_med_id,
            "matched_medicine_name": match_result.get("matched_name", original_name),
            "match_confidence": match_result.get("confidence", 0),
            "match_method": match_result.get("method", "neo_postprocess"),
            "match_source": match_result.get("source", "neo_template"),
            "diagnosis_context": None
        }).execute()
    except Exception as e:
        logger.warning(f"[NEO Medicine Post-Process] Failed to log match for '{original_name}': {e}")

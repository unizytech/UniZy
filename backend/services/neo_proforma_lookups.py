"""
NEO_PROFORMA Raster API Lookup Tables

Field-level value normalization/validation for NEO_PROFORMA payloads before
sending to the Neopaed API. Converts extracted text values to the exact
enum strings expected by the Raster database.

Reference: references/Neopaed - One Hat integration values reference sheet.md
"""

import re
import logging
from typing import Dict, Any, Union, Optional, List

logger = logging.getLogger(__name__)


# ============================================================================
# SENTENCE CAPITALIZATION UTILITY (shared across all neo_* templates)
# ============================================================================

# Medical abbreviations that should always be uppercase (word-boundary matched).
# Curated for NICU/neonatal clinical context.
_MEDICAL_ABBREVIATIONS = {
    # Diagnostics & monitoring
    "ecg", "eeg", "emg", "mri", "usg", "cfm", "abr", "oae",
    # Blood gas & lab
    "abg", "vbg", "cbg", "crp", "csf", "tsb", "dct", "ict", "pcv",
    "hco3", "pco2", "po2", "aado2", "rbs", "gir", "alp",
    # Ventilation & respiratory
    "cpap", "hfov", "hfnc", "nimv", "peep", "pip", "fio2", "spo2",
    "ett", "ppv", "cpr", "rds", "ttn", "bpd", "cld",
    # Conditions & syndromes
    "mas", "hie", "cdh", "nec", "pda", "rop", "nnj", "pphn",
    "hellp", "gdm", "pih", "iugr", "fgr", "prom", "pprom",
    "aph", "uti", "dcc", "ivh",
    # Units & facilities
    "nicu", "hdu", "scbu", "picu",
    # Procedures & access
    "uac", "uvc", "picc", "pvc", "pac", "lscs", "nvd",
    # Treatments & substances
    "ivf", "tpn", "mgso4",
    # Identifiers
    "vdrl", "hiv", "uhid", "ofc", "cft",
    # Routes & measurements (2-letter, unambiguous in medical context)
    "iv", "im", "bp", "hr", "gi", "hb", "ct",
}

# Pre-compile regex patterns for each abbreviation (word-boundary match)
_ABBR_PATTERNS = [
    (re.compile(r'\b' + re.escape(abbr) + r'\b', re.IGNORECASE), abbr.upper())
    for abbr in _MEDICAL_ABBREVIATIONS
]


def convert_comma_separated_to_int_array(value: Any) -> List[int]:
    """
    Convert a comma-separated string of IDs to an array of integers.

    Handles multiple input formats:
    - String: "3, 4, 5, 7" or "3,4,5,7" → [3, 4, 5, 7]
    - Already an array: validates and converts elements to int
    - None/empty: returns []

    Args:
        value: Input value (string, list, or None)

    Returns:
        List of integers
    """
    if value is None:
        return []

    # Already an array - validate and convert elements to int
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, int):
                result.append(item)
            elif isinstance(item, (str, float)) and str(item).strip():
                try:
                    result.append(int(float(str(item).strip())))
                except (ValueError, TypeError):
                    pass
        return result

    # String value - parse comma-separated IDs
    if isinstance(value, str):
        value_str = value.strip()
        if not value_str:
            return []

        result = []
        for part in value_str.split(","):
            part = part.strip()
            if part:
                try:
                    result.append(int(float(part)))
                except (ValueError, TypeError):
                    pass
        return result

    # Single numeric value
    if isinstance(value, (int, float)):
        return [int(value)]

    # Unexpected type - default to empty array
    return []


def convert_comma_separated_to_string_array(value: Any) -> List[str]:
    """
    Convert a comma-separated string to an array of strings.

    Handles multiple input formats:
    - String: "RDS, Sepsis, PDA" → ["RDS", "Sepsis", "PDA"]
    - Already an array: validates and strips elements
    - None/empty: returns []

    Args:
        value: Input value (string, list, or None)

    Returns:
        List of strings
    """
    if value is None:
        return []

    # Already an array - validate and strip string elements
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
            elif item is not None:
                str_val = str(item).strip()
                if str_val:
                    result.append(str_val)
        return result

    # String value - parse comma-separated values
    if isinstance(value, str):
        value_str = value.strip()
        if not value_str:
            return []

        result = []
        for part in value_str.split(","):
            part = part.strip()
            if part:
                result.append(part)
        return result

    # Single value - convert to string
    str_val = str(value).strip()
    if str_val:
        return [str_val]

    return []


def capitalize_sentences(value: Any) -> Any:
    """
    Capitalize the first letter of each sentence in free-text fields.

    - Capitalizes the first character of the string
    - Capitalizes the first letter after sentence-ending punctuation (. ! ?)
    - Preserves and restores medical abbreviations (ECG, IVF, CPAP, etc.)
    - Handles None, non-string, and empty values gracefully
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    val = value.strip()
    if not val:
        return val
    # Capitalize first character
    result = val[0].upper() + val[1:]
    # Capitalize first letter after sentence-ending punctuation + whitespace
    result = re.sub(
        r'([.!?])\s+([a-z])',
        lambda m: m.group(1) + ' ' + m.group(2).upper(),
        result
    )
    # Restore medical abbreviations to uppercase (e.g., "ecg" → "ECG", "Ecg" → "ECG")
    for pattern, replacement in _ABBR_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def _capitalize_fields(obj: Dict[str, Any], fields: List[str]) -> None:
    """Apply capitalize_sentences to a list of fields in a dict, in-place."""
    for field in fields:
        if field in obj and isinstance(obj[field], str):
            obj[field] = capitalize_sentences(obj[field])


# ============================================================================
# STRING ENUM MAPS
# ============================================================================

BIRTH_STATUS_MAP: Dict[str, str] = {
    "inborn": "Inborn",
    "outborn": "Outborn",
}

SEX_MAP: Dict[str, str] = {
    "male": "Male",
    "m": "Male",
    "female": "Female",
    "f": "Female",
    "indeterminate": "Indeterminate",
    "ambiguous": "Indeterminate",
}

BLOOD_GROUP_MAP: Dict[str, str] = {
    "not known": "Not Known",
    "unknown": "Not Known",
    "a positive": "A Positive",
    "a+": "A Positive",
    "a1 positive": "A1 Positive",
    "a1+": "A1 Positive",
    "a2 positive": "A2 Positive",
    "a2+": "A2 Positive",
    "a negative": "A Negative",
    "a-": "A Negative",
    "a1 negative": "A1 Negative",
    "a1-": "A1 Negative",
    "a2 negative": "A2 Negative",
    "a2-": "A2 Negative",
    "b positive": "B Positive",
    "b+": "B Positive",
    "b negative": "B Negative",
    "b-": "B Negative",
    "o positive": "O Positive",
    "o+": "O Positive",
    "o negative": "O Negative",
    "o-": "O Negative",
    "ab positive": "AB Positive",
    "ab+": "AB Positive",
    "a1b positive": "A1B Positive",
    "a1b+": "A1B Positive",
    "a2b positive": "A2B Positive",
    "a2b+": "A2B Positive",
    "ab negative": "AB Negative",
    "ab-": "AB Negative",
    "a1b negative": "A1B Negative",
    "a1b-": "A1B Negative",
    "a2b negative": "A2B Negative",
    "a2b-": "A2B Negative",
}

BIRTH_ORDER_MAP: Dict[str, str] = {
    "singleton": "Singleton",
    "single": "Singleton",
    "twin 1": "Twin 1",
    "twin1": "Twin 1",
    "twin 2": "Twin 2",
    "twin2": "Twin 2",
    "triplet 1": "Triplet 1",
    "triplet1": "Triplet 1",
    "triplet 2": "Triplet 2",
    "triplet2": "Triplet 2",
    "triplet 3": "Triplet 3",
    "triplet3": "Triplet 3",
}

TRANSFER_STATUS_MAP: Dict[str, str] = {
    "nicu": "NICU",
    "hdu": "HDU",
    "scbu": "SCBU",
    "postnatal ward": "Postnatal Ward",
    "postnatal": "Postnatal Ward",
    "nursery": "Nursery",
}

CONCEPTION_MAP: Dict[str, str] = {
    "not known": "Not Known",
    "unknown": "Not Known",
    "spontaneous": "Spontaneous",
    "natural": "Spontaneous",
    "medical art": "Medical ART",
    "art": "ART",
    "ivf": "ART",
    "assisted": "ART",
}

HIV_MAP: Dict[str, str] = {
    "negative": "Negative",
    "non-reactive": "Negative",
    "non reactive": "Negative",
    "positive": "Positive",
    "reactive": "Positive",
    "unknown": "Unknown",
    "not known": "Unknown",
}

VDRL_MAP: Dict[str, str] = {
    "non-reactive": "Non-reactive",
    "non reactive": "Non-reactive",
    "negative": "Non-reactive",
    "reactive": "Reactive",
    "positive": "Reactive",
    "unknown": "Unknown",
    "not known": "Unknown",
}

MODE_OF_DELIVERY_MAP: Dict[str, str] = {
    "normal vaginal": "Normal Vaginal",
    "nvd": "Normal Vaginal",
    "normal vaginal delivery": "Normal Vaginal",
    "preterm vaginal": "Preterm Vaginal",
    "forceps": "Forceps",
    "ventouse": "Ventouse",
    "vacuum": "Ventouse",
    "assisted breech": "Assisted Breech",
    "emergency caesarian": "Emergency Caesarian",
    "emergency lscs": "Emergency Caesarian",
    "emergency c-section": "Emergency Caesarian",
    "emergency cesarean": "Emergency Caesarian",
    "emergency caesarean": "Emergency Caesarian",
    "elective caesarian": "Elective Caesarian",
    "elective lscs": "Elective Caesarian",
    "elective c-section": "Elective Caesarian",
    "elective cesarean": "Elective Caesarian",
    "elective caesarean": "Elective Caesarian",
    "caesarian": "Caesarian",
    "cesarean": "Caesarian",
    "caesarean": "Caesarian",
    "lscs": "Caesarian",
    "c-section": "Caesarian",
    "c section": "Caesarian",
    "cs": "Caesarian",
}

PRESENTATION_MAP: Dict[str, str] = {
    "not known": "Not Known",
    "unknown": "Not Known",
    "cephalic": "Cephalic",
    "vertex": "Cephalic",
    "head": "Cephalic",
    "breech": "Breech",
    "twins": "Twins",
    "twin": "Twins",
    "transverse lie": "Transverse Lie",
    "transverse": "Transverse Lie",
    "other": "Other",
    "others": "Other",
}

CTG_MAP: Dict[str, str] = {
    "normal": "Normal",
    "abnormal": "Abnormal",
    "not known": "Not Known",
    "unknown": "Not Known",
}

CORD_BLOOD_GAS_MAP: Dict[str, str] = {
    "not done": "Not done",
    "none": "Not done",
    "not indicated": "Not indicated",
    "arterial": "Arterial",
    "abg": "Arterial",
    "venous": "Venous",
    "vbg": "Venous",
    "capillary": "Capillary",
    "cbg": "Capillary",
}

GASTRIC_ASPIRATE_MAP: Dict[str, str] = {
    "not done": "Not done",
    "none": "Not done",
    "clear": "Clear",
    "meconium stained": "Meconium Stained",
    "meconium": "Meconium Stained",
    "blood stained": "Blood Stained",
    "bilious": "Bilious",
    "nil": "Nil",
}

COMMENT_ON_LIQUOR_MAP: Dict[str, str] = {
    "clear": "Clear",
    "meconium stained": "Meconium Stained",
    "meconium": "Meconium Stained",
    "msl": "Meconium Stained",
    "blood stained": "Blood Stained",
    "foul smelling": "Foul Smelling",
    "foul": "Foul Smelling",
}

STEROID_TYPE_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "none": "N/A",
    "dexa": "Dexa",
    "dexamethasone": "Dexa",
    "beta": "Beta",
    "betamethasone": "Beta",
}

STEROID_COURSE_MAP: Dict[str, str] = {
    "complete": "Complete",
    "partial/incomplete": "Partial/Incomplete",
    "partial": "Partial/Incomplete",
    "incomplete": "Partial/Incomplete",
    "multiple": "Multiple",
}

LAST_DOSE_INTERVAL_MAP: Dict[str, str] = {
    "< 24 hrs": "< 24 hrs",
    "less than 24 hrs": "< 24 hrs",
    "less than 24 hours": "< 24 hrs",
    "<24 hrs": "< 24 hrs",
    "24 hrs - 7 days": "24 hrs - 7 days",
    "24hrs - 7days": "24 hrs - 7 days",
    "24 hours to 7 days": "24 hrs - 7 days",
    "> 7 days": "> 7 days",
    "more than 7 days": "> 7 days",
    ">7 days": "> 7 days",
}

NATURE_OF_LABOUR_MAP: Dict[str, str] = {
    "spontaneous": "Spontaneous",
    "induced": "Induced",
}

DURATION_OF_PROM_MAP: Dict[str, str] = {
    "less than 6 hrs": "Less than 6 hrs",
    "< 6 hrs": "Less than 6 hrs",
    "<6 hrs": "Less than 6 hrs",
    "less than 6 hours": "Less than 6 hrs",
    "6 - 12": "6 - 12",
    "6-12": "6 - 12",
    "6 to 12": "6 - 12",
    "12 - 18": "12 - 18",
    "12-18": "12 - 18",
    "12 to 18": "12 - 18",
    "18 - 24": "18 - 24",
    "18-24": "18 - 24",
    "18 to 24": "18 - 24",
    "more than 24": "More than 24",
    "> 24": "More than 24",
    ">24": "More than 24",
    "more than 24 hrs": "More than 24",
    "more than 24 hours": "More than 24",
    "unknown": "Unknown",
    "not known": "Unknown",
}

TIME_OF_LAST_DOSE_MAP: Dict[str, str] = {
    "less than 4 hours": "Less than 4 hours",
    "< 4 hours": "Less than 4 hours",
    "<4 hours": "Less than 4 hours",
    "less than 4 hrs": "Less than 4 hours",
    "more than 4 hours": "More than 4 hours",
    "> 4 hours": "More than 4 hours",
    ">4 hours": "More than 4 hours",
    "more than 4 hrs": "More than 4 hours",
    "unknown": "Unknown",
    "not known": "Unknown",
}


# ============================================================================
# DOSE / ROUTE / EQUIPMENT ENUMS
# ============================================================================

VITAMIN_K_DOSE_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "none": "N/A",
    "1 mg": "1 mg",
    "1mg": "1 mg",
    "0.5 mg": "0.5 mg",
    "0.5mg": "0.5 mg",
}

VITAMIN_K_ROUTE_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "none": "N/A",
    "im": "IM",
    "intramuscular": "IM",
    "iv": "IV",
    "intravenous": "IV",
    "oral": "Oral",
    "po": "Oral",
}

ICT_DCT_MAP: Dict[str, str] = {
    "not done": "Not done",
    "none": "Not done",
    "positive": "Positive",
    "negative": "Negative",
    "not indicated": "Not indicated",
}

ETT_SIZE_MAP: Dict[str, str] = {
    "0": "0",
    "none": "0",
    "n/a": "0",
    "na": "0",
    "2": "2.0",
    "2.0": "2.0",
    "2.5": "2.5",
    "3": "3.0",
    "3.0": "3.0",
    "3.5": "3.5",
    "4": "4.0",
    "4.0": "4.0",
}

UNKNOWN_KNOWN_MAP: Dict[str, str] = {
    "unknown": "Unknown",
    "known": "Known",
}


# ============================================================================
# TRISOMY RISK — passthrough unless it matches a known keyword
# ============================================================================

TRISOMY_RISK_KEYWORDS: Dict[str, str] = {
    "not done": "Not Done",
    "not indicated": "Not Indicated",
    "others": "Others",
    "other": "Others",
}


# ============================================================================
# YES/NO FIELD LISTS
# ============================================================================

# Type A: Yes / No (default "No")
YES_NO_FIELDS = [
    "consanguinity", "booked", "supervised", "multiplePregnancy",
    "pregnancyComplications", "antenatalSteroids", "labour",
    "maternalPyrexia", "PROM", "malformation",
    "facialOxygen", "resuscitation", "deliveryRoomCPAP",
    "bagMaskVentilation", "bagMaskVentilationDuration",
    "intubation", "PPV", "durationOfPTV", "CPR", "durationOfCPR", "drugs",
]

# Type B: N/A / No / Yes (default "N/A")
NA_YES_NO_FIELDS = [
    "antenatalMgSO4ForNeuroprotection", "initialSteps",
    "riskFactorsForSepsisInMothers", "umbilicalCordMilking",
    "cutCordMilking",
]

# Type C: Not known / No / Yes (default "Not known")
NOT_KNOWN_YES_NO_FIELDS = [
    "maternalAntibiotics", "fetalDistress", "vitaminK",
]


# ============================================================================
# INTEGER ID MAPS — Complication text → ID
# ============================================================================

COMPLICATION_TEXT_TO_ID: Dict[str, int] = {
    "gdm": 1,
    "gestational diabetes": 1,
    "gestational diabetes mellitus": 39,
    "cholestasis": 2,
    "eclampsia": 3,
    "urinary tract infection": 6,
    "uti": 6,
    "pih": 7,
    "pregnancy induced hypertension": 7,
    "gestational hypertension": 49,
    "oligohydramnios": 8,
    "placenta previa": 9,
    "fetal growth restriction": 10,
    "iugr": 10,
    "fgr": 10,
    "maternal fever": 11,
    "fever": 11,
    "preterm prolonged rupture of membranes": 12,
    "pprom": 12,
    "polyhydramnios": 13,
    "antepartum haemorrhage": 14,
    "antepartum hemorrhage": 14,
    "aph": 14,
    "preterm rupture of membranes": 15,
    "prom": 21,
    "abruptio placenta": 16,
    "abruption": 16,
    "placental abruption": 16,
    "pre eclampsia": 17,
    "pre-eclampsia": 17,
    "preeclampsia": 17,
    "reduced fetal movements": 18,
    "decreased fetal movement": 18,
    "cord prolapse": 19,
    "anaemia": 20,
    "anemia": 40,
    "meconium stained liquor": 22,
    "msl": 22,
    "preterm labour": 23,
    "preterm labor": 23,
    "herpes vaginalis": 24,
    "renal failure": 25,
    "hypothyroidism": 26,
    "rh iso immunised pregnancy": 27,
    "rh isoimmunisation": 27,
    "preterm preeclampsia": 28,
    "preterm pre-eclampsia": 28,
    "rh negative pregnancy": 29,
    "prolonged rupture of membranes": 30,
    "hellp syndrome": 31,
    "hellp": 31,
    "gestational thrombocytopenia": 32,
    "shoulder dystocia": 33,
    "preeclampsia": 34,
    "cervical incompetence": 35,
    "cord around the neck": 36,
    "nuchal cord": 36,
    "pulmonary hypertension": 38,
    "varicella": 41,
    "maternal heart disease": 42,
    "fibroid complicating pregnancy": 43,
    "cardiomyopathy": 44,
    "sickle cell disease": 45,
    "aflp": 46,
    "prolonged labour": 47,
    "elderly pregnancy": 50,
    "ivf conception": 51,
    "complicated uti": 54,
    "anhydramnios": 55,
    "hyperemesis gravidarum": 57,
    "peripartum cardiomyopathy": 58,
}


# ============================================================================
# INTEGER ID MAPS — Maternal Medical Problem text → ID
# ============================================================================

MATERNAL_PROBLEM_TEXT_TO_ID: Dict[str, int] = {
    # Cardiac conditions
    "rhd": 1,
    "rheumatic heart disease": 1,
    "mitral valve prolapse": 64,
    "mvp": 64,
    "bicuspid aortic valve": 84,
    "aortic valve replacement": 34,
    "mitral valve replacement": 34,
    # Hypertension
    "chronic hypertension": 2,
    "chronic htn": 2,
    "essential hypertension": 2,
    "pih": 24,
    "pregnancy induced hypertension": 24,
    "gestational hypertension": 85,
    # Diabetes
    "type 1 dm": 3,
    "type 1 diabetes": 3,
    "t1dm": 3,
    "insulin dependent diabetes": 3,
    "type 2 dm": 4,
    "type 2 diabetes": 4,
    "t2dm": 4,
    "non-insulin dependent diabetes": 4,
    "overt diabetes": 37,
    "pre-existing diabetes": 37,
    "gdm": 55,
    "gestational diabetes": 55,
    "gestational diabetes mellitus": 55,
    # Thyroid
    "hypothyroidism": 5,
    "low thyroid": 5,
    "underactive thyroid": 5,
    "hyperthyroidism": 93,
    "thyroid disorder": 23,
    "thyroid disorders": 23,
    "autoimmune thyroiditis": 49,
    "hashimoto's": 49,
    # Infections
    "uti": 6,
    "urinary tract infection": 6,
    "tb": 11,
    "tuberculosis": 11,
    "pulmonary tb": 11,
    "syphilis": 12,
    "viral hepatitis": 13,
    "hepatitis": 13,
    "hepatitis c positive": 71,
    "septicemia": 14,
    "varicella": 15,
    "chickenpox": 15,
    "herpes vaginalis": 28,
    "genital herpes": 28,
    "retroviral disease": 27,
    "hiv positive": 27,
    "covid 19": 62,
    "covid-19": 62,
    "covid infection": 62,
    # Kidney
    "chronic renal failure": 7,
    "crf": 7,
    "chronic kidney disease": 7,
    "ckd": 7,
    # Blood disorders
    "anemia": 8,
    "anaemia": 8,
    "low hemoglobin": 8,
    "thalassemia trait": 54,
    "thalassemic trait": 54,
    "thalassemia minor": 54,
    "beta thalassemic trait": 68,
    "sickle cell disease": 90,
    "scd": 90,
    "itp": 30,
    "idiopathic thrombocytopenic purpura": 30,
    "gestational thrombocytopenia": 63,
    "thrombocytopenia": 41,
    # Respiratory
    "bronchial asthma": 9,
    "asthma": 9,
    "pulmonary hypertension": 77,
    "pah": 77,
    # Neurological
    "epilepsy": 10,
    "seizure disorder": 10,
    "multiple sclerosis": 32,
    # Autoimmune
    "sle": 16,
    "systemic lupus erythematosus": 16,
    "lupus": 16,
    "apla": 65,
    "antiphospholipid antibody": 65,
    "apla syndrome": 39,
    "antiphospholipid antibody syndrome": 39,
    "aps": 39,
    "rheumatoid arthritis": 86,
    "ra": 86,
    "ana positive": 70,
    "ana positivity": 60,
    # Gynecological
    "pcod": 33,
    "pcos": 33,
    "polycystic ovarian": 33,
    "endometriosis": 57,
    "adenomyosis": 58,
    "cervical incompetence": 69,
    "unicornuate uterus": 66,
    # Mental health
    "depression": 38,
    "depressive disorder": 38,
    # Other
    "obesity": 45,
    "obese": 45,
    "dyslipidemia": 73,
    "vitamin b12 deficiency": 40,
}


def convert_maternal_problem_to_id(value: Any) -> Union[int, str, None]:
    """
    Convert maternal medical problem text to integer ID.
    Passes through if already an int or unrecognized.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    val_str = str(value).strip()
    if val_str.isdigit():
        return int(val_str)
    val_lower = val_str.lower()
    if val_lower in MATERNAL_PROBLEM_TEXT_TO_ID:
        return MATERNAL_PROBLEM_TEXT_TO_ID[val_lower]
    # Passthrough unrecognized text
    logger.warning(f"Unrecognized maternal problem text: '{val_str}', passing through")
    return val_str


# ============================================================================
# NESTED OBJECT MAPS — liveBirthBabyDetails, pregnancyComplicationsDetails
# ============================================================================

TYPE_OF_DELIVERY_MAP: Dict[str, str] = {
    "vaginal": "Vaginal",
    "normal vaginal": "Vaginal",
    "nvd": "Vaginal",
    "lscs": "LSCS",
    "caesarian": "LSCS",
    "cesarean": "LSCS",
    "caesarean": "LSCS",
    "c-section": "LSCS",
    "c section": "LSCS",
    "instrumental": "Instrumental",
    "forceps": "Instrumental",
    "ventouse": "Instrumental",
    "breech": "Breech",
}

HEALTH_MAP: Dict[str, str] = {
    "alive": "Alive",
    "living": "Alive",
    "died": "Died",
    "dead": "Died",
    "expired": "Died",
    "unhealthy": "Unhealthy",
    "sick": "Unhealthy",
}

DURATION_TYPE_MAP: Dict[str, str] = {
    "days": "days",
    "day": "days",
    "weeks": "weeks",
    "week": "weeks",
    "month": "month",
    "months": "month",
}


# ============================================================================
# NORMALIZER FUNCTIONS
# ============================================================================

def _lookup(value: Any, lookup_map: Dict[str, str], default: Optional[str] = None) -> Optional[str]:
    """Generic lookup: lowercase strip and match against map. Returns original if no match and no default."""
    if value is None:
        return default
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in lookup_map:
        return lookup_map[val_lower]
    # Check if already a valid value (case-insensitive)
    valid_values_lower = {v.lower(): v for v in set(lookup_map.values())}
    if val_lower in valid_values_lower:
        return valid_values_lower[val_lower]
    if default is not None:
        return default
    return val_str  # passthrough if no default


def normalize_birth_status(value: Any) -> Optional[str]:
    return _lookup(value, BIRTH_STATUS_MAP)


def normalize_sex(value: Any) -> Optional[str]:
    return _lookup(value, SEX_MAP)


def normalize_blood_group(value: Any) -> Optional[str]:
    return _lookup(value, BLOOD_GROUP_MAP, default="Not Known")


def normalize_birth_order(value: Any) -> Optional[str]:
    return _lookup(value, BIRTH_ORDER_MAP, default="Singleton")


def normalize_transfer_status(value: Any) -> Optional[str]:
    return _lookup(value, TRANSFER_STATUS_MAP)


def normalize_conception(value: Any) -> Optional[str]:
    return _lookup(value, CONCEPTION_MAP, default="Not Known")


def normalize_hiv(value: Any) -> Optional[str]:
    return _lookup(value, HIV_MAP, default="Unknown")


def normalize_vdrl(value: Any) -> Optional[str]:
    return _lookup(value, VDRL_MAP, default="Unknown")


def normalize_mode_of_delivery(value: Any) -> Optional[str]:
    return _lookup(value, MODE_OF_DELIVERY_MAP)


def normalize_presentation(value: Any) -> Optional[str]:
    return _lookup(value, PRESENTATION_MAP, default="Not Known")


def normalize_ctg(value: Any) -> Optional[str]:
    return _lookup(value, CTG_MAP, default="Not Known")


def normalize_cord_blood_gas(value: Any) -> Optional[str]:
    return _lookup(value, CORD_BLOOD_GAS_MAP, default="Not done")


def normalize_gastric_aspirate(value: Any) -> Optional[str]:
    return _lookup(value, GASTRIC_ASPIRATE_MAP, default="Not done")


def normalize_comment_on_liquor(value: Any) -> Optional[str]:
    return _lookup(value, COMMENT_ON_LIQUOR_MAP)


def normalize_steroid_type(value: Any) -> Optional[str]:
    return _lookup(value, STEROID_TYPE_MAP, default="N/A")


def normalize_steroid_course(value: Any) -> Optional[str]:
    return _lookup(value, STEROID_COURSE_MAP)


def normalize_last_dose_interval(value: Any) -> Optional[str]:
    return _lookup(value, LAST_DOSE_INTERVAL_MAP)


def normalize_nature_of_labour(value: Any) -> Optional[str]:
    return _lookup(value, NATURE_OF_LABOUR_MAP)


def normalize_duration_of_prom(value: Any) -> Optional[str]:
    return _lookup(value, DURATION_OF_PROM_MAP, default="Unknown")


def normalize_time_of_last_dose(value: Any) -> Optional[str]:
    return _lookup(value, TIME_OF_LAST_DOSE_MAP, default="Unknown")


def normalize_vitamin_k_dose(value: Any) -> Optional[str]:
    return _lookup(value, VITAMIN_K_DOSE_MAP, default="N/A")


def normalize_vitamin_k_route(value: Any) -> Optional[str]:
    return _lookup(value, VITAMIN_K_ROUTE_MAP, default="N/A")


def normalize_ict_dct(value: Any) -> Optional[str]:
    return _lookup(value, ICT_DCT_MAP, default="Not done")


def normalize_ett_size(value: Any) -> Optional[str]:
    if value is None:
        return "0"
    val_str = str(value).strip().lower()
    if val_str in ETT_SIZE_MAP:
        return ETT_SIZE_MAP[val_str]
    return "0"


def normalize_unknown_known(value: Any) -> str:
    return _lookup(value, UNKNOWN_KNOWN_MAP, default="Unknown")


# --- Yes/No variants ---

def normalize_yes_no(value: Any) -> str:
    """Type A: Yes / No (default No)."""
    if value is None:
        return "No"
    val_str = str(value).strip().lower()
    if val_str in ("yes", "true", "1", "y"):
        return "Yes"
    if val_str in ("no", "false", "0", "n", ""):
        return "No"
    return "No"


def normalize_na_yes_no(value: Any) -> str:
    """Type B: N/A / No / Yes (default N/A)."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in ("yes", "true", "1", "y"):
        return "Yes"
    if val_str in ("no", "false", "0", "n"):
        return "No"
    if val_str in ("n/a", "na", "none", ""):
        return "N/A"
    return "N/A"


def normalize_not_known_yes_no(value: Any) -> str:
    """Type C: Not known / No / Yes (default Not known)."""
    if value is None:
        return "Not known"
    val_str = str(value).strip().lower()
    if val_str in ("yes", "true", "1", "y"):
        return "Yes"
    if val_str in ("no", "false", "0", "n"):
        return "No"
    if val_str in ("not known", "unknown", ""):
        return "Not known"
    return "Not known"


def normalize_unknown_yes_no(value: Any) -> str:
    """Type D: Unknown / No / Yes (default Unknown)."""
    if value is None:
        return "Unknown"
    val_str = str(value).strip().lower()
    if val_str in ("yes", "true", "1", "y"):
        return "Yes"
    if val_str in ("no", "false", "0", "n"):
        return "No"
    if val_str in ("unknown", "not known", ""):
        return "Unknown"
    return "Unknown"


# --- Trisomy risk ---

def normalize_trisomy_risk(value: Any) -> Optional[str]:
    """Normalize trisomy risk: known keywords map, otherwise passthrough the value."""
    if value is None:
        return "Not Done"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in TRISOMY_RISK_KEYWORDS:
        return TRISOMY_RISK_KEYWORDS[val_lower]
    # Passthrough actual risk values (e.g. "1:250", "1 in 10000")
    return val_str


# --- Gestation cleanup ---

def strip_gestation_suffix(value: Any) -> Optional[str]:
    """Strip 'weeks'/'wks'/'week' suffix from gestation values. '32 weeks' -> '32'."""
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return val_str
    cleaned = re.sub(r'\s*(weeks?|wks)\s*$', '', val_str, flags=re.IGNORECASE).strip()
    return cleaned


# --- Complication text-to-ID converter ---

def convert_complication_to_id(value: Any) -> Union[int, str, None]:
    """Convert complication text to integer ID. Passes through if already an int or unrecognized."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    val_str = str(value).strip()
    if val_str.isdigit():
        return int(val_str)
    val_lower = val_str.lower()
    if val_lower in COMPLICATION_TEXT_TO_ID:
        return COMPLICATION_TEXT_TO_ID[val_lower]
    # Passthrough unrecognized text
    logger.warning(f"Unrecognized complication text: '{val_str}', passing through")
    return val_str


# --- Nested object normalizers ---

def normalize_type_of_delivery(value: Any) -> Optional[str]:
    return _lookup(value, TYPE_OF_DELIVERY_MAP)


def normalize_health(value: Any) -> Optional[str]:
    return _lookup(value, HEALTH_MAP)


def normalize_duration_type(value: Any) -> Optional[str]:
    return _lookup(value, DURATION_TYPE_MAP)


# ============================================================================
# MASTER FUNCTION
# ============================================================================

def apply_raster_lookups_to_neo_proforma(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply all Raster lookup transformations to a NEO_PROFORMA payload.

    Normalizes enum fields, Yes/No fields, gestation suffixes, complication
    text-to-ID conversion, and nested object enums.
    """
    # 1. String enums (top-level fields) — only normalize if field exists
    _normalize_field(payload, "birthStatus", normalize_birth_status)
    _normalize_field(payload, "sex", normalize_sex)
    _normalize_field(payload, "babyBloodGroup", normalize_blood_group)
    _normalize_field(payload, "motherBloodGroup", normalize_blood_group)
    _normalize_field(payload, "birthOrder", normalize_birth_order)
    _normalize_field(payload, "transferStatus", normalize_transfer_status)
    _normalize_field(payload, "conception", normalize_conception)
    _normalize_field(payload, "HIV", normalize_hiv)
    _normalize_field(payload, "VDRL", normalize_vdrl)
    _normalize_field(payload, "modeOfDelivery", normalize_mode_of_delivery)
    _normalize_field(payload, "presentation", normalize_presentation)
    _normalize_field(payload, "CTG", normalize_ctg)
    _normalize_field(payload, "cordBloodGas", normalize_cord_blood_gas)
    _normalize_field(payload, "typeofAnesthesia", normalize_cord_blood_gas)  # same enum
    _normalize_field(payload, "gastricAspirate", normalize_gastric_aspirate)
    _normalize_field(payload, "commentOnLiquor", normalize_comment_on_liquor)
    _normalize_field(payload, "typeOfSteriods", normalize_steroid_type)
    _normalize_field(payload, "steroidCourse", normalize_steroid_course)
    _normalize_field(payload, "lastDoseDeliveryInterval", normalize_last_dose_interval)
    _normalize_field(payload, "natureofLabour", normalize_nature_of_labour)
    _normalize_field(payload, "durationOfPROM", normalize_duration_of_prom)
    _normalize_field(payload, "timeOfLastDose", normalize_time_of_last_dose)

    # 2. Dose/Route/Equipment
    _normalize_field(payload, "vitaminKDose", normalize_vitamin_k_dose)
    _normalize_field(payload, "vitaminKRoute", normalize_vitamin_k_route)
    _normalize_field(payload, "ICT", normalize_ict_dct)
    _normalize_field(payload, "DCT", normalize_ict_dct)
    _normalize_field(payload, "ETTSizeInMM", normalize_ett_size)
    _normalize_field(payload, "regularRespiration", normalize_unknown_known)
    _normalize_field(payload, "depthOfInsertion", normalize_unknown_known)

    # 3. Yes/No fields (Type A)
    for field in YES_NO_FIELDS:
        if field in payload:
            payload[field] = normalize_yes_no(payload[field])

    # 4. N/A/Yes/No fields (Type B)
    for field in NA_YES_NO_FIELDS:
        if field in payload:
            payload[field] = normalize_na_yes_no(payload[field])

    # 5. Not known/Yes/No fields (Type C)
    for field in NOT_KNOWN_YES_NO_FIELDS:
        if field in payload:
            payload[field] = normalize_not_known_yes_no(payload[field])

    # 6. Unknown/Yes/No (Type D)
    _normalize_field(payload, "delayedCordClamping", normalize_unknown_yes_no)

    # 7. Trisomy risk fields
    for field in ["adjustedRiskForTrisomy21", "adjustedRiskForTrisomy18", "adjustedRiskForTrisomy13"]:
        if field in payload:
            payload[field] = normalize_trisomy_risk(payload[field])

    # 8. Gestation cleanup — strip "weeks" suffix
    if "gestationWeeks" in payload:
        payload["gestationWeeks"] = strip_gestation_suffix(payload["gestationWeeks"])

    for scan_key in ["datingScanDetails", "anomalyScanDetails"]:
        if scan_key in payload and isinstance(payload[scan_key], dict):
            if "gestation" in payload[scan_key]:
                payload[scan_key]["gestation"] = strip_gestation_suffix(payload[scan_key]["gestation"])

    for scan_key in ["otherScanDetails", "dopplerScanDetails"]:
        if scan_key in payload and isinstance(payload[scan_key], list):
            for scan in payload[scan_key]:
                if isinstance(scan, dict) and "gestation" in scan:
                    scan["gestation"] = strip_gestation_suffix(scan["gestation"])

    # 9. liveBirthBabyDetails nested normalization
    if "liveBirthBabyDetails" in payload and isinstance(payload["liveBirthBabyDetails"], list):
        for birth in payload["liveBirthBabyDetails"]:
            if isinstance(birth, dict):
                _normalize_field(birth, "typeOfDelivery", normalize_type_of_delivery)
                _normalize_field(birth, "health", normalize_health)

    # 10. pregnancyComplicationsDetails — complicationId text→ID + durationType
    if "pregnancyComplicationsDetails" in payload and isinstance(payload["pregnancyComplicationsDetails"], list):
        for comp in payload["pregnancyComplicationsDetails"]:
            if isinstance(comp, dict):
                if "complicationId" in comp:
                    comp["complicationId"] = convert_complication_to_id(comp["complicationId"])
                _normalize_field(comp, "durationType", normalize_duration_type)
                _capitalize_fields(comp, ["treatment"])

    # 11. Sentence capitalization — free-text narrative fields
    _capitalize_fields(payload, [
        "initialExaminationSummary", "backgroundDetails", "plan",
        "CTGDetails", "otherInvestigations",
    ])

    # Scan findings
    for scan_key in ["datingScanDetails", "anomalyScanDetails"]:
        if scan_key in payload and isinstance(payload[scan_key], dict):
            _capitalize_fields(payload[scan_key], ["findings"])

    for scan_key in ["otherScanDetails", "dopplerScanDetails"]:
        if scan_key in payload and isinstance(payload[scan_key], list):
            for scan in payload[scan_key]:
                if isinstance(scan, dict):
                    _capitalize_fields(scan, ["findings"])

    # liveBirthBabyDetails free-text
    if "liveBirthBabyDetails" in payload and isinstance(payload["liveBirthBabyDetails"], list):
        for birth in payload["liveBirthBabyDetails"]:
            if isinstance(birth, dict):
                _capitalize_fields(birth, ["complications", "details"])

    # medicalProblem — maternal problem ID validation + medications text capitalization
    if "medicalProblem" in payload and isinstance(payload["medicalProblem"], list):
        for prob in payload["medicalProblem"]:
            if isinstance(prob, dict):
                # Validate/convert problemsId using maternal problem lookup
                if "problemsId" in prob:
                    prob["problemsId"] = convert_maternal_problem_to_id(prob["problemsId"])
                # Capitalize medications text
                _capitalize_fields(prob, ["medications"])

    return payload


def _normalize_field(obj: Dict[str, Any], field: str, normalizer) -> None:
    """Normalize a field in-place only if it exists in the object."""
    if field in obj:
        obj[field] = normalizer(obj[field])

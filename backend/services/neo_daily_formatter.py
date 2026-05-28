"""
NEO_DAILY Formatter Service - RASTER FORMAT

Reconstructs nested structure from flattened Gemini extraction results.
Converts flat schema output to the Raster API expected format.

Supports:
1. Two-part extraction (Part 1: General/Respiratory/CVS, Part 2: GI/CNS/etc.)
2. Single flattened extraction (legacy compatibility)

Final output structure matches Raster API:
{
    "uhid": "...",
    "dailyLog": {
        "date": "...",
        "time": "...",
        "dayOfLife": 10,
        "careType": "...",
        "seenBy": [...],
        "background": "...",
        "problems": {"current": [...], "previous": [...]},
        "respiratory": {...},
        "cvs": {...},
        "gi": {...},
        "cns": {...},
        "sepsis": {...},
        "renalMetabolic": {...},
        "invasiveLines": {...},
        "inotropes": {...},
        "skin": {...},
        "rop": {...}
    },
    "antibiotics": [...],
    "transfusions": [...],
    "fluids": [...]
}
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS FOR RASTER API FORMAT
# ============================================================================

def _format_antibiotics_for_raster(antibiotics_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format antibiotics array to match Raster API expected structure.

    Raster expects: { drugId: int, dose: str, frequency: str, route: str }
    We extract: { drugName: str, dose: str, frequency: str, route: str }

    Priority for drugId:
    1. _external_id from medicine list post-processing (resolved from doctor's list)
    2. drugId from extraction (if Gemini extracted an ID)
    3. Sequential fallback (idx + 1)
    """
    formatted = []
    for idx, antibiotic in enumerate(antibiotics_list):
        if not isinstance(antibiotic, dict):
            continue

        # Prefer _external_id (resolved from doctor's medicine list) over sequential fallback
        drug_id = antibiotic.get("_external_id") or antibiotic.get("drugId") or idx + 1

        formatted_item = {
            "drugId": drug_id,
            "drugName": antibiotic.get("drugName", ""),  # Keep name for reference
            "dose": antibiotic.get("dose", ""),
            "frequency": antibiotic.get("frequency", ""),
            "route": antibiotic.get("route", "IV"),  # Default to IV if not specified
        }
        formatted.append(formatted_item)

    return formatted


def _format_transfusions_for_raster(transfusions_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format transfusions array to match Raster API expected structure.

    Raster expects: { product: str, volume: number }
    """
    formatted = []
    for transfusion in transfusions_list:
        if not isinstance(transfusion, dict):
            continue

        formatted_item = {
            "product": transfusion.get("product", ""),
            "volume": transfusion.get("volume"),
        }
        formatted.append(formatted_item)

    return formatted


def _format_fluids_for_raster(fluids_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format fluids array to match Raster API expected structure.

    Raster expects: { fluidId: int, rate: str, duration: str }
    We extract: { fluidName: str, rate: str, duration: str }
    """
    formatted = []
    for idx, fluid in enumerate(fluids_list):
        if not isinstance(fluid, dict):
            continue

        formatted_item = {
            "fluidId": fluid.get("fluidId") or idx + 1,  # Use extracted ID or generate sequential
            "fluidName": fluid.get("fluidName", ""),  # Keep name for reference
            "rate": fluid.get("rate", ""),
            "duration": fluid.get("duration", ""),
        }
        formatted.append(formatted_item)

    return formatted


def _clean_empty_objects(obj: Dict[str, Any], parent_key: str = "") -> Dict[str, Any]:
    """
    Clean empty nested objects by setting them to None or removing them.

    Empty objects like {} can cause issues when Raster tries to access their properties.
    """
    if not isinstance(obj, dict):
        return obj

    cleaned = {}
    for key, value in obj.items():
        if isinstance(value, dict):
            if not value:  # Empty dict {}
                # For nested objects like echo, liver, spleen - set to None instead of empty dict
                cleaned[key] = None
            else:
                cleaned[key] = _clean_empty_objects(value, key)
        elif isinstance(value, list):
            cleaned[key] = value
        else:
            cleaned[key] = value

    return cleaned


def format_neo_daily_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge and reconstruct NEO_DAILY from two-part extraction.

    Args:
        part1_data: Part 1 extraction (Patient + General + Respiratory + CVS)
        part2_data: Part 2 extraction (GI + CNS + Sepsis + Renal + Lines + Inotropes + Skin + ROP + Arrays)

    Returns:
        Nested structure matching Raster API format
    """
    try:
        logger.info("[NEO_DAILY_FORMATTER_SPLIT] Starting merge of Part 1 and Part 2 extractions")

        # Merge both parts into a single flat dictionary
        merged_flat = {**part1_data, **part2_data}

        logger.info(
            f"[NEO_DAILY_FORMATTER_SPLIT] Merged {len(part1_data)} fields from Part 1 + "
            f"{len(part2_data)} fields from Part 2 = {len(merged_flat)} total fields"
        )

        # Use the formatter to reconstruct nested structure
        nested_result = format_neo_daily(merged_flat)

        logger.info("[NEO_DAILY_FORMATTER_SPLIT] Two-part merge complete")

        return nested_result

    except Exception as e:
        logger.error(f"[NEO_DAILY_FORMATTER_SPLIT] Merge failed: {e}", exc_info=True)
        # Return merged flat data as fallback
        return {**part1_data, **part2_data}


def format_neo_daily(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested NEO_DAILY structure from flattened extraction.

    Converts flattened field names to the Raster API nested format.

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching Raster API format
    """
    try:
        logger.info("[NEO_DAILY_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== TOP-LEVEL FIELDS ==========
        nested["uhid"] = flat_data.get("uhid", "")

        # ========== DAILY LOG NESTED STRUCTURE ==========
        daily_log = {}

        # ---------- GENERAL FIELDS ----------
        daily_log["date"] = flat_data.get("dailyLog_date", "")
        daily_log["time"] = flat_data.get("dailyLog_time", "")
        daily_log["dayOfLife"] = flat_data.get("dailyLog_dayOfLife")
        daily_log["careType"] = flat_data.get("dailyLog_careType", "")
        daily_log["seenBy"] = flat_data.get("dailyLog_seenBy", [])
        daily_log["background"] = flat_data.get("dailyLog_background", "")
        daily_log["problems"] = {
            "current": flat_data.get("dailyLog_problems_current", []),
            "previous": flat_data.get("dailyLog_problems_previous", [])
        }

        # ---------- RESPIRATORY SECTION ----------
        daily_log["respiratory"] = {
            "support": flat_data.get("respiratory_support", ""),
            "ventOption": flat_data.get("respiratory_ventOption", ""),
            "fiO2": flat_data.get("respiratory_fiO2"),
            "fiO2Delivered": flat_data.get("respiratory_fiO2Delivered"),
            "peep": flat_data.get("respiratory_peep"),
            "pip": flat_data.get("respiratory_pip"),
            "pipDelivered": flat_data.get("respiratory_pipDelivered"),
            "map": flat_data.get("respiratory_map"),
            "frequency": flat_data.get("respiratory_frequency"),
            "ieRatio": flat_data.get("respiratory_ieRatio", ""),
            "amplitude": flat_data.get("respiratory_amplitude"),
            "airEntry": flat_data.get("respiratory_airEntry", ""),
            "retractions": flat_data.get("respiratory_retractions", ""),
            "chestMovement": flat_data.get("respiratory_chestMovement", ""),
            "addedSounds": flat_data.get("respiratory_addedSounds", ""),
            "findings": flat_data.get("respiratory_findings", ""),
            "volumeTargeting": flat_data.get("respiratory_volumeTargeting", False),
            "claco": flat_data.get("respiratory_claco", False),
            "dayOfVentilation": flat_data.get("respiratory_dayOfVentilation"),
            "spontaneouslyVentilating": flat_data.get("respiratory_spontaneouslyVentilating", False),
            "etTube": flat_data.get("respiratory_etTube", ""),
            "size": flat_data.get("respiratory_size"),
            "lips": flat_data.get("respiratory_lips"),
            "flow": flat_data.get("respiratory_flow"),
            "it": flat_data.get("respiratory_it"),
            "aaDO2": flat_data.get("respiratory_aaDO2"),
            "bloodGas": {
                "ph": flat_data.get("respiratory_bloodGas_ph"),
                "paO2": flat_data.get("respiratory_bloodGas_paO2"),
                "paCo2": flat_data.get("respiratory_bloodGas_paCo2"),
                "hco3": flat_data.get("respiratory_bloodGas_hco3"),
                "be": flat_data.get("respiratory_bloodGas_be"),
                "lactate": flat_data.get("respiratory_bloodGas_lactate")
            },
            "additionalIcd": flat_data.get("respiratory_additionalIcd", [])
        }

        # ---------- CVS SECTION ----------
        daily_log["cvs"] = {
            "hr": flat_data.get("cvs_hr"),
            "systolicBp": flat_data.get("cvs_systolicBp"),
            "diastolicBp": flat_data.get("cvs_diastolicBp"),
            "meanBP": flat_data.get("cvs_meanBP"),
            "pulsePressure": flat_data.get("cvs_pulsePressure"),
            "centralPulses": flat_data.get("cvs_centralPulses", ""),
            "peripheralPulses": flat_data.get("cvs_peripheralPulses", ""),
            "femoralPulses": flat_data.get("cvs_femoralPulses", ""),
            "precordialActivity": flat_data.get("cvs_precordialActivity", ""),
            "s1s2": flat_data.get("cvs_s1s2", ""),
            "murmur": flat_data.get("cvs_murmur", ""),
            "murmurCharacter": flat_data.get("cvs_murmurCharacter", ""),
            "cft": flat_data.get("cvs_cft", ""),
            "centralTemperature": flat_data.get("cvs_centralTemperature"),
            "peripheralTemperature": flat_data.get("cvs_peripheralTemperature"),
            "color": flat_data.get("cvs_color", ""),
            "findings": flat_data.get("cvs_findings", ""),
            "pda": flat_data.get("cvs_pda", ""),
            "pdaTreatment": flat_data.get("cvs_pdaTreatment", ""),
            "pah": flat_data.get("cvs_pah", ""),
            "pahTreatment": flat_data.get("cvs_pahTreatment", ""),
            "echo": {
                "status": flat_data.get("cvs_echo_status", ""),
                "day": flat_data.get("cvs_echo_day"),
                "report": flat_data.get("cvs_echo_report", "")
            },
            "additionalIcd": flat_data.get("cvs_additionalIcd", [])
        }

        # ---------- GI SECTION ----------
        daily_log["gi"] = {
            "abdomen": flat_data.get("gi_abdomen", ""),
            "bowelSounds": flat_data.get("gi_bowelSounds", ""),
            "girth": flat_data.get("gi_girth"),
            "stools": flat_data.get("gi_stools", False),
            "stoolNature": flat_data.get("gi_stoolNature", ""),
            "aspirateVolume": flat_data.get("gi_aspirateVolume", ""),
            "aspirateNature": flat_data.get("gi_aspirateNature", ""),
            "findings": flat_data.get("gi_findings", ""),
            "nec": flat_data.get("gi_nec", ""),
            "necTreatment": flat_data.get("gi_necTreatment", ""),
            "liver": {
                "status": flat_data.get("gi_liver_status", ""),
                "span": flat_data.get("gi_liver_span")
            },
            "spleen": {
                "status": flat_data.get("gi_spleen_status", ""),
                "span": flat_data.get("gi_spleen_span")
            },
            "umbilicus": flat_data.get("gi_umbilicus", ""),
            "hernia": flat_data.get("gi_hernia", ""),
            "genitalia": flat_data.get("gi_genitalia", ""),
            "nnj": {
                "status": flat_data.get("gi_nnj_status", ""),
                "tsb": flat_data.get("gi_nnj_tsb"),
                "treatment": flat_data.get("gi_nnj_treatment", "")
            },
            "nutrition": {
                "feeds": flat_data.get("gi_nutrition_feeds", ""),
                "volume": flat_data.get("gi_nutrition_volume"),
                "frequency": flat_data.get("gi_nutrition_frequency"),
                "workingWeight": flat_data.get("gi_nutrition_workingWeight"),
                "fullEnteralFeeds": flat_data.get("gi_nutrition_fullEnteralFeeds", ""),
                "ivFluids": flat_data.get("gi_nutrition_ivFluids", ""),
                "ivFluidsMlDay": flat_data.get("gi_nutrition_ivFluidsMlDay"),
                "tpn": flat_data.get("gi_nutrition_tpn", ""),
                "carbohydrates": flat_data.get("gi_nutrition_carbohydrates"),
                "protein": flat_data.get("gi_nutrition_protein"),
                "fat": flat_data.get("gi_nutrition_fat"),
                "totalEnergy": flat_data.get("gi_nutrition_totalEnergy"),
                "otherDrugs": flat_data.get("gi_nutrition_otherDrugs", "")
            },
            "immunoglobulins": flat_data.get("gi_immunoglobulins", ""),
            "additionalIcd": flat_data.get("gi_additionalIcd", [])
        }

        # ---------- CNS SECTION ----------
        daily_log["cns"] = {
            "anteriorFontanelle": flat_data.get("cns_anteriorFontanelle", ""),
            "activity": flat_data.get("cns_activity", ""),
            "tone": flat_data.get("cns_tone", ""),
            "cry": flat_data.get("cns_cry", ""),
            "seizures": flat_data.get("cns_seizures", ""),
            "typeOfSeizures": flat_data.get("cns_typeOfSeizures", ""),
            "reflexes": flat_data.get("cns_reflexes", ""),
            "pupils": flat_data.get("cns_pupils", ""),
            "findings": flat_data.get("cns_findings", ""),
            "headCircumference": flat_data.get("cns_headCircumference"),
            "therapeuticHypothermia": flat_data.get("cns_therapeuticHypothermia", ""),
            "sedationParalysis": flat_data.get("cns_sedationParalysis", ""),
            "neuroSonogram": flat_data.get("cns_neuroSonogram", ""),
            "ultrasoundSpine": flat_data.get("cns_ultrasoundSpine", ""),
            "mriCtBrain": flat_data.get("cns_mriCtBrain", ""),
            "eegCfm": {
                "status": flat_data.get("cns_eegCfm_status", ""),
                "report": flat_data.get("cns_eegCfm_report", "")
            },
            "additionalIcd": flat_data.get("cns_additionalIcd", [])
        }

        # ---------- SEPSIS SECTION ----------
        daily_log["sepsis"] = {
            "crp": flat_data.get("sepsis_crp"),
            "lumbarPuncture": flat_data.get("sepsis_lumbarPuncture", ""),
            "viralMeningitis": flat_data.get("sepsis_viralMeningitis", ""),
            "organisms": flat_data.get("sepsis_organisms", []),
            "additionalIcd": flat_data.get("sepsis_additionalIcd", [])
        }

        # ---------- RENAL/METABOLIC SECTION ----------
        daily_log["renalMetabolic"] = {
            "previousWeight": flat_data.get("renalMetabolic_previousWeight"),
            "currentWeight": flat_data.get("renalMetabolic_currentWeight"),
            "uo": flat_data.get("renalMetabolic_uo"),
            "bloodOut": flat_data.get("renalMetabolic_bloodOut"),
            "drainOutput": flat_data.get("renalMetabolic_drainOutput"),
            "gir": flat_data.get("renalMetabolic_gir"),
            "dilutionExchange": flat_data.get("renalMetabolic_dilutionExchange", ""),
            "rbs": flat_data.get("renalMetabolic_rbs"),
            "serumNa": flat_data.get("renalMetabolic_serumNa"),
            "serumK": flat_data.get("renalMetabolic_serumK"),
            "additionalIcd": flat_data.get("renalMetabolic_additionalIcd", [])
        }

        # ---------- INVASIVE LINES SECTION ----------
        daily_log["invasiveLines"] = {
            "pvc": {
                "status": flat_data.get("invasiveLines_pvc_status", ""),
                "number": flat_data.get("invasiveLines_pvc_number"),
                "site": flat_data.get("invasiveLines_pvc_site", ""),
                "day": flat_data.get("invasiveLines_pvc_day"),
                "dayChange": flat_data.get("invasiveLines_pvc_dayChange", False),
                "complication": flat_data.get("invasiveLines_pvc_complication", "")
            },
            "picc": {
                "status": flat_data.get("invasiveLines_picc_status", ""),
                "site": flat_data.get("invasiveLines_picc_site", ""),
                "day": flat_data.get("invasiveLines_picc_day"),
                "complication": flat_data.get("invasiveLines_picc_complication", "")
            },
            "uvc": {
                "status": flat_data.get("invasiveLines_uvc_status", ""),
                "position": flat_data.get("invasiveLines_uvc_position", ""),
                "day": flat_data.get("invasiveLines_uvc_day"),
                "complication": flat_data.get("invasiveLines_uvc_complication", "")
            },
            "uac": {
                "status": flat_data.get("invasiveLines_uac_status", ""),
                "position": flat_data.get("invasiveLines_uac_position", ""),
                "day": flat_data.get("invasiveLines_uac_day"),
                "complication": flat_data.get("invasiveLines_uac_complication", "")
            },
            "pac": {
                "status": flat_data.get("invasiveLines_pac_status", ""),
                "site": flat_data.get("invasiveLines_pac_site", ""),
                "day": flat_data.get("invasiveLines_pac_day"),
                "complication": flat_data.get("invasiveLines_pac_complication", "")
            }
        }

        # ---------- INOTROPES SECTION ----------
        daily_log["inotropes"] = {
            "status": flat_data.get("inotropes_status", ""),
            "dopamine": flat_data.get("inotropes_dopamine"),
            "dobutamine": flat_data.get("inotropes_dobutamine"),
            "adrenaline": flat_data.get("inotropes_adrenaline"),
            "noradrenaline": flat_data.get("inotropes_noradrenaline"),
            "milrinone": flat_data.get("inotropes_milrinone")
        }

        # ---------- SKIN SECTION ----------
        daily_log["skin"] = {
            "findings": flat_data.get("skin_findings", ""),
            "additionalIcd": flat_data.get("skin_additionalIcd", [])
        }

        # ---------- ROP SECTION ----------
        daily_log["rop"] = {
            "findings": flat_data.get("rop_findings", ""),
            "additionalIcd": flat_data.get("rop_additionalIcd", [])
        }

        # Clean empty nested objects (echo: {}, liver: {}, etc.)
        # These can cause issues when Raster tries to flatten them
        daily_log = _clean_empty_objects(daily_log)

        # Attach dailyLog to nested result
        nested["dailyLog"] = daily_log

        # ========== TOP-LEVEL ARRAYS ==========
        # These are outside dailyLog per Raster API spec
        # Format arrays to match Raster API expected structure
        nested["antibiotics"] = _format_antibiotics_for_raster(flat_data.get("antibiotics_list", []))
        nested["transfusions"] = _format_transfusions_for_raster(flat_data.get("transfusions_list", []))
        nested["fluids"] = _format_fluids_for_raster(flat_data.get("fluids_list", []))

        logger.info(
            f"[NEO_DAILY_FORMATTER] Reconstruction complete - "
            f"uhid: {nested.get('uhid', 'N/A')}, "
            f"sections in dailyLog: {len(daily_log)}, "
            f"antibiotics: {len(nested.get('antibiotics', []))}, "
            f"feeds: {daily_log.get('gi', {}).get('nutrition', {}).get('feeds', 'N/A')}"
        )

        return nested

    except Exception as e:
        logger.error(f"[NEO_DAILY_FORMATTER] Reconstruction failed: {e}", exc_info=True)
        # Return flat data as fallback
        return flat_data


def validate_neo_daily(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and clean NEO_DAILY extraction data.

    Ensures required fields are present and data types are correct.

    Args:
        data: Extraction data (nested or flat)

    Returns:
        Validated and cleaned data
    """
    try:
        # Check if already nested
        if "dailyLog" in data:
            daily_log = data.get("dailyLog", {})

            # Validate high priority fields
            gi = daily_log.get("gi", {})
            cvs = daily_log.get("cvs", {})
            respiratory = daily_log.get("respiratory", {})

            warnings = []

            # Check critical fields
            if not gi.get("nutrition", {}).get("feeds"):
                warnings.append("gi.nutrition.feeds is missing (CRITICAL for Raster API)")
            if cvs.get("hr") is None:
                warnings.append("cvs.hr (heart rate) is missing")
            if not respiratory.get("support"):
                warnings.append("respiratory.support is missing")

            if warnings:
                logger.warning(f"[NEO_DAILY_VALIDATOR] Missing fields: {', '.join(warnings)}")

        return data

    except Exception as e:
        logger.error(f"[NEO_DAILY_VALIDATOR] Validation failed: {e}", exc_info=True)
        return data


def flatten_neo_daily(nested_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested NEO_DAILY structure back to flat format.

    This is useful for database storage or when you need to merge
    user edits with the original extraction.

    Args:
        nested_data: Nested NEO_DAILY structure (Raster format)

    Returns:
        Flattened dictionary with prefixed field names
    """
    try:
        flat = {}

        # Top-level fields
        flat["uhid"] = nested_data.get("uhid", "")

        daily_log = nested_data.get("dailyLog", {})

        # General fields
        flat["dailyLog_date"] = daily_log.get("date", "")
        flat["dailyLog_time"] = daily_log.get("time", "")
        flat["dailyLog_dayOfLife"] = daily_log.get("dayOfLife")
        flat["dailyLog_careType"] = daily_log.get("careType", "")
        flat["dailyLog_seenBy"] = daily_log.get("seenBy", [])
        flat["dailyLog_background"] = daily_log.get("background", "")
        flat["dailyLog_problems_current"] = daily_log.get("problems", {}).get("current", [])
        flat["dailyLog_problems_previous"] = daily_log.get("problems", {}).get("previous", [])

        # Respiratory - flatten nested bloodGas
        respiratory = daily_log.get("respiratory", {})
        for key, value in respiratory.items():
            if key == "bloodGas" and isinstance(value, dict):
                for bg_key, bg_value in value.items():
                    flat[f"respiratory_bloodGas_{bg_key}"] = bg_value
            elif key != "additionalIcd":
                flat[f"respiratory_{key}"] = value
        flat["respiratory_additionalIcd"] = respiratory.get("additionalIcd", [])

        # CVS - flatten nested echo
        cvs = daily_log.get("cvs", {})
        for key, value in cvs.items():
            if key == "echo" and isinstance(value, dict):
                for echo_key, echo_value in value.items():
                    flat[f"cvs_echo_{echo_key}"] = echo_value
            elif key != "additionalIcd":
                flat[f"cvs_{key}"] = value
        flat["cvs_additionalIcd"] = cvs.get("additionalIcd", [])

        # GI - flatten nested liver, spleen, nnj, nutrition
        gi = daily_log.get("gi", {})
        for key, value in gi.items():
            if key in ["liver", "spleen", "nnj", "nutrition"] and isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flat[f"gi_{key}_{sub_key}"] = sub_value
            elif key != "additionalIcd":
                flat[f"gi_{key}"] = value
        flat["gi_additionalIcd"] = gi.get("additionalIcd", [])

        # CNS - flatten nested eegCfm
        cns = daily_log.get("cns", {})
        for key, value in cns.items():
            if key == "eegCfm" and isinstance(value, dict):
                for cfm_key, cfm_value in value.items():
                    flat[f"cns_eegCfm_{cfm_key}"] = cfm_value
            elif key != "additionalIcd":
                flat[f"cns_{key}"] = value
        flat["cns_additionalIcd"] = cns.get("additionalIcd", [])

        # Sepsis
        sepsis = daily_log.get("sepsis", {})
        for key, value in sepsis.items():
            flat[f"sepsis_{key}"] = value

        # Renal/Metabolic
        renal = daily_log.get("renalMetabolic", {})
        for key, value in renal.items():
            flat[f"renalMetabolic_{key}"] = value

        # Invasive Lines - flatten nested pvc, picc, uvc, uac, pac
        lines = daily_log.get("invasiveLines", {})
        for line_type, line_data in lines.items():
            if isinstance(line_data, dict):
                for line_key, line_value in line_data.items():
                    flat[f"invasiveLines_{line_type}_{line_key}"] = line_value

        # Inotropes
        inotropes = daily_log.get("inotropes", {})
        for key, value in inotropes.items():
            flat[f"inotropes_{key}"] = value

        # Skin
        skin = daily_log.get("skin", {})
        for key, value in skin.items():
            flat[f"skin_{key}"] = value

        # ROP
        rop = daily_log.get("rop", {})
        for key, value in rop.items():
            flat[f"rop_{key}"] = value

        # Top-level arrays
        flat["antibiotics_list"] = nested_data.get("antibiotics", [])
        flat["transfusions_list"] = nested_data.get("transfusions", [])
        flat["fluids_list"] = nested_data.get("fluids", [])

        return flat

    except Exception as e:
        logger.error(f"[NEO_DAILY_FORMATTER] Flattening failed: {e}", exc_info=True)
        return nested_data

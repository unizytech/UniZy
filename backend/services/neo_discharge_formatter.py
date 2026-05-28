"""
NEONATAL_DISCHARGE Formatter Service

Reconstructs nested structure from flattened Gemini extraction results.
Converts flat schema output back to the expected nested format for
frontend, webhook, and external APIs.

Supports two-part extraction:
- Part 1: Core discharge info, immunization, physical findings, medications
- Part 2: Checklist, blood tests, screenings, procedures
"""

import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def format_neo_discharge(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested NEONATAL_DISCHARGE structure from flattened extraction.

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching production API format
    """
    try:
        logger.info("[NEO_DISCHARGE_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== SECTION 1: TOP-LEVEL FIELDS ==========
        nested["uhid"] = flat_data.get("uhid", "")
        nested["visitNumber"] = flat_data.get("visitNumber", "")
        nested["roomId"] = flat_data.get("roomId")
        nested["roomNumber"] = flat_data.get("roomNumber")
        nested["bedId"] = flat_data.get("bedId")
        nested["bedNumber"] = flat_data.get("bedNumber")

        # ========== SECTION 2: DISCHARGE OBJECT ==========
        discharge = {}

        # Basic discharge info
        discharge["status"] = flat_data.get("discharge_status", "")
        discharge["date"] = flat_data.get("discharge_date", "")
        discharge["diedTime"] = flat_data.get("discharge_diedTime", "")
        discharge["weight"] = flat_data.get("discharge_weight", "")
        discharge["ofc"] = flat_data.get("discharge_ofc", "")
        discharge["length"] = flat_data.get("discharge_length", "")

        # Immunization
        vaccine_ids = flat_data.get("immunization_vaccineIds", []) or []
        vaccine_dates = flat_data.get("immunization_vaccineDates", []) or []
        vaccine_list = []
        for i, vaccine_id in enumerate(vaccine_ids):
            vaccine_entry = {"vaccineId": vaccine_id}
            if i < len(vaccine_dates):
                vaccine_entry["date"] = vaccine_dates[i]
            vaccine_list.append(vaccine_entry)

        discharge["immunization"] = {
            "status": flat_data.get("immunization_status", ""),
            "schedule": flat_data.get("immunization_schedule", ""),
            "vaccineList": vaccine_list
        }

        # Physical findings
        discharge["additionalInformation"] = flat_data.get("discharge_additionalInformation", "")
        discharge["eyes"] = flat_data.get("discharge_eyes", "")
        discharge["cardiacMurmur"] = flat_data.get("discharge_cardiacMurmur", "")
        discharge["postductalSaturation"] = flat_data.get("discharge_postductalSaturation", "")
        discharge["femoralPulses"] = flat_data.get("discharge_femoralPulses", "")
        discharge["hips"] = flat_data.get("discharge_hips", "")
        discharge["genitalia"] = flat_data.get("discharge_genitalia", "")
        discharge["genitaliaFindings"] = flat_data.get("discharge_genitaliaFindings", "")
        discharge["malformation"] = flat_data.get("discharge_malformation", "")
        discharge["malformationDetails"] = flat_data.get("discharge_malformationDetails", "")
        discharge["feeding"] = flat_data.get("discharge_feeding", "")
        discharge["neurologicalStatus"] = flat_data.get("discharge_neurologicalStatus", "")

        # Next appointment
        discharge["nextAppointment"] = {
            "status": flat_data.get("nextAppointment_status", False),
            "dateTime": flat_data.get("nextAppointment_dateTime", "")
        }

        # Medications - reconstruct with multi-dosage support
        drug_ids = flat_data.get("medications_drugIds", []) or []
        resolved_ids = flat_data.get("_resolved_medication_drugIds", []) or []
        routes = flat_data.get("medications_routes", []) or []
        dosages_json = flat_data.get("medications_dosages", []) or []

        # Fallback parallel arrays for single-dosage mode
        doses = flat_data.get("medications_doses", []) or []
        frequencies = flat_data.get("medications_frequencies", []) or []
        durations = flat_data.get("medications_durations", []) or []
        instructions = flat_data.get("medications_instructions", []) or []

        medications = []
        for i, drug_id in enumerate(drug_ids):
            # Prefer resolved drug ID from medicine list post-processing
            final_drug_id = drug_id
            if resolved_ids and i < len(resolved_ids) and resolved_ids[i] is not None:
                final_drug_id = resolved_ids[i]

            route = routes[i] if i < len(routes) else ""

            # Try JSON-encoded dosage array first (supports multiple dosages per med)
            dosage_list = []
            if dosages_json and i < len(dosages_json):
                try:
                    dosage_entry = dosages_json[i]
                    if isinstance(dosage_entry, str) and dosage_entry:
                        dosage_list = json.loads(dosage_entry)
                    elif isinstance(dosage_entry, list):
                        dosage_list = dosage_entry
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"[NEO_DISCHARGE_FORMATTER] Failed to parse dosage JSON for drug {drug_id}: {e}")

            # Ensure each dosage entry has additionalInstruction field
            if dosage_list:
                for d in dosage_list:
                    if isinstance(d, dict) and "additionalInstruction" not in d:
                        d["additionalInstruction"] = ""
            else:
                # Fallback to parallel arrays (single dosage per medication)
                dosage_list = [{
                    "dose": doses[i] if i < len(doses) else "",
                    "frequency": frequencies[i] if i < len(frequencies) else "",
                    "duration": durations[i] if i < len(durations) else "",
                    "additionalInstruction": instructions[i] if i < len(instructions) else ""
                }]

            med_entry = {
                "drugId": str(final_drug_id),
                "route": str(route),
                "dosage": dosage_list
            }
            medications.append(med_entry)

        discharge["medications"] = medications

        # ========== SECTION 3: CHECKLIST ==========
        checklist = {}

        # Blood test results
        checklist["bloodTest"] = {
            "hb": flat_data.get("bloodTest_hb", ""),
            "pcv": flat_data.get("bloodTest_pcv", ""),
            "dct": flat_data.get("bloodTest_dct", ""),
            "tsb": flat_data.get("bloodTest_tsb", ""),
            "directBilirubin": flat_data.get("bloodTest_directBilirubin", ""),
            "serumCa": flat_data.get("bloodTest_serumCa", ""),
            "serumPo4": flat_data.get("bloodTest_serumPo4", ""),
            "serumALP": flat_data.get("bloodTest_serumALP", ""),
            "serumNa": flat_data.get("bloodTest_serumNa", ""),
            "homeOxygen": flat_data.get("bloodTest_homeOxygen", ""),
            "cranialUltrasound": {
                "status": flat_data.get("cranialUltrasound_status", ""),
                "condition": flat_data.get("cranialUltrasound_condition", "")
            },
            "echoCardiography": {
                "status": flat_data.get("echoCardiography_status", ""),
                "condition": flat_data.get("echoCardiography_condition", "")
            }
        }

        # Newborn screen
        checklist["newBornScreen"] = flat_data.get("newBornScreen", "")

        # Hearing screening
        checklist["hearingScreening"] = {
            "status": flat_data.get("hearingScreening_status", ""),
            "oae": {
                "left": flat_data.get("hearingScreening_oae_left", ""),
                "right": flat_data.get("hearingScreening_oae_right", "")
            },
            "abr": {
                "left": flat_data.get("hearingScreening_abr_left", ""),
                "right": flat_data.get("hearingScreening_abr_right", "")
            }
        }

        # ROP screening
        checklist["ropScreening"] = {
            "status": flat_data.get("ropScreening_status", ""),
            "result": {
                "left": flat_data.get("ropScreening_result_left", ""),
                "right": flat_data.get("ropScreening_result_right", "")
            }
        }

        # ROP treatment
        left_treatments = flat_data.get("ropTreatment_left", []) or []
        right_treatments = flat_data.get("ropTreatment_right", []) or []

        checklist["ropTreatment"] = {
            "status": flat_data.get("ropTreatment_status", ""),
            "type": {
                "left": [{"treatment": t} for t in left_treatments],
                "right": [{"treatment": t} for t in right_treatments]
            }
        }

        # ROP follow-up
        checklist["ropFollowUp"] = flat_data.get("ropFollowUp")

        # Procedures
        procedures_raw = flat_data.get("procedures", []) or []
        checklist["procedures"] = [{"name": p} for p in procedures_raw]

        # Infections
        checklist["hospitalAcquiredInfection"] = flat_data.get("hospitalAcquiredInfection", "")
        checklist["ventilatorAssociatedPneumonia"] = flat_data.get("ventilatorAssociatedPneumonia", "")
        checklist["bloodStreamInfections"] = flat_data.get("bloodStreamInfections", "")

        # Advice and follow-up
        checklist["advice"] = flat_data.get("advice", "")
        checklist["planFollowUp"] = flat_data.get("planFollowUp", "")

        discharge["checklist"] = checklist
        nested["discharge"] = discharge

        logger.info("[NEO_DISCHARGE_FORMATTER] Successfully reconstructed nested structure")
        return nested

    except Exception as e:
        logger.error(f"[NEO_DISCHARGE_FORMATTER] Error reconstructing nested structure: {e}")
        raise


def format_neo_discharge_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested NEONATAL_DISCHARGE structure from two-part extraction.

    Args:
        part1_data: Part 1 extraction (core discharge info, immunization, medications)
        part2_data: Part 2 extraction (checklist, screenings, procedures)

    Returns:
        Nested structure matching production API format
    """
    try:
        logger.info("[NEO_DISCHARGE_FORMATTER] Merging Part 1 and Part 2 extraction results")

        # Merge both parts into single flat dict
        merged = {}
        merged.update(part1_data or {})
        merged.update(part2_data or {})

        # Use the standard formatter
        result = format_neo_discharge(merged)

        logger.info("[NEO_DISCHARGE_FORMATTER] Successfully merged two-part extraction")
        return result

    except Exception as e:
        logger.error(f"[NEO_DISCHARGE_FORMATTER] Error merging parts: {e}")
        raise

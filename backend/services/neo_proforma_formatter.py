"""
NEO_PROFORMA Formatter Service

Reconstructs nested structure from flattened Gemini extraction results.
Converts flat schema output back to the expected nested format for
frontend, webhook, and external APIs.

Supports both:
1. Single flattened extraction (legacy)
2. Two-part extraction (Part 1: Baby Vitals, Part 2: Maternal History)
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def format_neo_proforma(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested NEO_PROFORMA structure from flattened extraction.

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching production API format
    """
    try:
        logger.info("[NEO_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== SECTION 1: SIMPLE FIELDS (NO NESTING) ==========
        # Copy all simple string fields directly
        simple_fields = [
            "uhid", "dateTime", "babyName", "dob", "tob", "birthStatus", "birthWeight",
            "gestationWeeks", "gestationDays", "babyBloodGroup", "birthOrder", "sex",
            "birthLength", "birthHeadCircunference", "transferStatus", "consanguinity",
            "gravida", "para", "liveBirth", "abortion", "conception", "lmp", "EDDByUSG",
            "EDDByDate", "motherBloodGroup", "HIV", "HepatitisB", "VDRL", "booked",
            "bookedPlace", "pleaceOfBooking", "supervised", "pleaceOfSupervision",
            "adjustedRiskForTrisomiesAvailable", "adjustedRiskForTrisomy21",
            "adjustedRiskForTrisomy18", "adjustedRiskForTrisomy13", "otherInvestigations",
            "multiplePregnancy", "pregnancyComplications", "antenatalSteroids",
            "typeOfSteriods", "lastDoseDeliveryInterval", "steroidCourse",
            "antenatalMgSO4ForNeuroprotection", "labour", "natureofLabour", "commentOnLiquor",
            "riskFactorsForSepsisInMothers", "maternalPyrexia",
            "maternalPyrexiaTemperatureFahrenheit", "PROM", "durationOfPROM",
            "maternalAntibiotics", "timeOfLastDose", "modeOfDelivery", "presentation",
            "fetalDistress", "CTG", "CTGDetails", "cordBloodGas", "cordPH", "cordHCO3",
            "cordBE", "typeofAnesthesia", "gastricAspirate", "delayedCordClamping",
            "delayedCordClampingduration", "reasonForNoDCC", "umbilicalCordMilking",
            "cutCordMilking", "facialOxygen", "durationOfFacialOxygen", "maximumFio2Rquired",
            "resuscitation", "initialSteps", "timeOf1stGasp", "timeOf1stGaspInMinutes",
            "regularRespiration", "regularRespirationMinutes", "deliveryRoomCPAP",
            "bagMaskVentilation", "bagMaskVentilationDuration", "bagMaskVentilationDurationMin",
            "intubation", "ETTSizeInMM", "depthOfInsertion", "depthOfInsertionLengthInCM",
            "PPV", "durationOfPTV", "durationOfPTVMinutes", "CPR", "durationOfCPR",
            "durationOfCPRMinutes", "drugs", "vitaminK", "vitaminKDose", "vitaminKRoute",
            "initialExaminationSummary", "malformation", "ICT", "DCT", "backgroundDetails", "plan"
        ]

        for field in simple_fields:
            nested[field] = flat_data.get(field, "")

        # ========== SECTION 2: MATERNAL MEDICAL PROBLEMS (RECONSTRUCT ARRAY OF OBJECTS) ==========
        # Note: These are MATERNAL medical problems, not baby's neonatal conditions
        # Field names: problemsId (not problem), medications (not medication) per Raster API schema
        problem_ids = flat_data.get("medicalProblemIDs", [])
        medications = flat_data.get("medicalProblemMedications", [])

        nested["medicalProblem"] = []
        for i, problem_id in enumerate(problem_ids):
            medication = medications[i] if i < len(medications) else ""
            nested["medicalProblem"].append({
                "problemsId": problem_id,
                "medications": medication
            })

        # ========== SECTION 3: LIVE BIRTH DETAILS (RECONSTRUCT ARRAY) ==========
        nested["liveBirthBabyDetails"] = []

        # Previous Birth 1
        birth1 = _reconstruct_live_birth(flat_data, "liveBirth1_")
        nested["liveBirthBabyDetails"].append(birth1)

        # Previous Birth 2
        birth2 = _reconstruct_live_birth(flat_data, "liveBirth2_")
        nested["liveBirthBabyDetails"].append(birth2)

        # ========== SECTION 4: PREGNANCY COMPLICATIONS (RECONSTRUCT ARRAY) ==========
        # Field name is "complicationId" (integer) per reference file: pregnancy -> complication -> complicationId
        nested["pregnancyComplicationsDetails"] = []

        # Complication 1
        comp1 = {
            "complicationId": flat_data.get("complication1_name", ""),
            "treatment": flat_data.get("complication1_treatment", ""),
            "duration": flat_data.get("complication1_duration", ""),
            "durationType": flat_data.get("complication1_durationType", "")
        }
        nested["pregnancyComplicationsDetails"].append(comp1)

        # Complication 2
        comp2 = {
            "complicationId": flat_data.get("complication2_name", ""),
            "treatment": flat_data.get("complication2_treatment", ""),
            "duration": flat_data.get("complication2_duration", ""),
            "durationType": flat_data.get("complication2_durationType", "")
        }
        nested["pregnancyComplicationsDetails"].append(comp2)

        # ========== SECTION 5: SCAN DETAILS (RECONSTRUCT OBJECTS/ARRAYS) ==========
        # Dating Scan
        nested["datingScanDetails"] = {
            "date": flat_data.get("datingScan_date", ""),
            "gestation": flat_data.get("datingScan_gestation", ""),
            "findings": flat_data.get("datingScan_findings", "")
        }

        # Anomaly Scan
        nested["anomalyScanDetails"] = {
            "date": flat_data.get("anomalyScan_date", ""),
            "gestation": flat_data.get("anomalyScan_gestation", ""),
            "findings": flat_data.get("anomalyScan_findings", "")
        }

        # Other Scans Array
        nested["otherScanDetails"] = []
        for i in range(1, 3):  # 2 other scans
            scan = {
                "date": flat_data.get(f"otherScan{i}_date", ""),
                "gestation": flat_data.get(f"otherScan{i}_gestation", ""),
                "findings": flat_data.get(f"otherScan{i}_findings", "")
            }
            nested["otherScanDetails"].append(scan)

        # Doppler Scans Array
        nested["dopplerScanDetails"] = []
        for i in range(1, 3):  # 2 Doppler scans
            scan = {
                "date": flat_data.get(f"dopplerScan{i}_date", ""),
                "gestation": flat_data.get(f"dopplerScan{i}_gestation", ""),
                "findings": flat_data.get(f"dopplerScan{i}_findings", "")
            }
            nested["dopplerScanDetails"].append(scan)

        # ========== SECTION 6: RISK FACTORS & INDICATION (SIMPLE ARRAYS) ==========
        nested["riskFactors"] = flat_data.get("riskFactors", [])
        nested["indication"] = flat_data.get("indication", [])

        # ========== SECTION 7: MATERNAL ANTIBIOTICS (RECONSTRUCT ARRAY OF OBJECTS) ==========
        antibiotics_array = flat_data.get("maternalAntibioticsArray", [])
        nested["maternalAntibioticsDetails"] = []
        for antibiotic in antibiotics_array:
            nested["maternalAntibioticsDetails"].append({
                "antibiotic": antibiotic
            })

        # ========== SECTION 8: APGAR SCORES (RECONSTRUCT NESTED OBJECT) ==========
        nested["apgar"] = {
            "status": flat_data.get("apgar_status", "unknown")
        }

        # Reconstruct all 5 time points
        for minute in ["minute1", "minute5", "minute10", "minute15", "minute20"]:
            nested["apgar"][minute] = {
                "color": flat_data.get(f"apgar_{minute}_color"),
                "heartRate": flat_data.get(f"apgar_{minute}_heartRate"),
                "reflex": flat_data.get(f"apgar_{minute}_reflex"),
                "tone": flat_data.get(f"apgar_{minute}_tone"),
                "respiration": flat_data.get(f"apgar_{minute}_respiration"),
                "total": flat_data.get(f"apgar_{minute}_total")
            }

        # ========== SECTION 9: DRUG DETAILS (SIMPLE ARRAY) ==========
        nested["drugDetails"] = flat_data.get("drugDetails", [])

        logger.info(
            f"[NEO_FORMATTER] ✅ Reconstruction complete - "
            f"{len(nested)} top-level fields, "
            f"{len(nested.get('medicalProblem', []))} maternal medical problems, "
            f"APGAR status: {nested['apgar']['status']}"
        )

        return nested

    except Exception as e:
        logger.error(f"[NEO_FORMATTER] ❌ Reconstruction failed: {e}", exc_info=True)
        # Return flat data as fallback
        return flat_data


def format_neo_proforma_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge and reconstruct NEO_PROFORMA from two-part extraction.

    This function handles the split schema approach where extraction is done
    in two separate Gemini API calls to avoid schema complexity limits:
    - Part 1: Baby vitals & immediate care (82 fields)
    - Part 2: Maternal history & pregnancy (103 fields)

    Args:
        part1_data: Baby vitals extraction result (Part 1)
        part2_data: Maternal history extraction result (Part 2)

    Returns:
        Nested structure matching production API format
    """
    try:
        logger.info("[NEO_FORMATTER_SPLIT] Starting merge of Part 1 and Part 2 extractions")

        # Merge both parts into a single flat dictionary
        # Parts have non-overlapping fields, so simple dict merge works
        merged_flat = {**part1_data, **part2_data}

        logger.info(
            f"[NEO_FORMATTER_SPLIT] Merged {len(part1_data)} fields from Part 1 + "
            f"{len(part2_data)} fields from Part 2 = {len(merged_flat)} total fields"
        )

        # Use existing formatter to reconstruct nested structure
        nested_result = format_neo_proforma(merged_flat)

        logger.info("[NEO_FORMATTER_SPLIT] ✅ Two-part merge complete")

        return nested_result

    except Exception as e:
        logger.error(f"[NEO_FORMATTER_SPLIT] ❌ Merge failed: {e}", exc_info=True)
        # Return merged flat data as fallback
        return {**part1_data, **part2_data}


def _reconstruct_live_birth(flat_data: Dict[str, Any], prefix: str) -> Dict[str, str]:
    """
    Reconstruct a single live birth detail object from flattened fields.

    Args:
        flat_data: Flattened extraction result
        prefix: Field prefix (e.g., 'liveBirth1_' or 'liveBirth2_')

    Returns:
        Live birth detail object
    """
    return {
        "birthYear": flat_data.get(f"{prefix}birthYear", ""),
        "place": flat_data.get(f"{prefix}place", ""),
        "typeOfDelivery": flat_data.get(f"{prefix}typeOfDelivery", ""),
        "complications": flat_data.get(f"{prefix}complications", ""),
        "gender": flat_data.get(f"{prefix}gender", ""),
        "gestation": flat_data.get(f"{prefix}gestation", ""),
        "birthWeight": flat_data.get(f"{prefix}birthWeight", ""),
        "health": flat_data.get(f"{prefix}health", ""),
        "details": flat_data.get(f"{prefix}details", "")
    }


def format_neo_daily(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format NEO_DAILY extraction (if needed).

    Currently NEO_DAILY schema is not overly complex, so this is a passthrough.
    Add formatting logic here if NEO_DAILY schema needs flattening in the future.

    Args:
        flat_data: Extraction result

    Returns:
        Formatted data
    """
    # NEO_DAILY doesn't need restructuring yet
    return flat_data

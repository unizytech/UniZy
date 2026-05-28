"""
NEO_OP Formatter Service

Reconstructs nested structure from flattened Gemini extraction results.
Converts flat schema output back to the expected nested format for
frontend, webhook, and external APIs (Raster API).

Supports two-part extraction (Part 1: Baby/Eligibility/MedicalHistory, Part 2: Family/FollowUp/Medications)
"""

import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def format_neo_op(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested NEO_OP structure from flattened extraction.

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching production API format
    """
    try:
        logger.info("[NEO_OP_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== SECTION 1: TOP-LEVEL FIELDS ==========
        nested["uhid"] = flat_data.get("uhid", "")
        nested["opDateTime"] = flat_data.get("opDateTime", "")
        nested["hospitalName"] = flat_data.get("hospitalName", "")

        # ========== SECTION 2: BABY DETAILS (Reconstruct nested object) ==========
        nested["baby"] = {
            "name": flat_data.get("baby_name", ""),
            "dob": flat_data.get("baby_dob", ""),
            "tob": flat_data.get("baby_tob", ""),
            "sex": flat_data.get("baby_sex", ""),
            "birthStatus": flat_data.get("baby_birthStatus", ""),
            "birthOrder": flat_data.get("baby_birthOrder", ""),
            "bloodGroup": flat_data.get("baby_bloodGroup", ""),
            "birthWeight": flat_data.get("baby_birthWeight", ""),
            "birthHeadCircumference": flat_data.get("baby_birthHeadCircumference", ""),
            "currentWeight": flat_data.get("baby_currentWeight", ""),
            "currentHeadCircumference": flat_data.get("baby_currentHeadCircumference", ""),
            "currentLength": flat_data.get("baby_currentLength", ""),
            "gestation": {
                "weeks": flat_data.get("baby_gestation_weeks") or 0,
                "days": flat_data.get("baby_gestation_days") or 0
            },
            "chronologicalAge": {
                "yearMonthDays": {
                    "years": flat_data.get("baby_chronologicalAge_years") or 0,
                    "months": flat_data.get("baby_chronologicalAge_months") or 0,
                    "days": flat_data.get("baby_chronologicalAge_days") or 0
                },
                "weeksDays": {
                    "weeks": flat_data.get("baby_chronologicalAge_weeks") or 0,
                    "days": flat_data.get("baby_chronologicalAge_weeksDays") or 0
                }
            },
            "correctedAge": {
                "yearMonthDays": {
                    "years": flat_data.get("baby_correctedAge_years") or 0,
                    "months": flat_data.get("baby_correctedAge_months") or 0,
                    "days": flat_data.get("baby_correctedAge_days") or 0
                },
                "weeksDays": {
                    "weeks": flat_data.get("baby_correctedAge_weeks") or 0,
                    "days": flat_data.get("baby_correctedAge_weeksDays") or 0
                }
            }
        }

        # ========== SECTION 3: MOTHER DETAILS (Reconstruct nested object) ==========
        nested["mother"] = {
            "uhid": flat_data.get("mother_uhid", ""),
            "title": flat_data.get("mother_title", ""),
            "name": {
                "initial": flat_data.get("mother_name_initial", ""),
                "first": flat_data.get("mother_name_first", ""),
                "last": flat_data.get("mother_name_last", "")
            },
            "dob": flat_data.get("mother_dob", ""),
            "age": flat_data.get("mother_age", ""),
            "education": flat_data.get("mother_education", ""),
            "occupation": {
                "type": flat_data.get("mother_occupation_type", ""),
                "status": flat_data.get("mother_occupation_status", "")
            },
            "contact": {
                "primary": flat_data.get("mother_contact_primary", ""),
                "secondary": flat_data.get("mother_contact_secondary", ""),
                "email": flat_data.get("mother_contact_email", "")
            },
            "language": flat_data.get("mother_language", ""),
            "address": {
                "doorNo": flat_data.get("mother_address_doorNo", ""),
                "street": flat_data.get("mother_address_street", ""),
                "city": flat_data.get("mother_address_city", ""),
                "pinCode": flat_data.get("mother_address_pinCode", ""),
                "country": flat_data.get("mother_address_country", "")
            },
            "bloodGroup": flat_data.get("mother_bloodGroup", "")
        }

        # ========== SECTION 4: PARTNER DETAILS (Reconstruct nested object) ==========
        nested["partner"] = {
            "title": flat_data.get("partner_title", ""),
            "name": {
                "initial": flat_data.get("partner_name_initial", ""),
                "first": flat_data.get("partner_name_first", ""),
                "last": flat_data.get("partner_name_last", "")
            },
            "dob": flat_data.get("partner_dob", ""),
            "age": flat_data.get("partner_age", ""),
            "education": flat_data.get("partner_education", ""),
            "occupation": {
                "type": flat_data.get("partner_occupation_type", ""),
                "status": flat_data.get("partner_occupation_status", "")
            },
            "contact": {
                "primary": flat_data.get("partner_contact_primary", ""),
                "secondary": flat_data.get("partner_contact_secondary", ""),
                "email": flat_data.get("partner_contact_email", "")
            },
            "language": flat_data.get("partner_language", ""),
            "address": {
                "doorNo": flat_data.get("partner_address_doorNo", ""),
                "street": flat_data.get("partner_address_street", ""),
                "city": flat_data.get("partner_address_city", ""),
                "pinCode": flat_data.get("partner_address_pinCode", ""),
                "country": flat_data.get("partner_address_country", "")
            },
            "sameAsMotherDetails": flat_data.get("partner_sameAsMotherDetails", False),
            "sameAsAddress": flat_data.get("partner_sameAsAddress", False)
        }

        # ========== SECTION 5: ELIGIBILITY CRITERIA (Reconstruct nested object) ==========
        nested["eligibility"] = {
            "birthWeightGestationIsLesser": flat_data.get("eligibility_birthWeightGestationIsLesser", False),
            "birthWeightGestationIsGreater": flat_data.get("eligibility_birthWeightGestationIsGreater", False),
            "intrauterineGrowth": flat_data.get("eligibility_intrauterineGrowth", False),
            "meningitis": flat_data.get("eligibility_meningitis", False),
            "mechanicalVentilation": flat_data.get("eligibility_mechanicalVentilation", False),
            "encephalopathyStage2OrMore": flat_data.get("eligibility_encephalopathyStage2OrMore", False),
            "majorMalformation": flat_data.get("eligibility_majorMalformation", False),
            "inbornErrors": flat_data.get("eligibility_inbornErrors", False),
            "symptomaticHypoglycemia": flat_data.get("eligibility_symptomaticHypoglycemia", False),
            "symptomaticPolycythemia": flat_data.get("eligibility_symptomaticPolycythemia", False),
            "retrovirusPositiveMother": flat_data.get("eligibility_retrovirusPositiveMother", False),
            "hyperbilirubinemiaTransfusionRh": flat_data.get("eligibility_hyperbilirubinemiaTransfusionRh", False),
            "abnormalNeuroExam": flat_data.get("eligibility_abnormalNeuroExam", False),
            "majorMorbidities": flat_data.get("eligibility_majorMorbidities", False),
            "otherSpecifyIsPresent": flat_data.get("eligibility_otherSpecifyIsPresent", False),
            "otherSpecify": flat_data.get("eligibility_otherSpecify", ""),
            "generalCheckup": flat_data.get("eligibility_generalCheckup", False)
        }

        # ========== SECTION 6: MEDICAL HISTORY (Reconstruct nested object) ==========
        nested["medicalHistory"] = {
            "babyBackground": flat_data.get("medicalHistory_babyBackground", ""),
            "confidentialDetails": flat_data.get("medicalHistory_confidentialDetails", ""),
            "complaints": flat_data.get("medicalHistory_complaints", ""),
            "hpi": flat_data.get("medicalHistory_hpi", ""),
            "allergy": flat_data.get("medicalHistory_allergy", ""),
            "familyHistory": flat_data.get("medicalHistory_familyHistory", ""),
            "treatmentHistory": flat_data.get("medicalHistory_treatmentHistory", ""),
            "development": flat_data.get("medicalHistory_development", ""),
            "examination": flat_data.get("medicalHistory_examination", ""),
            "neurosonogram": flat_data.get("medicalHistory_neurosonogram") or 0,
            "echocardiogram": flat_data.get("medicalHistory_echocardiogram") or 0,
            "diagnosis": flat_data.get("medicalHistory_diagnosis", ""),
            "advice": flat_data.get("medicalHistory_advice", ""),
            "investigations": flat_data.get("medicalHistory_investigations", "")
        }

        # ========== SECTION 7: FOLLOW-UP DETAILS (Reconstruct nested object) ==========
        nested["followUp"] = {
            "appointmentType": flat_data.get("followUp_appointmentType", ""),
            "reviewDateTime": flat_data.get("followUp_reviewDateTime", ""),
            "nextReviewIndication": flat_data.get("followUp_nextReviewIndication", ""),
            "needNeuro": flat_data.get("followUp_needNeuro", False),
            "outcome": flat_data.get("followUp_outcome", ""),
            "seenBy": flat_data.get("followUp_seenBy") or 7,
            "fee": {
                "status": flat_data.get("followUp_fee_status", False),
                "amount": flat_data.get("followUp_fee_amount", ""),
                "reason": flat_data.get("followUp_fee_reason", "")
            }
        }

        # ========== SECTION 8: MEDICATIONS (Reconstruct array of objects) ==========
        drug_ids = flat_data.get("medication_drugIds", [])
        resolved_ids = flat_data.get("_resolved_medication_drugIds", [])
        routes = flat_data.get("medication_routes", [])
        dosages_json = flat_data.get("medication_dosages", [])

        medications = []
        for i, drug_id in enumerate(drug_ids):
            route = routes[i] if i < len(routes) else ""

            # Parse dosage JSON string
            dosage_list = []
            if i < len(dosages_json):
                try:
                    dosage_str = dosages_json[i]
                    if isinstance(dosage_str, str) and dosage_str:
                        dosage_list = json.loads(dosage_str)
                    elif isinstance(dosage_str, list):
                        dosage_list = dosage_str
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"[NEO_OP_FORMATTER] Failed to parse dosage JSON for drug {drug_id}: {e}")
                    dosage_list = []

            # Prefer resolved _external_id from medicine list post-processing
            final_drug_id = str(drug_id)
            if resolved_ids and i < len(resolved_ids) and resolved_ids[i] is not None:
                final_drug_id = str(resolved_ids[i])

            medications.append({
                "drugId": final_drug_id,
                "route": str(route),
                "dosage": dosage_list if dosage_list else []
            })

        nested["medications"] = medications

        # ========== SECTION 9: IMMUNIZATION (Reconstruct nested object with array) ==========
        vaccine_ids = flat_data.get("immunization_vaccineIds", [])
        vaccine_list = [{"vaccineId": vid} for vid in vaccine_ids]

        nested["immunization"] = {
            "status": flat_data.get("immunization_status", ""),
            "schedule": flat_data.get("immunization_schedule", ""),
            "vaccineList": vaccine_list
        }

        logger.info(
            f"[NEO_OP_FORMATTER] ✅ Reconstruction complete - "
            f"{len(nested)} top-level sections, "
            f"{len(medications)} medications, "
            f"{len(vaccine_list)} vaccines"
        )

        return nested

    except Exception as e:
        logger.error(f"[NEO_OP_FORMATTER] ❌ Reconstruction failed: {e}", exc_info=True)
        # Return flat data as fallback
        return flat_data


def format_neo_op_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge and reconstruct NEO_OP from two-part extraction.

    This function handles the split schema approach where extraction is done
    in two separate Gemini API calls to avoid schema complexity limits:
    - Part 1: Baby, Eligibility, Medical History (~65 fields)
    - Part 2: Mother, Partner, Follow-up, Medications, Immunization (~60 fields)

    Args:
        part1_data: Baby/Eligibility/MedicalHistory extraction result (Part 1)
        part2_data: Family/FollowUp/Medications extraction result (Part 2)

    Returns:
        Nested structure matching production API format
    """
    try:
        logger.info("[NEO_OP_FORMATTER_SPLIT] Starting merge of Part 1 and Part 2 extractions")

        # Merge both parts into a single flat dictionary
        # Parts have non-overlapping fields, so simple dict merge works
        merged_flat = {**part1_data, **part2_data}

        logger.info(
            f"[NEO_OP_FORMATTER_SPLIT] Merged {len(part1_data)} fields from Part 1 + "
            f"{len(part2_data)} fields from Part 2 = {len(merged_flat)} total fields"
        )

        # Use existing formatter to reconstruct nested structure
        nested_result = format_neo_op(merged_flat)

        logger.info("[NEO_OP_FORMATTER_SPLIT] ✅ Two-part merge complete")

        return nested_result

    except Exception as e:
        logger.error(f"[NEO_OP_FORMATTER_SPLIT] ❌ Merge failed: {e}", exc_info=True)
        # Return merged flat data as fallback
        return {**part1_data, **part2_data}

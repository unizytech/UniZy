"""
OPTOMETRY Formatter Service

Reconstructs nested structure from flattened Gemini extraction results.
Converts flat schema output back to the expected nested format for
frontend, webhook, and external APIs.

Supports both:
1. Single flattened extraction (full schema)
2. Two-part extraction (if needed for very large datasets)
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def format_optometry(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested OPTOMETRY structure from flattened extraction.

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching expected API format
    """
    try:
        logger.info("[OPTO_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== SECTION 1: STUDENT DEMOGRAPHICS (RECONSTRUCT OBJECT) ==========
        nested["patientDemographics"] = {
            "date": flat_data.get("patientDemographics_date", ""),
            "mrNumber": flat_data.get("patientDemographics_mrNumber", ""),
            "title": flat_data.get("patientDemographics_title", ""),
            "surname": flat_data.get("patientDemographics_surname", ""),
            "name": flat_data.get("patientDemographics_name", ""),
            "dob": flat_data.get("patientDemographics_dob", ""),
            "address": flat_data.get("patientDemographics_address", "")
        }

        # ========== SECTION 2: REFERRAL INFORMATION (RECONSTRUCT OBJECT) ==========
        nested["referralInformation"] = {
            "referralType": flat_data.get("referralInformation_referralType", "")
        }

        # ========== SECTION 3: RIGHT EYE MEASUREMENTS (RECONSTRUCT OBJECT) ==========
        nested["rightEye"] = {
            "vision": flat_data.get("rightEye_vision", ""),
            "refraction": flat_data.get("rightEye_refraction", ""),
            "vaDistance": flat_data.get("rightEye_vaDistance", ""),
            "add": flat_data.get("rightEye_add", ""),
            "vaNear": flat_data.get("rightEye_vaNear", "")
        }

        # ========== SECTION 4: LEFT EYE MEASUREMENTS (RECONSTRUCT OBJECT) ==========
        nested["leftEye"] = {
            "vision": flat_data.get("leftEye_vision", ""),
            "refraction": flat_data.get("leftEye_refraction", ""),
            "vaDistance": flat_data.get("leftEye_vaDistance", ""),
            "add": flat_data.get("leftEye_add", ""),
            "vaNear": flat_data.get("leftEye_vaNear", "")
        }

        # ========== SECTION 5: GLAUCOMA ASSESSMENT (RECONSTRUCT OBJECT) ==========
        nested["glaucomaAssessment"] = {
            "cdRatioRight": flat_data.get("glaucomaAssessment_cdRatioRight", ""),
            "cdRatioLeft": flat_data.get("glaucomaAssessment_cdRatioLeft", ""),
            "iopRight": flat_data.get("glaucomaAssessment_iopRight", ""),
            "iopLeft": flat_data.get("glaucomaAssessment_iopLeft", ""),
            "iopMethod": flat_data.get("glaucomaAssessment_iopMethod", ""),
            "iopTime": flat_data.get("glaucomaAssessment_iopTime", ""),
            "visualFieldRight": flat_data.get("glaucomaAssessment_visualFieldRight", ""),
            "visualFieldLeft": flat_data.get("glaucomaAssessment_visualFieldLeft", "")
        }

        # ========== SECTION 6: CLINICAL NOTES (SIMPLE FIELD) ==========
        nested["clinicalNotes"] = flat_data.get("clinicalNotes", "")

        # ========== SECTION 7: PROVIDER INFORMATION (RECONSTRUCT OBJECT) ==========
        nested["providerInformation"] = {
            "signature": flat_data.get("providerInformation_signature", ""),
            "providerName": flat_data.get("providerInformation_providerName", "")
        }

        logger.info(
            f"[OPTO_FORMATTER] ✅ Reconstruction complete - "
            f"7 top-level sections reconstructed"
        )

        return nested

    except Exception as e:
        logger.error(f"[OPTO_FORMATTER] ❌ Reconstruction failed: {e}", exc_info=True)
        # Return flat data as fallback
        return flat_data


def format_optometry_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge and reconstruct OPTOMETRY from two-part extraction.

    This function handles split schema approach where extraction is done
    in two separate Gemini API calls to avoid schema complexity limits.

    Args:
        part1_data: First part extraction result
        part2_data: Second part extraction result

    Returns:
        Nested structure matching expected API format
    """
    try:
        logger.info("[OPTO_FORMATTER_SPLIT] Starting merge of Part 1 and Part 2 extractions")

        # Merge both parts into a single flat dictionary
        merged_flat = {**part1_data, **part2_data}

        logger.info(
            f"[OPTO_FORMATTER_SPLIT] Merged {len(part1_data)} fields from Part 1 + "
            f"{len(part2_data)} fields from Part 2 = {len(merged_flat)} total fields"
        )

        # Use existing formatter to reconstruct nested structure
        nested_result = format_optometry(merged_flat)

        logger.info("[OPTO_FORMATTER_SPLIT] ✅ Two-part merge complete")

        return nested_result

    except Exception as e:
        logger.error(f"[OPTO_FORMATTER_SPLIT] ❌ Merge failed: {e}", exc_info=True)
        # Return merged flat data as fallback
        return {**part1_data, **part2_data}

"""
OPHTHALMOLOGY Formatter Service

Reconstructs nested structure from flattened Gemini extraction results.
Converts flat schema output back to the expected nested format for
frontend, webhook, and external APIs.

Supports both:
1. Single flattened extraction (full schema)
2. Two-part extraction (if needed for very large datasets)
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def format_ophthalmology(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested OPHTHALMOLOGY structure from flattened extraction.

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching expected API format
    """
    try:
        logger.info("[OPHTHAL_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== SECTION 1: STUDENT DEMOGRAPHICS (RECONSTRUCT OBJECT) ==========
        nested["patientDemographics"] = {
            "mrNumber": flat_data.get("patientDemographics_mrNumber", ""),
            "date": flat_data.get("patientDemographics_date", ""),
            "patientName": flat_data.get("patientDemographics_patientName", ""),
            "age": flat_data.get("patientDemographics_age", ""),
            "gender": flat_data.get("patientDemographics_gender", "")
        }

        # ========== SECTION 2: CLINICAL HISTORY (RECONSTRUCT OBJECT) ==========
        nested["clinicalHistory"] = {
            "complaints": flat_data.get("clinicalHistory_complaints", "N/A"),
            "pastHistory": flat_data.get("clinicalHistory_pastHistory", "N/A"),
            "systemicIllness": flat_data.get("clinicalHistory_systemicIllness", "N/A"),
            "familyHistory": flat_data.get("clinicalHistory_familyHistory", "N/A"),
            "allergy": flat_data.get("clinicalHistory_allergy", "N/A"),
            "currentTreatment": flat_data.get("clinicalHistory_currentTreatment", "N/A"),
            "pgp": flat_data.get("clinicalHistory_pgp", "N/A")
        }

        # ========== SECTION 3: VISUAL ACUITY (RECONSTRUCT 2-LEVEL NESTED OBJECT) ==========
        nested["visualAcuity"] = {
            "rightEye": {
                "distance": flat_data.get("visualAcuity_rightEye_distance", "N/A"),
                "near": flat_data.get("visualAcuity_rightEye_near", "N/A")
            },
            "leftEye": {
                "distance": flat_data.get("visualAcuity_leftEye_distance", "N/A"),
                "near": flat_data.get("visualAcuity_leftEye_near", "N/A")
            }
        }

        # ========== SECTION 4: REFRACTION (RECONSTRUCT 3-LEVEL NESTED OBJECT) ==========
        nested["refraction"] = {
            "objective": {
                "rightEye": flat_data.get("refraction_objective_rightEye", "N/A"),
                "leftEye": flat_data.get("refraction_objective_leftEye", "N/A")
            },
            "subjective": {
                "rightEye": {
                    "distance": flat_data.get("refraction_subjective_rightEye_distance", "N/A"),
                    "near": flat_data.get("refraction_subjective_rightEye_near", "N/A")
                },
                "leftEye": {
                    "distance": flat_data.get("refraction_subjective_leftEye_distance", "N/A"),
                    "near": flat_data.get("refraction_subjective_leftEye_near", "N/A")
                }
            }
        }

        # ========== SECTION 5: MUSCLE BALANCE (RECONSTRUCT OBJECT) ==========
        nested["muscleBalance"] = {
            "eom": flat_data.get("muscleBalance_eom", "N/A"),
            "coverTest": flat_data.get("muscleBalance_coverTest", "N/A"),
            "coverTestDistance": flat_data.get("muscleBalance_coverTestDistance", "N/A"),
            "coverTestNear": flat_data.get("muscleBalance_coverTestNear", "N/A")
        }

        # ========== SECTION 6: SLIT LAMP EXAMINATION (RECONSTRUCT 2-LEVEL NESTED OBJECT) ==========
        nested["slitLampExamination"] = {
            "rightEye": {
                "lidsAndLashes": flat_data.get("slitLampExamination_rightEye_lidsAndLashes", "N/A"),
                "conjunctiva": flat_data.get("slitLampExamination_rightEye_conjunctiva", "N/A"),
                "cornea": flat_data.get("slitLampExamination_rightEye_cornea", "N/A"),
                "anteriorChamber": flat_data.get("slitLampExamination_rightEye_anteriorChamber", "N/A"),
                "iris": flat_data.get("slitLampExamination_rightEye_iris", "N/A"),
                "lens": flat_data.get("slitLampExamination_rightEye_lens", "N/A")
            },
            "leftEye": {
                "lidsAndLashes": flat_data.get("slitLampExamination_leftEye_lidsAndLashes", "N/A"),
                "conjunctiva": flat_data.get("slitLampExamination_leftEye_conjunctiva", "N/A"),
                "cornea": flat_data.get("slitLampExamination_leftEye_cornea", "N/A"),
                "anteriorChamber": flat_data.get("slitLampExamination_leftEye_anteriorChamber", "N/A"),
                "iris": flat_data.get("slitLampExamination_leftEye_iris", "N/A"),
                "lens": flat_data.get("slitLampExamination_leftEye_lens", "N/A")
            }
        }

        # ========== SECTION 7: INTRAOCULAR PRESSURE (RECONSTRUCT OBJECT) ==========
        nested["intraocularPressure"] = {
            "rightEye": flat_data.get("intraocularPressure_rightEye", "N/A"),
            "leftEye": flat_data.get("intraocularPressure_leftEye", "N/A"),
            "time": flat_data.get("intraocularPressure_time", ""),
            "method": flat_data.get("intraocularPressure_method", "")
        }

        # ========== SECTION 8: GONIOSCOPY (RECONSTRUCT OBJECT) ==========
        nested["gonioscopy"] = {
            "rightEye": flat_data.get("gonioscopy_rightEye", "N/A"),
            "leftEye": flat_data.get("gonioscopy_leftEye", "N/A")
        }

        # ========== SECTION 9: FUNDUS EXAMINATION (RECONSTRUCT 4-LEVEL NESTED OBJECT) ==========
        # This is the most complex section with 4 levels of nesting
        nested["fundusExamination"] = {
            "rightEye": {
                "opticDisc": {
                    "cdRatio": flat_data.get("fundusExamination_rightEye_opticDisc_cdRatio", "N/A"),
                    "color": flat_data.get("fundusExamination_rightEye_opticDisc_color", "N/A"),
                    "margins": flat_data.get("fundusExamination_rightEye_opticDisc_margins", "N/A"),
                    "neovascularization": flat_data.get("fundusExamination_rightEye_opticDisc_neovascularization", "N/A")
                },
                "macula": {
                    "fovealReflex": flat_data.get("fundusExamination_rightEye_macula_fovealReflex", "N/A"),
                    "findings": flat_data.get("fundusExamination_rightEye_macula_findings", "N/A")
                },
                "vessels": {
                    "avRatio": flat_data.get("fundusExamination_rightEye_vessels_avRatio", "N/A"),
                    "caliber": flat_data.get("fundusExamination_rightEye_vessels_caliber", "N/A"),
                    "findings": flat_data.get("fundusExamination_rightEye_vessels_findings", "N/A")
                },
                "periphery": {
                    "retina": flat_data.get("fundusExamination_rightEye_periphery_retina", "N/A"),
                    "vitreous": flat_data.get("fundusExamination_rightEye_periphery_vitreous", "N/A")
                },
                "drawing": flat_data.get("fundusExamination_rightEye_drawing", "")
            },
            "leftEye": {
                "opticDisc": {
                    "cdRatio": flat_data.get("fundusExamination_leftEye_opticDisc_cdRatio", "N/A"),
                    "color": flat_data.get("fundusExamination_leftEye_opticDisc_color", "N/A"),
                    "margins": flat_data.get("fundusExamination_leftEye_opticDisc_margins", "N/A"),
                    "neovascularization": flat_data.get("fundusExamination_leftEye_opticDisc_neovascularization", "N/A")
                },
                "macula": {
                    "fovealReflex": flat_data.get("fundusExamination_leftEye_macula_fovealReflex", "N/A"),
                    "findings": flat_data.get("fundusExamination_leftEye_macula_findings", "N/A")
                },
                "vessels": {
                    "avRatio": flat_data.get("fundusExamination_leftEye_vessels_avRatio", "N/A"),
                    "caliber": flat_data.get("fundusExamination_leftEye_vessels_caliber", "N/A"),
                    "findings": flat_data.get("fundusExamination_leftEye_vessels_findings", "N/A")
                },
                "periphery": {
                    "retina": flat_data.get("fundusExamination_leftEye_periphery_retina", "N/A"),
                    "vitreous": flat_data.get("fundusExamination_leftEye_periphery_vitreous", "N/A")
                },
                "drawing": flat_data.get("fundusExamination_leftEye_drawing", "")
            }
        }

        # ========== SECTION 10: DIAGNOSIS (RECONSTRUCT ARRAY) ==========
        # Handle diagnosis as array
        diagnosis_data = flat_data.get("diagnosis", [])
        if isinstance(diagnosis_data, list):
            nested["diagnosis"] = diagnosis_data
        elif isinstance(diagnosis_data, str) and diagnosis_data.strip():
            # If single string provided, convert to array
            nested["diagnosis"] = [diagnosis_data]
        else:
            nested["diagnosis"] = []

        # ========== SECTION 11: ADVICE AND FOLLOW-UP (SIMPLE FIELD) ==========
        nested["adviceAndFollowUp"] = flat_data.get("adviceAndFollowUp", "N/A")

        # ========== SECTION 12: PROVIDER INFORMATION (RECONSTRUCT OBJECT) ==========
        nested["providerInformation"] = {
            "signature": flat_data.get("providerInformation_signature", ""),
            "providerName": flat_data.get("providerInformation_providerName", "")
        }

        logger.info(
            f"[OPHTHAL_FORMATTER] ✅ Reconstruction complete - "
            f"12 top-level sections reconstructed"
        )

        return nested

    except Exception as e:
        logger.error(f"[OPHTHAL_FORMATTER] ❌ Reconstruction failed: {e}", exc_info=True)
        # Return flat data as fallback
        return flat_data


def format_ophthalmology_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge and reconstruct OPHTHALMOLOGY from two-part extraction.

    This function handles split schema approach where extraction is done
    in two separate Gemini API calls to avoid schema complexity limits.

    Args:
        part1_data: First part extraction result
        part2_data: Second part extraction result

    Returns:
        Nested structure matching expected API format
    """
    try:
        logger.info("[OPHTHAL_FORMATTER_SPLIT] Starting merge of Part 1 and Part 2 extractions")

        # Merge both parts into a single flat dictionary
        merged_flat = {**part1_data, **part2_data}

        logger.info(
            f"[OPHTHAL_FORMATTER_SPLIT] Merged {len(part1_data)} fields from Part 1 + "
            f"{len(part2_data)} fields from Part 2 = {len(merged_flat)} total fields"
        )

        # Use existing formatter to reconstruct nested structure
        nested_result = format_ophthalmology(merged_flat)

        logger.info("[OPHTHAL_FORMATTER_SPLIT] ✅ Two-part merge complete")

        return nested_result

    except Exception as e:
        logger.error(f"[OPHTHAL_FORMATTER_SPLIT] ❌ Merge failed: {e}", exc_info=True)
        # Return merged flat data as fallback
        return {**part1_data, **part2_data}

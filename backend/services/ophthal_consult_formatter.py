"""
OPHTHALMOLOGY FULL CONSULTATION Formatter Service

Reconstructs nested structure from flattened Gemini extraction results.
Converts flat schema output back to the expected nested format for
frontend, webhook, and external APIs.

This is the most complex ophthalmology formatter supporting all 26 sections
of a comprehensive ophthalmic examination, including:
- Extended history (systemicIllness, familyHistory, allergies, pastGlassesPrescription)
- Additional VA fields (pinholeVision, nearAdd, nearVision)
- Document metadata (formSubtype, referralType, nextReview, sourceSchema)
- Quality metadata (lowConfidenceFields)
- Additional data catch-all for schema transformation

Supports both:
1. Single flattened extraction (full schema)
2. Two-part extraction (if needed for very large datasets)
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def format_ophthal_full_consult(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested OPHTHALMOLOGY FULL CONSULTATION structure from flattened extraction.

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching expected API format (26 top-level sections)
    """
    try:
        logger.info("[OPHTHAL_FULL_CONSULT_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== SECTION 1: PATIENT DEMOGRAPHICS (RECONSTRUCT OBJECT) ==========
        nested["patientDemographics"] = {
            "name": flat_data.get("patientDemographics_name", ""),
            "mrNumber": flat_data.get("patientDemographics_mrNumber", ""),
            "age": flat_data.get("patientDemographics_age", ""),
            "gender": flat_data.get("patientDemographics_gender", ""),
            "consultationDate": flat_data.get("patientDemographics_consultationDate", ""),
            "visitId": flat_data.get("patientDemographics_visitId", ""),
            "doctorName": flat_data.get("patientDemographics_doctorName", "")
        }

        # ========== SECTION 1A: EXTENDED HISTORY (NEW) ==========
        nested["extendedHistory"] = {
            "systemicIllness": flat_data.get("extendedHistory_systemicIllness", ""),
            "familyHistory": flat_data.get("extendedHistory_familyHistory", ""),
            "allergies": flat_data.get("extendedHistory_allergies", ""),
            "pastGlassesPrescription": flat_data.get("extendedHistory_pastGlassesPrescription", "")
        }

        # ========== SECTIONS 2-4: SIMPLE CLINICAL HISTORY FIELDS ==========
        nested["pastOcularHistory"] = flat_data.get("pastOcularHistory", "N/A")
        nested["currentTreatment"] = flat_data.get("currentTreatment", "N/A")
        nested["complaints"] = flat_data.get("complaints", "N/A")

        # ========== SECTION 5: VISUAL ACUITY AND REFRACTION (RECONSTRUCT 2-LEVEL NESTED WITH NEW FIELDS) ==========
        nested["visualAcuityAndRefraction"] = {
            "rightEye": {
                "unaidedVision": flat_data.get("visualAcuityAndRefraction_rightEye_unaidedVision", "N/A"),
                "aidedVision": flat_data.get("visualAcuityAndRefraction_rightEye_aidedVision", "N/A"),
                "patientGlasses": flat_data.get("visualAcuityAndRefraction_rightEye_patientGlasses", "N/A"),
                "pinholeVision": flat_data.get("visualAcuityAndRefraction_rightEye_pinholeVision", "N/A"),
                "nearAdd": flat_data.get("visualAcuityAndRefraction_rightEye_nearAdd", "N/A"),
                "nearVision": flat_data.get("visualAcuityAndRefraction_rightEye_nearVision", "N/A"),
                "refractionSphere": flat_data.get("visualAcuityAndRefraction_rightEye_refractionSphere"),
                "refractionCylinder": flat_data.get("visualAcuityAndRefraction_rightEye_refractionCylinder"),
                "refractionAxis": flat_data.get("visualAcuityAndRefraction_rightEye_refractionAxis")
            },
            "leftEye": {
                "unaidedVision": flat_data.get("visualAcuityAndRefraction_leftEye_unaidedVision", "N/A"),
                "aidedVision": flat_data.get("visualAcuityAndRefraction_leftEye_aidedVision", "N/A"),
                "patientGlasses": flat_data.get("visualAcuityAndRefraction_leftEye_patientGlasses", "N/A"),
                "pinholeVision": flat_data.get("visualAcuityAndRefraction_leftEye_pinholeVision", "N/A"),
                "nearAdd": flat_data.get("visualAcuityAndRefraction_leftEye_nearAdd", "N/A"),
                "nearVision": flat_data.get("visualAcuityAndRefraction_leftEye_nearVision", "N/A"),
                "refractionSphere": flat_data.get("visualAcuityAndRefraction_leftEye_refractionSphere"),
                "refractionCylinder": flat_data.get("visualAcuityAndRefraction_leftEye_refractionCylinder"),
                "refractionAxis": flat_data.get("visualAcuityAndRefraction_leftEye_refractionAxis")
            }
        }

        # ========== SECTION 6: KERATOMETRY (RECONSTRUCT 2-LEVEL NESTED) ==========
        nested["keratometry"] = {
            "rightEye": {
                "horizontal": flat_data.get("keratometry_rightEye_horizontal"),
                "horizontalAxis": flat_data.get("keratometry_rightEye_horizontalAxis"),
                "vertical": flat_data.get("keratometry_rightEye_vertical"),
                "verticalAxis": flat_data.get("keratometry_rightEye_verticalAxis")
            },
            "leftEye": {
                "horizontal": flat_data.get("keratometry_leftEye_horizontal"),
                "horizontalAxis": flat_data.get("keratometry_leftEye_horizontalAxis"),
                "vertical": flat_data.get("keratometry_leftEye_vertical"),
                "verticalAxis": flat_data.get("keratometry_leftEye_verticalAxis")
            }
        }

        # ========== SECTION 7: COVER TEST WITH GLASS (RECONSTRUCT OBJECT) ==========
        nested["coverTestWithGlass"] = {
            "coverTestDist": flat_data.get("coverTestWithGlass_coverTestDist", "N/A"),
            "coverTestNear": flat_data.get("coverTestWithGlass_coverTestNear", "N/A"),
            "uncoverTestDist": flat_data.get("coverTestWithGlass_uncoverTestDist", "N/A"),
            "uncoverTestNear": flat_data.get("coverTestWithGlass_uncoverTestNear", "N/A"),
            "alternateCoverTestDist": flat_data.get("coverTestWithGlass_alternateCoverTestDist", "N/A"),
            "alternateCoverTestNear": flat_data.get("coverTestWithGlass_alternateCoverTestNear", "N/A")
        }

        # ========== SECTION 8: COVER TEST WITHOUT GLASS (RECONSTRUCT OBJECT) ==========
        nested["coverTestWithoutGlass"] = {
            "coverTestDist": flat_data.get("coverTestWithoutGlass_coverTestDist", "N/A"),
            "coverTestNear": flat_data.get("coverTestWithoutGlass_coverTestNear", "N/A"),
            "uncoverTestDist": flat_data.get("coverTestWithoutGlass_uncoverTestDist", "N/A"),
            "uncoverTestNear": flat_data.get("coverTestWithoutGlass_uncoverTestNear", "N/A"),
            "alternateCoverTestDist": flat_data.get("coverTestWithoutGlass_alternateCoverTestDist", "N/A"),
            "alternateCoverTestNear": flat_data.get("coverTestWithoutGlass_alternateCoverTestNear", "N/A")
        }

        # ========== SECTION 9: BINOCULAR VISION TESTS (RECONSTRUCT OBJECT) ==========
        nested["binocularVisionTests"] = {
            "fixationDist": flat_data.get("binocularVisionTests_fixationDist", "N/A"),
            "fixationNear": flat_data.get("binocularVisionTests_fixationNear", "N/A"),
            "stereopsisDist": flat_data.get("binocularVisionTests_stereopsisDist", "N/A"),
            "stereopsisNear": flat_data.get("binocularVisionTests_stereopsisNear", "N/A"),
            "avPatternDist": flat_data.get("binocularVisionTests_avPatternDist", "N/A"),
            "avPatternNear": flat_data.get("binocularVisionTests_avPatternNear", "N/A"),
            "worthFourDotDist": flat_data.get("binocularVisionTests_worthFourDotDist", "N/A"),
            "worthFourDotNear": flat_data.get("binocularVisionTests_worthFourDotNear", "N/A"),
            "bagoliniDist": flat_data.get("binocularVisionTests_bagoliniDist", "N/A"),
            "bagoliniNear": flat_data.get("binocularVisionTests_bagoliniNear", "N/A"),
            "faceExternalExamDist": flat_data.get("binocularVisionTests_faceExternalExamDist", "N/A"),
            "faceExternalExamNear": flat_data.get("binocularVisionTests_faceExternalExamNear", "N/A")
        }

        # ========== SECTION 10: MACULAR FUNCTION TESTS (RECONSTRUCT OBJECT) ==========
        nested["macularFunctionTests"] = {
            "colorVisionOD": flat_data.get("macularFunctionTests_colorVisionOD", "N/A"),
            "colorVisionOS": flat_data.get("macularFunctionTests_colorVisionOS", "N/A"),
            "amslersTestOD": flat_data.get("macularFunctionTests_amslersTestOD", "N/A"),
            "amslersTestOS": flat_data.get("macularFunctionTests_amslersTestOS", "N/A")
        }

        # ========== SECTION 11: PBCT CHARTS (RECONSTRUCT 2D ARRAYS OR STRINGS) ==========
        # Handle PBCT charts - could be 2D arrays or flattened strings
        pbct_od = flat_data.get("pbctCharts_pbctOD", [])
        pbct_os = flat_data.get("pbctCharts_pbctOS", [])

        nested["pbctCharts"] = {
            "pbctOD": pbct_od if isinstance(pbct_od, list) else [],
            "pbctOS": pbct_os if isinstance(pbct_os, list) else []
        }

        # ========== SECTION 12: DIPLOPIA CHARTING (SIMPLE FIELD) ==========
        nested["diplopiaCharting"] = flat_data.get("diplopiaCharting", "N/A")

        # ========== SECTION 13: DRY EYE ASSESSMENT (RECONSTRUCT OBJECT) ==========
        nested["dryEyeAssessment"] = {
            "osdiQuestionnaire": flat_data.get("dryEyeAssessment_osdiQuestionnaire", "N/A"),
            "schimersTest1OD": flat_data.get("dryEyeAssessment_schimersTest1OD"),
            "schimersTest1OS": flat_data.get("dryEyeAssessment_schimersTest1OS"),
            "schimersTest2OD": flat_data.get("dryEyeAssessment_schimersTest2OD"),
            "schimersTest2OS": flat_data.get("dryEyeAssessment_schimersTest2OS"),
            "tearFilmBreakupTimeOD": flat_data.get("dryEyeAssessment_tearFilmBreakupTimeOD"),
            "tearFilmBreakupTimeOS": flat_data.get("dryEyeAssessment_tearFilmBreakupTimeOS"),
            "fluoresceinStainingOD": flat_data.get("dryEyeAssessment_fluoresceinStainingOD", "N/A"),
            "fluoresceinStainingOS": flat_data.get("dryEyeAssessment_fluoresceinStainingOS", "N/A"),
            "lissamineGreenOD": flat_data.get("dryEyeAssessment_lissamineGreenOD", "N/A"),
            "lissamineGreenOS": flat_data.get("dryEyeAssessment_lissamineGreenOS", "N/A")
        }

        # ========== SECTION 14: SLIT LAMP EXAMINATION (RECONSTRUCT 2-LEVEL NESTED) ==========
        nested["slitLampExamination"] = {
            "rightEye": {
                "lids": flat_data.get("slitLampExamination_rightEye_lids", "N/A"),
                "conjunctiva": flat_data.get("slitLampExamination_rightEye_conjunctiva", "N/A"),
                "cornea": flat_data.get("slitLampExamination_rightEye_cornea", "N/A"),
                "anteriorChamber": flat_data.get("slitLampExamination_rightEye_anteriorChamber", "N/A"),
                "iris": flat_data.get("slitLampExamination_rightEye_iris", "N/A"),
                "lens": flat_data.get("slitLampExamination_rightEye_lens", "N/A"),
                "pupil": flat_data.get("slitLampExamination_rightEye_pupil", "N/A")
            },
            "leftEye": {
                "lids": flat_data.get("slitLampExamination_leftEye_lids", "N/A"),
                "conjunctiva": flat_data.get("slitLampExamination_leftEye_conjunctiva", "N/A"),
                "cornea": flat_data.get("slitLampExamination_leftEye_cornea", "N/A"),
                "anteriorChamber": flat_data.get("slitLampExamination_leftEye_anteriorChamber", "N/A"),
                "iris": flat_data.get("slitLampExamination_leftEye_iris", "N/A"),
                "lens": flat_data.get("slitLampExamination_leftEye_lens", "N/A"),
                "pupil": flat_data.get("slitLampExamination_leftEye_pupil", "N/A")
            },
            "imageNotes": flat_data.get("slitLampExamination_imageNotes", "N/A")
        }

        # ========== SECTION 15: INTRAOCULAR PRESSURE (RECONSTRUCT WITH ARRAY OF OBJECTS) ==========
        # Reconstruct from parallel arrays
        iop_methods = flat_data.get("intraocularpressure_methods", [])
        iop_times = flat_data.get("intraocularpressure_times", [])
        iop_rightEye = flat_data.get("intraocularpressure_rightEyeIOPs", [])
        iop_leftEye = flat_data.get("intraocularpressure_leftEyeIOPs", [])

        iop_measurements = []
        for i, method in enumerate(iop_methods):
            if method:  # Only add if method exists
                iop_measurements.append({
                    "method": method,
                    "time": iop_times[i] if i < len(iop_times) else "",
                    "rightEyeIOP": iop_rightEye[i] if i < len(iop_rightEye) else None,
                    "leftEyeIOP": iop_leftEye[i] if i < len(iop_leftEye) else None
                })

        nested["intraocularpressure"] = {
            "measurements": iop_measurements,
            "pachymetryOD": flat_data.get("intraocularpressure_pachymetryOD"),
            "pachymetryOS": flat_data.get("intraocularpressure_pachymetryOS"),
            "pachymetryAdjustedIOPOD": flat_data.get("intraocularpressure_pachymetryAdjustedIOPOD"),
            "pachymetryAdjustedIOPOS": flat_data.get("intraocularpressure_pachymetryAdjustedIOPOS")
        }

        # ========== SECTION 16: GONIOSCOPY (SIMPLE FIELD) ==========
        nested["gonioscopy"] = flat_data.get("gonioscopy", "N/A")

        # ========== SECTION 17: FUNDUS EXAMINATION (RECONSTRUCT 2-LEVEL NESTED) ==========
        nested["fundusExamination"] = {
            "dilationStatus": flat_data.get("fundusExamination_dilationStatus", "N/A"),
            "rightEye": {
                "disc": flat_data.get("fundusExamination_rightEye_disc", "N/A"),
                "macula": flat_data.get("fundusExamination_rightEye_macula", "N/A"),
                "generalFundus": flat_data.get("fundusExamination_rightEye_generalFundus", "N/A")
            },
            "leftEye": {
                "disc": flat_data.get("fundusExamination_leftEye_disc", "N/A"),
                "macula": flat_data.get("fundusExamination_leftEye_macula", "N/A"),
                "generalFundus": flat_data.get("fundusExamination_leftEye_generalFundus", "N/A")
            }
        }

        # ========== SECTION 18: DIURNAL IOP VARIATION (RECONSTRUCT ARRAY OF OBJECTS) ==========
        diurnal_methods = flat_data.get("diurnalIOPVariation_methods", [])
        diurnal_times = flat_data.get("diurnalIOPVariation_times", [])
        diurnal_rightEye = flat_data.get("diurnalIOPVariation_rightEyeIOPs", [])
        diurnal_leftEye = flat_data.get("diurnalIOPVariation_leftEyeIOPs", [])

        diurnal_measurements = []
        for i, method in enumerate(diurnal_methods):
            if method:  # Only add if method exists
                diurnal_measurements.append({
                    "method": method,
                    "time": diurnal_times[i] if i < len(diurnal_times) else "",
                    "rightEyeIOP": diurnal_rightEye[i] if i < len(diurnal_rightEye) else None,
                    "leftEyeIOP": diurnal_leftEye[i] if i < len(diurnal_leftEye) else None
                })

        nested["diurnalIOPVariation"] = diurnal_measurements

        # ========== SECTION 19: VISUAL FIELD ANALYSIS (RECONSTRUCT OBJECT) ==========
        nested["visualFieldAnalysis"] = {
            "strategy": flat_data.get("visualFieldAnalysis_strategy", "N/A"),
            "interpretation": flat_data.get("visualFieldAnalysis_interpretation", "N/A"),
            "meanDeviation": flat_data.get("visualFieldAnalysis_meanDeviation", "N/A"),
            "patternDeviation": flat_data.get("visualFieldAnalysis_patternDeviation", "N/A"),
            "ght": flat_data.get("visualFieldAnalysis_ght", "N/A"),
            "vfi": flat_data.get("visualFieldAnalysis_vfi", "N/A"),
            "oct": flat_data.get("visualFieldAnalysis_oct", "N/A"),
            "targetIOP": flat_data.get("visualFieldAnalysis_targetIOP", "N/A")
        }

        # ========== SECTION 20: DIAGNOSIS (SIMPLE FIELD) ==========
        nested["diagnosis"] = flat_data.get("diagnosis", "N/A")

        # ========== SECTION 21: PROCEDURES (ARRAY OF STRINGS) ==========
        procedures = flat_data.get("procedures", [])
        if isinstance(procedures, str) and procedures.strip():
            procedures = [procedures]
        elif not isinstance(procedures, list):
            procedures = []
        nested["procedures"] = procedures

        # ========== SECTION 22: DOCTOR RECOMMENDATION (SIMPLE FIELD) ==========
        nested["doctorRecommendation"] = flat_data.get("doctorRecommendation", "N/A")

        # ========== SECTION 23: DOCTOR NOTES AND INVESTIGATION ==========
        nested["doctorNotes"] = flat_data.get("doctorNotes", "N/A")

        investigation = flat_data.get("investigation", [])
        if isinstance(investigation, str) and investigation.strip():
            investigation = [investigation]
        elif not isinstance(investigation, list):
            investigation = []
        nested["investigation"] = investigation

        # ========== SECTION 24: DOCUMENT METADATA (NEW - OPTIONAL) ==========
        nested["documentMetadata"] = {
            "formSubtype": flat_data.get("documentMetadata_formSubtype", ""),
            "referralType": flat_data.get("documentMetadata_referralType", ""),
            "nextReview": flat_data.get("documentMetadata_nextReview", ""),
            "sourceSchema": flat_data.get("documentMetadata_sourceSchema", "")
        }

        # ========== SECTION 25: QUALITY METADATA (NEW - OPTIONAL) ==========
        low_confidence = flat_data.get("qualityMetadata_lowConfidenceFields", [])
        if isinstance(low_confidence, str) and low_confidence.strip():
            low_confidence = [low_confidence]
        elif not isinstance(low_confidence, list):
            low_confidence = []
        nested["qualityMetadata"] = {
            "lowConfidenceFields": low_confidence
        }

        # ========== SECTION 26: ADDITIONAL DATA (NEW - OPTIONAL CATCH-ALL) ==========
        # additionalData is now an array of key-value pairs: [{"key": "...", "value": "..."}, ...]
        additional_data = flat_data.get("additionalData", [])
        if isinstance(additional_data, list):
            nested["additionalData"] = additional_data
        elif isinstance(additional_data, dict):
            # Convert dict to array format for backward compatibility
            nested["additionalData"] = [
                {"key": k, "value": str(v)} for k, v in additional_data.items()
            ]
        else:
            nested["additionalData"] = []

        logger.info(
            f"[OPHTHAL_FULL_CONSULT_FORMATTER] ✅ Reconstruction complete - "
            f"26 top-level sections reconstructed, "
            f"{len(iop_measurements)} IOP measurements, "
            f"{len(diurnal_measurements)} diurnal measurements"
        )

        return nested

    except Exception as e:
        logger.error(f"[OPHTHAL_FULL_CONSULT_FORMATTER] ❌ Reconstruction failed: {e}", exc_info=True)
        # Return flat data as fallback
        return flat_data


def format_ophthal_full_consult_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge and reconstruct OPHTHALMOLOGY FULL CONSULTATION from two-part extraction.

    This function handles split schema approach where extraction is done
    in two separate Gemini API calls to avoid schema complexity limits.

    Args:
        part1_data: First part extraction result
        part2_data: Second part extraction result

    Returns:
        Nested structure matching expected API format
    """
    try:
        logger.info("[OPHTHAL_FULL_CONSULT_FORMATTER_SPLIT] Starting merge of Part 1 and Part 2 extractions")

        # Merge both parts into a single flat dictionary
        # For arrays, concatenate them
        merged_flat = {}

        # Merge regular fields
        for key, value in part1_data.items():
            if isinstance(value, list) and key in part2_data and isinstance(part2_data[key], list):
                # Concatenate arrays
                merged_flat[key] = value + part2_data[key]
            else:
                merged_flat[key] = value

        # Add fields from part2 that aren't in part1
        for key, value in part2_data.items():
            if key not in merged_flat:
                merged_flat[key] = value

        logger.info(
            f"[OPHTHAL_FULL_CONSULT_FORMATTER_SPLIT] Merged {len(part1_data)} fields from Part 1 + "
            f"{len(part2_data)} fields from Part 2 = {len(merged_flat)} total fields"
        )

        # Use existing formatter to reconstruct nested structure
        nested_result = format_ophthal_full_consult(merged_flat)

        logger.info("[OPHTHAL_FULL_CONSULT_FORMATTER_SPLIT] ✅ Two-part merge complete")

        return nested_result

    except Exception as e:
        logger.error(f"[OPHTHAL_FULL_CONSULT_FORMATTER_SPLIT] ❌ Merge failed: {e}", exc_info=True)
        # Return merged flat data as fallback
        return {**part1_data, **part2_data}

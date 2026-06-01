"""
OPHTHALMOLOGY DISCHARGE Formatter Service

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


def format_ophthal_discharge(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested OPHTHALMOLOGY DISCHARGE structure from flattened extraction.

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching expected API format
    """
    try:
        logger.info("[OPHTHAL_DISCHARGE_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== SECTION 1: STUDENT DEMOGRAPHICS (RECONSTRUCT OBJECT) ==========
        nested["patientDemographics"] = {
            "name": flat_data.get("patientDemographics_name", ""),
            "visitId": flat_data.get("patientDemographics_visitId", ""),
            "mrNumber": flat_data.get("patientDemographics_mrNumber", ""),
            "date": flat_data.get("patientDemographics_date", ""),
            "age": flat_data.get("patientDemographics_age", ""),
            "gender": flat_data.get("patientDemographics_gender", "")
        }

        # ========== SECTION 2: ADMISSION DETAILS (RECONSTRUCT OBJECT) ==========
        nested["admissionDetails"] = {
            "dateOfAdmission": flat_data.get("admissionDetails_dateOfAdmission", ""),
            "dateOfProcedure": flat_data.get("admissionDetails_dateOfProcedure", "")
        }

        # ========== SECTION 3: MEDICAL TEAM (RECONSTRUCT ARRAY OF OBJECTS) ==========
        # Reconstruct from parallel arrays
        counsellor_names = flat_data.get("medicalTeam_doctorNames", [])
        doctor_regNumbers = flat_data.get("medicalTeam_doctorRegistrationNumbers", [])

        counsellors_attended = []
        for i, name in enumerate(counsellor_names):
            reg_number = doctor_regNumbers[i] if i < len(doctor_regNumbers) else ""
            if name:  # Only add if name exists
                counsellors_attended.append({
                    "name": name,
                    "registrationNumber": reg_number
                })

        nested["medicalTeam"] = {
            "doctorsAttended": counsellors_attended
        }

        # ========== SECTION 4: DIAGNOSIS (RECONSTRUCT OBJECT) ==========
        nested["diagnosis"] = {
            "rightEye": flat_data.get("diagnosis_rightEye", "N/A"),
            "leftEye": flat_data.get("diagnosis_leftEye", "N/A"),
            "bothEyes": flat_data.get("diagnosis_bothEyes", "N/A")
        }

        # ========== SECTION 5: ADMISSION STATUS (RECONSTRUCT OBJECT) ==========
        nested["admissionStatus"] = {
            "conditionOnAdmission": flat_data.get("admissionStatus_conditionOnAdmission", "N/A"),
            "nutritionalStatus": flat_data.get("admissionStatus_nutritionalStatus", "N/A")
        }

        # ========== SECTION 6: TREATMENT GIVEN (RECONSTRUCT OBJECT) ==========
        nested["treatmentGiven"] = {
            "eye": flat_data.get("treatmentGiven_eye", ""),
            "procedure": flat_data.get("treatmentGiven_procedure", ""),
            "technique": flat_data.get("treatmentGiven_technique", ""),
            "anesthesia": flat_data.get("treatmentGiven_anesthesia", ""),
            "date": flat_data.get("treatmentGiven_date", ""),
            "additionalDetails": flat_data.get("treatmentGiven_additionalDetails", "")
        }

        # ========== SECTION 7: DISCHARGE STATUS (RECONSTRUCT OBJECT) ==========
        nested["dischargeStatus"] = {
            "conditionOnDischarge": flat_data.get("dischargeStatus_conditionOnDischarge", "N/A")
        }

        # ========== SECTION 8: DISCHARGE MEDICATION (RECONSTRUCT ARRAY OF OBJECTS) ==========
        # Reconstruct from parallel arrays
        med_names = flat_data.get("dischargeMedication_medicationNames", [])
        med_dosages = flat_data.get("dischargeMedication_dosages", [])
        med_frequencies = flat_data.get("dischargeMedication_frequencies", [])
        med_routes = flat_data.get("dischargeMedication_routes", [])
        med_eyes = flat_data.get("dischargeMedication_eyes", [])
        med_durations = flat_data.get("dischargeMedication_durations", [])
        med_timings = flat_data.get("dischargeMedication_timings", [])
        med_instructions = flat_data.get("dischargeMedication_instructions", [])

        discharge_medications = []
        for i, med_name in enumerate(med_names):
            if med_name:  # Only add if medication name exists
                discharge_medications.append({
                    "medicationName": med_name,
                    "dosage": med_dosages[i] if i < len(med_dosages) else "",
                    "frequency": med_frequencies[i] if i < len(med_frequencies) else "",
                    "route": med_routes[i] if i < len(med_routes) else "",
                    "eye": med_eyes[i] if i < len(med_eyes) else "N/A",
                    "duration": med_durations[i] if i < len(med_durations) else "",
                    "timing": med_timings[i] if i < len(med_timings) else "",
                    "instructions": med_instructions[i] if i < len(med_instructions) else ""
                })

        nested["dischargeMedication"] = discharge_medications

        # ========== SECTION 9: DISCHARGE ADVICE (RECONSTRUCT OBJECT WITH ARRAY) ==========
        special_instructions = flat_data.get("dischargeAdvice_specialInstructions", [])
        if isinstance(special_instructions, str) and special_instructions.strip():
            # If single string provided, convert to array
            special_instructions = [special_instructions]
        elif not isinstance(special_instructions, list):
            special_instructions = []

        nested["dischargeAdvice"] = {
            "diet": flat_data.get("dischargeAdvice_diet", "N/A"),
            "physicalActivity": flat_data.get("dischargeAdvice_physicalActivity", "N/A"),
            "specialInstructions": special_instructions,
            "nextReview": flat_data.get("dischargeAdvice_nextReview", "")
        }

        # ========== SECTION 10: EMERGENCY CONTACT (RECONSTRUCT OBJECT WITH ARRAY AND NESTED OBJECT) ==========
        emergency_symptoms = flat_data.get("emergencyContact_emergencySymptoms", [])
        if isinstance(emergency_symptoms, str) and emergency_symptoms.strip():
            # If single string provided, convert to array
            emergency_symptoms = [emergency_symptoms]
        elif not isinstance(emergency_symptoms, list):
            emergency_symptoms = []

        nested["emergencyContact"] = {
            "emergencySymptoms": emergency_symptoms,
            "hospitalContactDetails": {
                "telephoneNumber": flat_data.get("emergencyContact_hospitalContactDetails_telephoneNumber", ""),
                "contactPersonName": flat_data.get("emergencyContact_hospitalContactDetails_contactPersonName", ""),
                "mobileNumber": flat_data.get("emergencyContact_hospitalContactDetails_mobileNumber", ""),
                "emergencyNumber": flat_data.get("emergencyContact_hospitalContactDetails_emergencyNumber", "")
            }
        }

        # ========== SECTION 11: PROVIDER INFORMATION (RECONSTRUCT OBJECT) ==========
        nested["providerInformation"] = {
            "signature": flat_data.get("providerInformation_signature", ""),
            "registrationNumber": flat_data.get("providerInformation_registrationNumber", ""),
            "seal": flat_data.get("providerInformation_seal", "")
        }

        logger.info(
            f"[OPHTHAL_DISCHARGE_FORMATTER] ✅ Reconstruction complete - "
            f"11 top-level sections reconstructed, "
            f"{len(counsellors_attended)} counsellors, {len(discharge_medications)} medications"
        )

        return nested

    except Exception as e:
        logger.error(f"[OPHTHAL_DISCHARGE_FORMATTER] ❌ Reconstruction failed: {e}", exc_info=True)
        # Return flat data as fallback
        return flat_data


def format_ophthal_discharge_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge and reconstruct OPHTHALMOLOGY DISCHARGE from two-part extraction.

    This function handles split schema approach where extraction is done
    in two separate Gemini API calls to avoid schema complexity limits.

    Args:
        part1_data: First part extraction result
        part2_data: Second part extraction result

    Returns:
        Nested structure matching expected API format
    """
    try:
        logger.info("[OPHTHAL_DISCHARGE_FORMATTER_SPLIT] Starting merge of Part 1 and Part 2 extractions")

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
            f"[OPHTHAL_DISCHARGE_FORMATTER_SPLIT] Merged {len(part1_data)} fields from Part 1 + "
            f"{len(part2_data)} fields from Part 2 = {len(merged_flat)} total fields"
        )

        # Use existing formatter to reconstruct nested structure
        nested_result = format_ophthal_discharge(merged_flat)

        logger.info("[OPHTHAL_DISCHARGE_FORMATTER_SPLIT] ✅ Two-part merge complete")

        return nested_result

    except Exception as e:
        logger.error(f"[OPHTHAL_DISCHARGE_FORMATTER_SPLIT] ❌ Merge failed: {e}", exc_info=True)
        # Return merged flat data as fallback
        return {**part1_data, **part2_data}

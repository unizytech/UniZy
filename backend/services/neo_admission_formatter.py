"""
NEONATAL_ADMISSION Formatter Service

Reconstructs nested structure from flattened Gemini extraction results.
Converts flat schema output back to the expected nested format for
frontend, webhook, and external APIs.

Supports two-part extraction:
- Part 1: Baby, admission, pregnancy, resuscitation details
- Part 2: Clinical assessment, procedures, scores, diagnosis
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def format_neo_admission(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested NEONATAL_ADMISSION structure from flattened extraction.

    Output matches the neopaed API sample schema with:
    - uhid, visitNumber, admissionDateTime at top level
    - Single admission object (admin info + physical exam merged)
    - baby object (name + resuscitation fields)
    - scores wrapper (crib2 + snappe2 nested)
    - additionalDiagnosis as simple string array

    Args:
        flat_data: Flattened extraction result from Gemini

    Returns:
        Nested structure matching neopaed API format
    """
    try:
        logger.info("[NEO_ADMISSION_FORMATTER] Starting reconstruction of nested structure")

        nested = {}

        # ========== SECTION 1: TOP-LEVEL FIELDS ==========
        # uhid is injected from patient_info by extraction_service
        nested["uhid"] = flat_data.get("uhid", "")
        nested["visitNumber"] = flat_data.get("visitNumber", "") or flat_data.get("admission_visitNumber", "")
        nested["admissionDateTime"] = flat_data.get("admissionDateTime", "") or flat_data.get("admission_admissionDate", "")

        # ========== SECTION 2: ADMISSION (admin + physical exam + referral merged) ==========
        seen_by_ids = flat_data.get("admission_seenByIds", []) or []
        nested["admission"] = {
            "typeOfCare": flat_data.get("admission_typeOfCare", ""),
            "admissionWt": flat_data.get("admission_admissionWt", ""),
            "surgeon": flat_data.get("admission_surgeon", ""),
            "hospitalName": flat_data.get("admission_hospitalName", ""),
            "seenBy": seen_by_ids,
            "referredBy": flat_data.get("referredBy", ""),
            "referralReason": flat_data.get("referralReason", ""),
            "admittedFrom": flat_data.get("admissionDetails_admittedFrom", ""),
            "majorComplaints": flat_data.get("admissionDetails_majorComplaints", ""),
            "ventilation": flat_data.get("admissionDetails_ventilation", ""),
            "mode": flat_data.get("admissionDetails_mode", ""),
            "retractions": flat_data.get("admissionDetails_retractions", ""),
            "airEntry": flat_data.get("admissionDetails_airEntry", ""),
            "chestMovement": flat_data.get("admissionDetails_chestMovement", ""),
            "hr": flat_data.get("admissionDetails_hr", ""),
            "systolicBp": flat_data.get("admissionDetails_systolicBp", ""),
            "diastolic_bp": flat_data.get("admissionDetails_diastolicBp", ""),
            "meanBP": flat_data.get("admissionDetails_meanBP", ""),
            "centralPulses": flat_data.get("admissionDetails_centralPulses", ""),
            "peripheralPulses": flat_data.get("admissionDetails_peripheralPulses", ""),
            "femoralPulses": flat_data.get("admissionDetails_femoralPulses", ""),
            "s1s2": flat_data.get("admissionDetails_s1s2", ""),
            "murmur": flat_data.get("admissionDetails_murmur", ""),
            "cft": flat_data.get("admissionDetails_cft", ""),
            "color": flat_data.get("admissionDetails_color", ""),
            "temperature": flat_data.get("admissionDetails_temperature", ""),
            "abdomen": flat_data.get("admissionDetails_abdomen", ""),
            "bowelSounds": flat_data.get("admissionDetails_bowelSounds", ""),
            "umbilicus": flat_data.get("admissionDetails_umbilicus", ""),
            "hepatomegaly": flat_data.get("admissionDetails_hepatomegaly", ""),
            "splenomegaly": flat_data.get("admissionDetails_splenomegaly", ""),
            "herina": flat_data.get("admissionDetails_herina", ""),
            "genitalia": flat_data.get("admissionDetails_genitalia", ""),
            "pupils": flat_data.get("admissionDetails_pupils", ""),
            "anteriorFontanelle": flat_data.get("admissionDetails_anteriorFontanelle", ""),
            "activity": flat_data.get("admissionDetails_activity", ""),
            "cry": flat_data.get("admissionDetails_cry", ""),
            "seizures": flat_data.get("admissionDetails_seizures", ""),
            "neonatalReflexes": flat_data.get("admissionDetails_neonatalReflexes", ""),
            "abnormalities": flat_data.get("admissionDetails_abnormalities", ""),
            "initialBloodGas": flat_data.get("admissionDetails_initialBloodGas", ""),
            "ageTime": flat_data.get("admissionDetails_ageTime", ""),
            "spo2": flat_data.get("admissionDetails_spo2", ""),
            "lactate": flat_data.get("admissionDetails_lactate", ""),
            "ph": flat_data.get("admissionDetails_ph", ""),
            "bloodGasBaseExcess": flat_data.get("admissionDetails_bloodGasBaseExcess", ""),
            "paO2": flat_data.get("admissionDetails_paO2", ""),
            "paCo2": flat_data.get("admissionDetails_paCo2", ""),
            "hco3": flat_data.get("admissionDetails_hco3", ""),
            "hct": flat_data.get("admissionDetails_hct", ""),
            "rbs": flat_data.get("admissionDetails_rbs", ""),
            "initialAssessmentCompletedDateTime": flat_data.get("admissionDetails_initialAssessmentCompletedDateTime", "")
        }

        # ========== SECTION 3: BABY (name + resuscitation) ==========
        nested["baby"] = {
            "name": flat_data.get("baby_name", ""),
            "descriptionOfResuscitation": flat_data.get("babyDetails_descriptionOfResuscitation", ""),
            "ventilationRequired": flat_data.get("babyDetails_ventilationRequired", ""),
            "surfactantGiven": flat_data.get("babyDetails_surfactantGiven", ""),
            "surfactantType": flat_data.get("babyDetails_surfactantType", ""),
            "dose": flat_data.get("babyDetails_dose", ""),
            "dateOfAdministration": flat_data.get("babyDetails_dateofAdministration", ""),
            "ageAfterBirth": flat_data.get("babyDetails_ageAfterBirth", ""),
            "deliveryCpap": flat_data.get("babyDetails_deliveryCpap", ""),
            "airFlow": flat_data.get("babyDetails_airFlow", ""),
            "oxgenFlow": flat_data.get("babyDetails_oxgenFlow", ""),
            "transferFiO2": flat_data.get("babyDetails_transferFiO2", "")
        }

        # ========== SECTION 4: MEDICAL HISTORY ==========
        problem_ids = flat_data.get("medicalHistory_problemIds", []) or []
        problem_meds = flat_data.get("medicalHistory_problemMedications", []) or []
        medical_problems = []
        for i, problem_id in enumerate(problem_ids):
            med = problem_meds[i] if i < len(problem_meds) else ""
            medical_problems.append({"problemsId": problem_id, "medications": med})

        nested["medicalHistory"] = {
            "smoking": flat_data.get("medicalHistory_smoking", ""),
            "alcohol": flat_data.get("medicalHistory_alcohol", ""),
            "tobacco": flat_data.get("medicalHistory_tobacco", ""),
            "medicalProblems": medical_problems
        }

        # ========== SECTION 5: PREGNANCY ==========
        # Complications
        complication_ids = flat_data.get("pregnancy_complicationIds", []) or []
        complication_treatments = flat_data.get("pregnancy_complicationTreatments", []) or []
        complications = []
        for i, comp_id in enumerate(complication_ids):
            treatment = complication_treatments[i] if i < len(complication_treatments) else ""
            complications.append({"complicationId": comp_id, "treatment": treatment})

        # Other scans
        other_dates = flat_data.get("pregnancy_otherScan_dates", []) or []
        other_gestations = flat_data.get("pregnancy_otherScan_gestations", []) or []
        other_findings = flat_data.get("pregnancy_otherScan_findings", []) or []
        other_scans = []
        for i, date in enumerate(other_dates):
            other_scans.append({
                "date": date,
                "gestation": other_gestations[i] if i < len(other_gestations) else "",
                "findings": other_findings[i] if i < len(other_findings) else ""
            })

        # Doppler scans
        doppler_dates = flat_data.get("pregnancy_dopplerScan_dates", []) or []
        doppler_gestations = flat_data.get("pregnancy_dopplerScan_gestations", []) or []
        doppler_findings = flat_data.get("pregnancy_dopplerScan_findings", []) or []
        doppler_scans = []
        for i, date in enumerate(doppler_dates):
            doppler_scans.append({
                "date": date,
                "gestation": doppler_gestations[i] if i < len(doppler_gestations) else "",
                "findings": doppler_findings[i] if i < len(doppler_findings) else ""
            })

        nested["pregnancy"] = {
            "complication": complications,
            "datingScanDetails": {
                "date": flat_data.get("pregnancy_datingScan_date", ""),
                "gestation": flat_data.get("pregnancy_datingScan_gestation", ""),
                "findings": flat_data.get("pregnancy_datingScan_findings", "")
            },
            "anomalyScanDetails": {
                "date": flat_data.get("pregnancy_anomalyScan_date", ""),
                "gestation": flat_data.get("pregnancy_anomalyScan_gestation", ""),
                "findings": flat_data.get("pregnancy_anomalyScan_findings", "")
            },
            "otherScanDetails": other_scans,
            "dopplerScanDetails": doppler_scans
        }

        # ========== SECTION 6: SCORES (nested under wrapper) ==========
        nested["scores"] = {
            "crib2": {
                "sexBirthWtGestation": flat_data.get("crib2_sexBirthWtGestation", ""),
                "baseExcess": flat_data.get("crib2_baseExcess", "")
            },
            "snappe2": {
                "mbp": flat_data.get("snappe2_mbp", ""),
                "lowestTemperature": flat_data.get("snappe2_lowestTemperature", ""),
                "po2Fio2Ratio": flat_data.get("snappe2_po2Fio2Ratio", ""),
                "lowestSerumPh": flat_data.get("snappe2_lowestSerumPh", ""),
                "multipleSeizures": flat_data.get("snappe2_multipleSeizures", ""),
                "urineOutput": flat_data.get("snappe2_urineOutput", ""),
                "bWeight": flat_data.get("snappe2_bWeight", ""),
                "smallForGestationalAge": flat_data.get("snappe2_smallForGestationalAge", ""),
                "apgar5Mins": flat_data.get("snappe2_apgar5Mins", "")
            }
        }

        # ========== SECTION 7: DIAGNOSIS ==========
        diff_diagnoses = flat_data.get("diagnosis_differentialDiagnosis", []) or []
        add_diagnoses = flat_data.get("diagnosis_additionalDiagnoses", []) or []

        nested["diagnosis"] = {
            "differentialDiagnosis": diff_diagnoses,
            "additionalDiagnosis": add_diagnoses,
            "plan": flat_data.get("diagnosis_plan", ""),
            "parentsSpokenTo": flat_data.get("diagnosis_parentsSpokenTo", ""),
            "timeOfDiscussion": flat_data.get("diagnosis_timeOfDiscussion", ""),
            "mattersDiscussed": flat_data.get("diagnosis_mattersDiscussed", ""),
            "parentsAddressedBy": flat_data.get("diagnosis_parentsAddressedBy", ""),
            "indicationOfAdmission": flat_data.get("diagnosis_indicationOfAdmission", ""),
            "indicationOfAdmissionOther": flat_data.get("diagnosis_indicationOfAdmissionOther", "")
        }

        # ========== SECTION 8: PROCEDURES ==========
        antibiotic_ids = flat_data.get("procedures_ivAntibioticIds", []) or []
        nested["procedures"] = {
            "initialxray": flat_data.get("procedures_initialxray", ""),
            "chestXrayFindings": flat_data.get("procedures_chestXrayFindings", ""),
            "abdominalXrayFindings": flat_data.get("procedures_abdominalXrayFindings", ""),
            "uac": {
                "status": flat_data.get("procedures_uac_status", ""),
                "position": flat_data.get("procedures_uac_position")
            },
            "uvc": {
                "status": flat_data.get("procedures_uvc_status", ""),
                "position": flat_data.get("procedures_uvc_position")
            },
            "sepsisScreen": flat_data.get("procedures_sepsisScreen", ""),
            "indications": flat_data.get("procedures_indications", ""),
            "enteralFeeding": flat_data.get("procedures_enteralFeeding", ""),
            "fluids": flat_data.get("procedures_fluids"),
            "ivAntibiotic": [{"antibiotic": ab_id} for ab_id in antibiotic_ids]
        }

        logger.info("[NEO_ADMISSION_FORMATTER] Successfully reconstructed nested structure")
        return nested

    except Exception as e:
        logger.error(f"[NEO_ADMISSION_FORMATTER] Error reconstructing nested structure: {e}")
        raise


def format_neo_admission_from_parts(part1_data: Dict[str, Any], part2_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct nested NEONATAL_ADMISSION structure from two-part extraction.

    Args:
        part1_data: Part 1 extraction (baby, admission, pregnancy, resuscitation)
        part2_data: Part 2 extraction (clinical assessment, procedures, scores, diagnosis)

    Returns:
        Nested structure matching production API format
    """
    try:
        logger.info("[NEO_ADMISSION_FORMATTER] Merging Part 1 and Part 2 extraction results")

        # Merge both parts into single flat dict
        merged = {}
        merged.update(part1_data or {})
        merged.update(part2_data or {})

        # Use the standard formatter
        result = format_neo_admission(merged)

        logger.info("[NEO_ADMISSION_FORMATTER] Successfully merged two-part extraction")
        return result

    except Exception as e:
        logger.error(f"[NEO_ADMISSION_FORMATTER] Error merging parts: {e}")
        raise

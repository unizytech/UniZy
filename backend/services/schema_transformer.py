"""
Schema Transformer Service

Transforms between different ophthalmology JSON schemas for merge operations.
Handles conversion from external schema formats (like Reference Guide schema)
to the internal OPHTHAL_FULL schema format.

Key Features:
- Field mapping between different naming conventions (snake_case ↔ camelCase)
- Type conversion (integer age → string age, string IOP → number IOP)
- Routing flexible arrays (additional_tests) to structured sections
- Catch-all for unmapped fields (additionalData)
- Schema detection based on field patterns

Author: System
Date: 2025-12-02
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# SCHEMA DETECTION
# ============================================================================

def detect_schema_type(data: Dict[str, Any]) -> str:
    """
    Detect the schema type of incoming data based on field patterns.

    Args:
        data: JSON data to analyze

    Returns:
        Schema type identifier: "OPHTHAL_OCR", "OPHTHAL_FULL", or "UNKNOWN"
    """
    # OPHTHAL_OCR schema indicators (snake_case, separate eye keys)
    # This is the format produced by OCR extraction from ophthalmology forms
    ophthal_ocr_indicators = [
        "patient_info",
        "visual_acuity_od",
        "visual_acuity_os",
        "slit_lamp_od",
        "slit_lamp_os",
        "fundus_od",
        "fundus_os",
        "iop_measurements",
        "additional_tests",
        "form_subtype",
        "low_confidence_fields"
    ]

    # OPHTHAL_FULL schema indicators (camelCase, nested rightEye/leftEye)
    ophthal_full_indicators = [
        "patientDemographics",
        "visualAcuityAndRefraction",
        "slitLampExamination",
        "fundusExamination",
        "intraocularpressure",
        "binocularVisionTests",
        "dryEyeAssessment"
    ]

    # Flattened OPHTHAL_FULL indicators (underscore-joined)
    ophthal_full_flat_indicators = [
        "patientDemographics_name",
        "visualAcuityAndRefraction_rightEye_unaidedVision",
        "slitLampExamination_rightEye_lids"
    ]

    ocr_score = sum(1 for key in ophthal_ocr_indicators if key in data)
    ophthal_score = sum(1 for key in ophthal_full_indicators if key in data)
    ophthal_flat_score = sum(1 for key in ophthal_full_flat_indicators if key in data)

    if ocr_score >= 3:
        return "OPHTHAL_OCR"
    elif ophthal_score >= 3:
        return "OPHTHAL_FULL"
    elif ophthal_flat_score >= 2:
        return "OPHTHAL_FULL_FLAT"
    else:
        return "UNKNOWN"


# ============================================================================
# SCHEMA TRANSFORMER CLASS
# ============================================================================

class SchemaTransformer:
    """
    Transform between different ophthalmology schemas.

    Supports:
    - OPHTHAL_OCR → OPHTHAL_FULL transformation
    - Field mapping with type conversion
    - Flexible test routing to structured sections
    - Unmapped field catch-all
    - Sparse mode for merge operations (only populated fields)
    """

    # Values considered "empty" and skipped in sparse mode
    EMPTY_VALUES = [None, "", "N/A", "n/a", "NA", "na", "nil", "Nil", "NIL", [], {}]

    def __init__(self, sparse_mode: bool = False):
        """
        Initialize the schema transformer.

        Args:
            sparse_mode: If True, only include fields with actual values.
                        Empty/N/A fields are omitted from output.
                        Use this for merge operations where empty fields
                        should not override existing data.
        """
        self.sparse_mode = sparse_mode
        self.unmapped_fields: Dict[str, Any] = {}

    def _is_empty(self, value: Any) -> bool:
        """Check if a value is considered empty."""
        if value in self.EMPTY_VALUES:
            return True
        # Check for whitespace-only strings
        if isinstance(value, str) and value.strip() == "":
            return True
        return False

    def _filter_empty(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively filter out empty values from a dictionary.

        In sparse mode, removes:
        - None, empty strings, "N/A", "nil", etc.
        - Empty lists and dicts
        - Nested objects that become empty after filtering

        Args:
            data: Dictionary to filter

        Returns:
            Filtered dictionary with only populated values
        """
        if not self.sparse_mode:
            return data

        result = {}
        for key, value in data.items():
            # Recursively filter nested dicts
            if isinstance(value, dict):
                filtered_nested = self._filter_empty(value)
                if filtered_nested:  # Only include if not empty after filtering
                    result[key] = filtered_nested
            # Filter lists - remove empty items, keep non-empty
            elif isinstance(value, list):
                filtered_list = []
                for item in value:
                    if isinstance(item, dict):
                        filtered_item = self._filter_empty(item)
                        if filtered_item:
                            filtered_list.append(filtered_item)
                    elif not self._is_empty(item):
                        filtered_list.append(item)
                if filtered_list:  # Only include non-empty lists
                    result[key] = filtered_list
            # Include non-empty scalar values
            elif not self._is_empty(value):
                result[key] = value

        return result

    def _add_if_not_empty(self, result: Dict[str, Any], key: str, value: Any) -> None:
        """
        Add a key-value pair to result only if value is not empty (in sparse mode).

        In non-sparse mode, always adds the value.

        Args:
            result: Target dictionary
            key: Key to add
            value: Value to add
        """
        if self.sparse_mode:
            if isinstance(value, dict):
                filtered = self._filter_empty(value)
                if filtered:
                    result[key] = filtered
            elif isinstance(value, list):
                filtered_list = [
                    self._filter_empty(item) if isinstance(item, dict) else item
                    for item in value
                    if not self._is_empty(item) and (not isinstance(item, dict) or self._filter_empty(item))
                ]
                if filtered_list:
                    result[key] = filtered_list
            elif not self._is_empty(value):
                result[key] = value
        else:
            result[key] = value

    def transform_to_ophthal_full(self, source_data: Dict[str, Any], source_schema: Optional[str] = None) -> Dict[str, Any]:
        """
        Transform any supported schema to OPHTHAL_FULL format.

        Args:
            source_data: Source JSON data
            source_schema: Optional schema type override. Auto-detected if not provided.

        Returns:
            Transformed data in OPHTHAL_FULL nested format
        """
        if source_schema is None:
            source_schema = detect_schema_type(source_data)
            logger.info(f"[SchemaTransformer] Auto-detected schema type: {source_schema}")

        if source_schema == "OPHTHAL_OCR":
            return self._transform_ophthal_ocr(source_data)
        elif source_schema in ["OPHTHAL_FULL", "OPHTHAL_FULL_FLAT"]:
            logger.info("[SchemaTransformer] Source already in OPHTHAL_FULL format")
            return source_data
        else:
            logger.warning(f"[SchemaTransformer] Unknown schema type: {source_schema}, returning as-is")
            return source_data

    def _transform_ophthal_ocr(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform OPHTHAL_OCR schema to OPHTHAL_FULL format.

        OPHTHAL_OCR (OCR extraction format) uses:
        - snake_case field names
        - Separate top-level keys per eye (visual_acuity_od, visual_acuity_os)
        - Flexible additional_tests array
        - form_subtype/referral_type for document classification

        OPHTHAL_FULL uses:
        - camelCase field names
        - Nested rightEye/leftEye structure
        - Dedicated sections for each test type

        In sparse_mode, only fields with actual values are included.
        Empty/N/A fields are omitted so they don't override existing data during merge.
        """
        mode_desc = "SPARSE" if self.sparse_mode else "FULL"
        logger.info(f"[SchemaTransformer] Transforming OPHTHAL_OCR → OPHTHAL_FULL ({mode_desc} mode)")

        result: Dict[str, Any] = {}
        self.unmapped_fields = {}

        # ========== 1. PATIENT DEMOGRAPHICS ==========
        if "patient_info" in data:
            pi = data["patient_info"]
            demographics = {
                "name": pi.get("name"),
                "mrNumber": pi.get("mr_no"),
                "age": str(pi.get("age")) if pi.get("age") is not None else None,
                "gender": pi.get("gender"),
                "consultationDate": pi.get("date"),
                "visitId": pi.get("visit_id"),
                "doctorName": pi.get("doctor_name")
            }
            self._add_if_not_empty(result, "patientDemographics", demographics)
        elif not self.sparse_mode:
            result["patientDemographics"] = self._empty_patient_demographics()

        # ========== 2. EXTENDED HISTORY (NEW SECTION) ==========
        if "history" in data:
            h = data["history"]
            extended_history = {
                "systemicIllness": h.get("systemic_illness"),
                "familyHistory": h.get("family_history"),
                "allergies": h.get("allergies"),
                "pastGlassesPrescription": h.get("pgp")
            }
            self._add_if_not_empty(result, "extendedHistory", extended_history)
            self._add_if_not_empty(result, "pastOcularHistory", h.get("past_ocular_history"))
            self._add_if_not_empty(result, "currentTreatment", h.get("current_treatment"))
        elif not self.sparse_mode:
            result["extendedHistory"] = {
                "systemicIllness": "",
                "familyHistory": "",
                "allergies": "",
                "pastGlassesPrescription": ""
            }
            result["pastOcularHistory"] = "N/A"
            result["currentTreatment"] = "N/A"

        # Complaints
        self._add_if_not_empty(result, "complaints", data.get("complaints"))

        # ========== 3. VISUAL ACUITY AND REFRACTION ==========
        va_right = self._transform_visual_acuity(data.get("visual_acuity_od", {}))
        va_left = self._transform_visual_acuity(data.get("visual_acuity_os", {}))
        va_section = {}
        if va_right:
            va_section["rightEye"] = va_right
        if va_left:
            va_section["leftEye"] = va_left
        self._add_if_not_empty(result, "visualAcuityAndRefraction", va_section)

        # ========== 4. KERATOMETRY ==========
        k_right = self._extract_keratometry(data.get("visual_acuity_od", {}))
        k_left = self._extract_keratometry(data.get("visual_acuity_os", {}))
        k_section = {}
        if k_right:
            k_section["rightEye"] = k_right
        if k_left:
            k_section["leftEye"] = k_left
        self._add_if_not_empty(result, "keratometry", k_section)

        # ========== 5. IOP MEASUREMENTS ==========
        if "iop_measurements" in data:
            iop = data["iop_measurements"]
            # Build measurement object only if there's actual data
            measurement = {}
            if iop.get("method"):
                measurement["method"] = iop["method"]
            if iop.get("time"):
                measurement["time"] = iop["time"]
            od_iop = self._parse_iop_value(iop.get("od_measured"))
            os_iop = self._parse_iop_value(iop.get("os_measured"))
            if od_iop is not None:
                measurement["rightEyeIOP"] = od_iop
            if os_iop is not None:
                measurement["leftEyeIOP"] = os_iop

            iop_section = {}
            if measurement:
                iop_section["measurements"] = [measurement]
            pachymetry_od = self._parse_numeric(iop.get("pachymetry_od"))
            pachymetry_os = self._parse_numeric(iop.get("pachymetry_os"))
            adj_od = self._parse_iop_value(iop.get("od_adjusted"))
            adj_os = self._parse_iop_value(iop.get("os_adjusted"))
            if pachymetry_od is not None:
                iop_section["pachymetryOD"] = pachymetry_od
            if pachymetry_os is not None:
                iop_section["pachymetryOS"] = pachymetry_os
            if adj_od is not None:
                iop_section["pachymetryAdjustedIOPOD"] = adj_od
            if adj_os is not None:
                iop_section["pachymetryAdjustedIOPOS"] = adj_os

            self._add_if_not_empty(result, "intraocularpressure", iop_section)
        elif not self.sparse_mode:
            result["intraocularpressure"] = self._empty_iop()

        # ========== 6. SLIT LAMP EXAMINATION ==========
        sl_right = self._transform_slit_lamp(data.get("slit_lamp_od", {}))
        sl_left = self._transform_slit_lamp(data.get("slit_lamp_os", {}))
        sl_section = {}
        if sl_right:
            sl_section["rightEye"] = sl_right
        if sl_left:
            sl_section["leftEye"] = sl_left
        self._add_if_not_empty(result, "slitLampExamination", sl_section)

        # ========== 7. GONIOSCOPY ==========
        if "gonioscopy" in data:
            gonio = data["gonioscopy"]
            gonio_parts = []
            if gonio.get("od"):
                gonio_parts.append(f"OD (Right Eye): {gonio['od']}")
            if gonio.get("os"):
                gonio_parts.append(f"OS (Left Eye): {gonio['os']}")
            if gonio_parts:
                self._add_if_not_empty(result, "gonioscopy", "; ".join(gonio_parts))
        elif not self.sparse_mode:
            result["gonioscopy"] = "N/A"

        # ========== 8. FUNDUS EXAMINATION ==========
        fundus_right = self._transform_fundus(data.get("fundus_od", {}))
        fundus_left = self._transform_fundus(data.get("fundus_os", {}))
        fundus_section = {}
        if fundus_right:
            fundus_section["rightEye"] = fundus_right
        if fundus_left:
            fundus_section["leftEye"] = fundus_left
        self._add_if_not_empty(result, "fundusExamination", fundus_section)

        # ========== 9. DIAGNOSIS, PLAN, NOTES ==========
        self._add_if_not_empty(result, "diagnosis", data.get("diagnosis"))
        if data.get("procedures_done"):
            self._add_if_not_empty(result, "procedures", [data["procedures_done"]])
        self._add_if_not_empty(result, "doctorRecommendation", data.get("plan"))
        self._add_if_not_empty(result, "doctorNotes", data.get("doctor_notes"))

        # ========== 10. ADDITIONAL TESTS → Route to appropriate sections ==========
        if "additional_tests" in data and data["additional_tests"]:
            self._route_additional_tests(data["additional_tests"], result)

        # Initialize remaining empty sections (only in non-sparse mode)
        if not self.sparse_mode:
            self._initialize_empty_sections(result)

        # ========== 11. DOCUMENT METADATA (NEW SECTION) ==========
        doc_metadata = {
            "formSubtype": data.get("form_subtype"),
            "referralType": data.get("referral_type"),
            "nextReview": data.get("next_review"),
            "sourceSchema": "OPHTHAL_OCR"  # Always include source schema
        }
        # Always include documentMetadata with at least sourceSchema
        filtered_doc_metadata = {k: v for k, v in doc_metadata.items() if not self._is_empty(v)}
        if filtered_doc_metadata:
            result["documentMetadata"] = filtered_doc_metadata

        # ========== 12. QUALITY METADATA (NEW SECTION) ==========
        if "low_confidence_fields" in data and data["low_confidence_fields"]:
            result["qualityMetadata"] = {
                "lowConfidenceFields": data["low_confidence_fields"]
            }
        elif not self.sparse_mode:
            result["qualityMetadata"] = {
                "lowConfidenceFields": []
            }

        # ========== 13. ADDITIONAL DATA (Catch-all for unmapped) ==========
        # additionalData is an array of key-value pairs: [{"key": "...", "value": "..."}, ...]
        if self.unmapped_fields:
            import json
            result["additionalData"] = [
                {
                    "key": k,
                    "value": json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                }
                for k, v in self.unmapped_fields.items()
            ]
        else:
            result["additionalData"] = []

        logger.info(f"[SchemaTransformer] ✅ Transformation complete - {len(result)} top-level sections ({mode_desc} mode)")

        return result

    # ========== HELPER METHODS ==========

    def _transform_visual_acuity(self, va_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform visual acuity data from Reference Guide format."""
        if not va_data:
            return {} if self.sparse_mode else None

        refraction = self._parse_refraction(va_data.get("refraction", ""))

        result = {}

        # Add fields only if they have values (in sparse mode)
        if va_data.get("unaided"):
            result["unaidedVision"] = va_data["unaided"]
        elif not self.sparse_mode:
            result["unaidedVision"] = "N/A"

        if va_data.get("aided"):
            result["aidedVision"] = va_data["aided"]
        elif not self.sparse_mode:
            result["aidedVision"] = "N/A"

        if va_data.get("patient_glasses"):
            result["patientGlasses"] = va_data["patient_glasses"]
        elif not self.sparse_mode:
            result["patientGlasses"] = "N/A"

        if va_data.get("pinhole"):
            result["pinholeVision"] = va_data["pinhole"]
        elif not self.sparse_mode:
            result["pinholeVision"] = "N/A"

        if va_data.get("near_add"):
            result["nearAdd"] = va_data["near_add"]
        elif not self.sparse_mode:
            result["nearAdd"] = "N/A"

        if va_data.get("near_vision"):
            result["nearVision"] = va_data["near_vision"]
        elif not self.sparse_mode:
            result["nearVision"] = "N/A"

        # Refraction values (numeric, so None is empty)
        if refraction.get("sphere") is not None:
            result["refractionSphere"] = refraction["sphere"]
        if refraction.get("cylinder") is not None:
            result["refractionCylinder"] = refraction["cylinder"]
        if refraction.get("axis") is not None:
            result["refractionAxis"] = refraction["axis"]

        return result if result else {}

    def _parse_refraction(self, refraction_str: str) -> Dict[str, Optional[float]]:
        """
        Parse refraction string into components.

        Examples:
        - "-2.00 / -0.75 x 90" → {"sphere": -2.0, "cylinder": -0.75, "axis": 90}
        - "+1.50 DS" → {"sphere": 1.5, "cylinder": None, "axis": None}
        - "Plano" → {"sphere": 0, "cylinder": None, "axis": None}
        """
        result = {"sphere": None, "cylinder": None, "axis": None}

        if not refraction_str or refraction_str.lower() in ["n/a", "nil", "", "plano"]:
            if refraction_str and refraction_str.lower() == "plano":
                result["sphere"] = 0.0
            return result

        # Pattern: Sph -2.00 Cyl -0.75 x 90 OR -2.00 / -0.75 x 90
        # Match sphere
        sphere_match = re.search(r'[Ss]ph?\s*([+-]?\d+\.?\d*)|^([+-]?\d+\.?\d*)', refraction_str)
        if sphere_match:
            val = sphere_match.group(1) or sphere_match.group(2)
            try:
                result["sphere"] = float(val)
            except ValueError:
                pass

        # Match cylinder
        cyl_match = re.search(r'[Cc]yl?\s*([+-]?\d+\.?\d*)|/\s*([+-]?\d+\.?\d*)', refraction_str)
        if cyl_match:
            val = cyl_match.group(1) or cyl_match.group(2)
            try:
                result["cylinder"] = float(val)
            except ValueError:
                pass

        # Match axis
        axis_match = re.search(r'[x×@]\s*(\d+)', refraction_str)
        if axis_match:
            try:
                result["axis"] = int(axis_match.group(1))
            except ValueError:
                pass

        return result

    def _extract_keratometry(self, va_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
        """Extract keratometry from visual acuity data."""
        k_reading = va_data.get("k_reading", "")

        if not k_reading:
            return {} if self.sparse_mode else {
                "horizontal": None,
                "horizontalAxis": None,
                "vertical": None,
                "verticalAxis": None
            }

        result = {}

        # Pattern: "43.50 D @ 180 / 44.50 D @ 90" or "43.50@180, 44.50@90"
        k_matches = re.findall(r'(\d+\.?\d*)\s*[D]?\s*[@]\s*(\d+)', k_reading)

        if len(k_matches) >= 1:
            result["horizontal"] = float(k_matches[0][0])
            result["horizontalAxis"] = int(k_matches[0][1])

        if len(k_matches) >= 2:
            result["vertical"] = float(k_matches[1][0])
            result["verticalAxis"] = int(k_matches[1][1])

        return result

    def _transform_slit_lamp(self, sl_data: Dict[str, Any]) -> Dict[str, str]:
        """Transform slit lamp data from Reference Guide format."""
        if not sl_data:
            return {} if self.sparse_mode else None

        result = {}
        fields = [
            ("lids", "lids"),
            ("conjunctiva", "conjunctiva"),
            ("cornea", "cornea"),
            ("anterior_chamber", "anteriorChamber"),
            ("iris", "iris"),
            ("lens", "lens"),
            ("pupil", "pupil")
        ]

        for src_key, dest_key in fields:
            value = sl_data.get(src_key)
            if value and not self._is_empty(value):
                result[dest_key] = value
            elif not self.sparse_mode:
                result[dest_key] = "N/A"

        return result if result else {}

    def _transform_fundus(self, fundus_data: Dict[str, Any]) -> Dict[str, str]:
        """Transform fundus data from Reference Guide format."""
        if not fundus_data:
            return {} if self.sparse_mode else None

        result = {}

        # Combine disc findings with CDR
        disc = fundus_data.get("disc", "")
        cdr = fundus_data.get("cup_disc_ratio", "")
        if cdr and disc:
            disc_combined = f"{disc} (CDR: {cdr})"
        elif cdr:
            disc_combined = f"CDR: {cdr}"
        elif disc:
            disc_combined = disc
        else:
            disc_combined = None

        if disc_combined:
            result["disc"] = disc_combined
        elif not self.sparse_mode:
            result["disc"] = "N/A"

        # Macula
        macula = fundus_data.get("macula")
        if macula and not self._is_empty(macula):
            result["macula"] = macula
        elif not self.sparse_mode:
            result["macula"] = "N/A"

        # Combine vessels and periphery
        vessels = fundus_data.get("vessels", "")
        periphery = fundus_data.get("periphery", "")
        general_fundus = fundus_data.get("findings", "")

        general_parts = []
        if vessels:
            general_parts.append(f"Vessels: {vessels}")
        if periphery:
            general_parts.append(f"Periphery: {periphery}")
        if general_fundus:
            general_parts.append(general_fundus)

        if general_parts:
            result["generalFundus"] = "; ".join(general_parts)
        elif not self.sparse_mode:
            result["generalFundus"] = "N/A"

        return result if result else {}

    def _route_additional_tests(self, tests: List[Dict[str, Any]], result: Dict[str, Any]):
        """
        Route flexible additional_tests to appropriate structured sections.

        Test routing rules:
        - Schirmer, TBUT, Staining → dryEyeAssessment
        - Worth Four Dot, Stereopsis, Bagolini → binocularVisionTests
        - Cover Test → coverTestWithGlass
        - HVF, Visual Field → visualFieldAnalysis
        - OCT → visualFieldAnalysis.oct
        - PBCT → pbctCharts
        - Amsler, Color Vision → macularFunctionTests
        """
        for test in tests:
            test_name = test.get("test_name", "").lower()
            result_od = test.get("result_od", "")
            result_os = test.get("result_os", "")
            result_combined = test.get("result_combined", "")
            notes = test.get("notes", "")

            routed = False

            # Dry Eye Assessment
            if "schirmer" in test_name:
                if "dryEyeAssessment" not in result:
                    result["dryEyeAssessment"] = self._empty_dry_eye()
                if "ii" in test_name or "2" in test_name:
                    result["dryEyeAssessment"]["schimersTest2OD"] = self._parse_numeric(result_od)
                    result["dryEyeAssessment"]["schimersTest2OS"] = self._parse_numeric(result_os)
                else:
                    result["dryEyeAssessment"]["schimersTest1OD"] = self._parse_numeric(result_od)
                    result["dryEyeAssessment"]["schimersTest1OS"] = self._parse_numeric(result_os)
                routed = True

            elif "tbut" in test_name or "break" in test_name:
                if "dryEyeAssessment" not in result:
                    result["dryEyeAssessment"] = self._empty_dry_eye()
                result["dryEyeAssessment"]["tearFilmBreakupTimeOD"] = self._parse_numeric(result_od)
                result["dryEyeAssessment"]["tearFilmBreakupTimeOS"] = self._parse_numeric(result_os)
                routed = True

            elif "fluorescein" in test_name:
                if "dryEyeAssessment" not in result:
                    result["dryEyeAssessment"] = self._empty_dry_eye()
                result["dryEyeAssessment"]["fluoresceinStainingOD"] = result_od or "N/A"
                result["dryEyeAssessment"]["fluoresceinStainingOS"] = result_os or "N/A"
                routed = True

            elif "lissamine" in test_name:
                if "dryEyeAssessment" not in result:
                    result["dryEyeAssessment"] = self._empty_dry_eye()
                result["dryEyeAssessment"]["lissamineGreenOD"] = result_od or "N/A"
                result["dryEyeAssessment"]["lissamineGreenOS"] = result_os or "N/A"
                routed = True

            # Binocular Vision Tests
            elif "worth" in test_name and "four" in test_name:
                if "binocularVisionTests" not in result:
                    result["binocularVisionTests"] = self._empty_binocular_vision()
                result["binocularVisionTests"]["worthFourDotDist"] = result_combined or "N/A"
                routed = True

            elif "stereopsis" in test_name:
                if "binocularVisionTests" not in result:
                    result["binocularVisionTests"] = self._empty_binocular_vision()
                result["binocularVisionTests"]["stereopsisNear"] = result_combined or "N/A"
                routed = True

            elif "bagolini" in test_name:
                if "binocularVisionTests" not in result:
                    result["binocularVisionTests"] = self._empty_binocular_vision()
                result["binocularVisionTests"]["bagoliniDist"] = result_combined or "N/A"
                routed = True

            # Visual Field
            elif "hvf" in test_name or "visual field" in test_name:
                if "visualFieldAnalysis" not in result:
                    result["visualFieldAnalysis"] = self._empty_visual_field()
                if result_combined or notes:
                    result["visualFieldAnalysis"]["interpretation"] = result_combined or notes
                routed = True

            elif "oct" in test_name:
                if "visualFieldAnalysis" not in result:
                    result["visualFieldAnalysis"] = self._empty_visual_field()
                result["visualFieldAnalysis"]["oct"] = result_combined or f"OD: {result_od}; OS: {result_os}"
                routed = True

            # Macular Function Tests
            elif "amsler" in test_name:
                if "macularFunctionTests" not in result:
                    result["macularFunctionTests"] = self._empty_macular_function()
                result["macularFunctionTests"]["amslersTestOD"] = result_od or "N/A"
                result["macularFunctionTests"]["amslersTestOS"] = result_os or "N/A"
                routed = True

            elif "color" in test_name and "vision" in test_name:
                if "macularFunctionTests" not in result:
                    result["macularFunctionTests"] = self._empty_macular_function()
                result["macularFunctionTests"]["colorVisionOD"] = result_od or "N/A"
                result["macularFunctionTests"]["colorVisionOS"] = result_os or "N/A"
                routed = True

            # Cover Test
            elif "cover" in test_name and "pbct" not in test_name:
                if "coverTestWithGlass" not in result:
                    result["coverTestWithGlass"] = self._empty_cover_test()
                # Try to determine distance vs near
                if "near" in test_name:
                    result["coverTestWithGlass"]["coverTestNear"] = result_combined or f"OD: {result_od}; OS: {result_os}"
                else:
                    result["coverTestWithGlass"]["coverTestDist"] = result_combined or f"OD: {result_od}; OS: {result_os}"
                routed = True

            # PBCT
            elif "pbct" in test_name or "prism bar" in test_name:
                if "pbctCharts" not in result:
                    result["pbctCharts"] = {"pbctOD": [], "pbctOS": []}
                # Can't easily convert string to 2D array, store as unmapped field
                # Will be converted to additionalData array format at the end
                if "pbctNotes" not in self.unmapped_fields:
                    self.unmapped_fields["pbctNotes"] = []
                self.unmapped_fields["pbctNotes"].append({
                    "test": test_name,
                    "od": result_od,
                    "os": result_os,
                    "combined": result_combined,
                    "notes": notes
                })
                routed = True

            # Unmapped test
            if not routed:
                if "unmappedTests" not in self.unmapped_fields:
                    self.unmapped_fields["unmappedTests"] = []
                self.unmapped_fields["unmappedTests"].append(test)

    def _parse_numeric(self, value: Any) -> Optional[float]:
        """Parse a value that may be string or number to float."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Extract numeric part
            match = re.search(r'(\d+\.?\d*)', value)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    return None
        return None

    def _parse_iop_value(self, value: Any) -> Optional[float]:
        """Parse IOP value, stripping 'mmHg' suffix."""
        return self._parse_numeric(value)

    def _initialize_empty_sections(self, result: Dict[str, Any]):
        """Initialize empty sections that weren't populated."""
        if "coverTestWithGlass" not in result:
            result["coverTestWithGlass"] = self._empty_cover_test()

        if "coverTestWithoutGlass" not in result:
            result["coverTestWithoutGlass"] = self._empty_cover_test()

        if "binocularVisionTests" not in result:
            result["binocularVisionTests"] = self._empty_binocular_vision()

        if "macularFunctionTests" not in result:
            result["macularFunctionTests"] = self._empty_macular_function()

        if "pbctCharts" not in result:
            result["pbctCharts"] = {"pbctOD": [], "pbctOS": []}

        if "diplopiaCharting" not in result:
            result["diplopiaCharting"] = "N/A"

        if "dryEyeAssessment" not in result:
            result["dryEyeAssessment"] = self._empty_dry_eye()

        if "diurnalIOPVariation" not in result:
            result["diurnalIOPVariation"] = []

        if "visualFieldAnalysis" not in result:
            result["visualFieldAnalysis"] = self._empty_visual_field()

    # ========== EMPTY SECTION TEMPLATES ==========

    def _empty_patient_demographics(self) -> Dict[str, str]:
        return {
            "name": "",
            "mrNumber": "",
            "age": "",
            "gender": "",
            "consultationDate": "",
            "visitId": "",
            "doctorName": ""
        }

    def _empty_cover_test(self) -> Dict[str, str]:
        return {
            "coverTestDist": "N/A",
            "coverTestNear": "N/A",
            "uncoverTestDist": "N/A",
            "uncoverTestNear": "N/A",
            "alternateCoverTestDist": "N/A",
            "alternateCoverTestNear": "N/A"
        }

    def _empty_binocular_vision(self) -> Dict[str, str]:
        return {
            "fixationDist": "N/A",
            "fixationNear": "N/A",
            "stereopsisDist": "N/A",
            "stereopsisNear": "N/A",
            "avPatternDist": "N/A",
            "avPatternNear": "N/A",
            "worthFourDotDist": "N/A",
            "worthFourDotNear": "N/A",
            "bagoliniDist": "N/A",
            "bagoliniNear": "N/A",
            "faceExternalExamDist": "N/A",
            "faceExternalExamNear": "N/A"
        }

    def _empty_macular_function(self) -> Dict[str, str]:
        return {
            "colorVisionOD": "N/A",
            "colorVisionOS": "N/A",
            "amslersTestOD": "N/A",
            "amslersTestOS": "N/A"
        }

    def _empty_dry_eye(self) -> Dict[str, Any]:
        return {
            "osdiQuestionnaire": "N/A",
            "schimersTest1OD": None,
            "schimersTest1OS": None,
            "schimersTest2OD": None,
            "schimersTest2OS": None,
            "tearFilmBreakupTimeOD": None,
            "tearFilmBreakupTimeOS": None,
            "fluoresceinStainingOD": "N/A",
            "fluoresceinStainingOS": "N/A",
            "lissamineGreenOD": "N/A",
            "lissamineGreenOS": "N/A"
        }

    def _empty_visual_field(self) -> Dict[str, str]:
        return {
            "strategy": "N/A",
            "interpretation": "N/A",
            "meanDeviation": "N/A",
            "patternDeviation": "N/A",
            "ght": "N/A",
            "vfi": "N/A",
            "oct": "N/A",
            "targetIOP": "N/A"
        }

    def _empty_iop(self) -> Dict[str, Any]:
        return {
            "measurements": [],
            "pachymetryOD": None,
            "pachymetryOS": None,
            "pachymetryAdjustedIOPOD": None,
            "pachymetryAdjustedIOPOS": None
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def transform_for_merge(
    source_data: Dict[str, Any],
    target_schema: str = "OPHTHAL_FULL",
    sparse_mode: bool = True
) -> Dict[str, Any]:
    """
    Convenience function to transform source data for merge operations.

    This function is designed for APPEND-ONLY merge operations where uploaded
    JSON should only contribute fields that have actual values. Empty fields
    are omitted so they don't override existing data from other extractions.

    The AI merge will perform contextual deep merge:
    - Latest values win for current-state fields (vitals, diagnosis)
    - History fields are deep merged chronologically
    - Arrays (medications, investigations) are appended
    - Source is treated as ONE of the merge inputs, not prioritized

    Args:
        source_data: Source JSON data in any supported format
        target_schema: Target schema format (default: OPHTHAL_FULL)
        sparse_mode: If True (default for merge), only include fields with
                    actual values. Empty/N/A fields are omitted so they
                    don't override existing data during merge.

    Returns:
        Transformed data ready for merge (sparse by default)
    """
    transformer = SchemaTransformer(sparse_mode=sparse_mode)

    if target_schema == "OPHTHAL_FULL":
        return transformer.transform_to_ophthal_full(source_data)
    else:
        logger.warning(f"[transform_for_merge] Unsupported target schema: {target_schema}")
        return source_data


def transform_full(source_data: Dict[str, Any], target_schema: str = "OPHTHAL_FULL") -> Dict[str, Any]:
    """
    Transform source data with ALL fields (including empty defaults).

    Use this when you need a complete schema with all fields populated,
    such as for standalone extraction display or validation.

    Args:
        source_data: Source JSON data in any supported format
        target_schema: Target schema format (default: OPHTHAL_FULL)

    Returns:
        Transformed data with all fields (empty fields get default "N/A")
    """
    transformer = SchemaTransformer(sparse_mode=False)

    if target_schema == "OPHTHAL_FULL":
        return transformer.transform_to_ophthal_full(source_data)
    else:
        logger.warning(f"[transform_full] Unsupported target schema: {target_schema}")
        return source_data

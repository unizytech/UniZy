"""
Test enhanced red flag detection with lab values and investigations.
"""

import pytest
from services.triage.triage_engine import TriageSuggestionEngine
from services.triage.structured_insights import StructuredInsights


class TestRedFlagDetection:
    """Test _check_red_flags with various clinical scenarios."""

    def setup_method(self):
        """Initialize engine for each test."""
        self.engine = TriageSuggestionEngine()

    def test_vital_sign_red_flags(self):
        """Test detection of vital sign abnormalities."""
        insights = StructuredInsights(
            chief_complaints=["fever", "weakness"],
            vital_signs={
                "systolic_bp": "85",
                "spo2": "88%",
                "heart_rate": "130/min",
                "temperature": "40°C"
            },
            specialty="medicine"
        )

        red_flags = self.engine._check_red_flags(insights, [])

        assert "Hypotension (SBP <90 mmHg)" in red_flags
        assert "Severe Hypoxia (SpO2 <90%)" in red_flags
        assert "Tachycardia (HR >120/min)" in red_flags
        assert "High Fever (>39°C / >102°F)" in red_flags

    def test_lab_value_red_flags_thrombocytopenia(self):
        """Test detection of severe thrombocytopenia from lab results."""
        insights = StructuredInsights(
            chief_complaints=["fever"],
            investigations_results=[
                {"test": "CBC", "result": "Platelet count: 15000/cumm"},
                {"test": "Hemoglobin", "result": "Hb: 6.5 g/dL"}
            ],
            specialty="medicine"
        )

        red_flags = self.engine._check_red_flags(insights, [])

        assert "Severe Thrombocytopenia (Platelets <20,000)" in red_flags
        assert "Severe Anemia (Hb <7 g/dL)" in red_flags

    def test_lab_value_red_flags_renal(self):
        """Test detection of acute kidney injury from lab results."""
        insights = StructuredInsights(
            chief_complaints=["swelling", "reduced urine"],
            investigations_results=[
                {"test": "RFT", "result": "Creatinine: 4.5 mg/dL, Urea: 120 mg/dL"}
            ],
            specialty="medicine"
        )

        red_flags = self.engine._check_red_flags(insights, [])

        assert "Acute Kidney Injury (Creatinine >3 mg/dL)" in red_flags

    def test_lab_value_red_flags_hyperglycemia(self):
        """Test detection of severe hyperglycemia (DKA)."""
        insights = StructuredInsights(
            chief_complaints=["vomiting", "abdominal pain"],
            investigations_results=[
                {"test": "RBS", "result": "Random Blood Sugar: 450 mg/dL"}
            ],
            specialty="medicine"
        )

        red_flags = self.engine._check_red_flags(insights, [])

        assert "Severe Hyperglycemia (>400 mg/dL)" in red_flags

    def test_lab_value_red_flags_hepatitis(self):
        """Test detection of severe hepatitis from transaminases."""
        insights = StructuredInsights(
            chief_complaints=["jaundice"],
            investigations_results=[
                {"test": "LFT", "result": "SGPT (ALT): 1500 U/L, SGOT (AST): 1200 U/L"}
            ],
            specialty="medicine"
        )

        red_flags = self.engine._check_red_flags(insights, [])

        assert "Severe Hepatitis (Transaminases >1000)" in red_flags

    def test_imaging_red_flags(self):
        """Test detection of imaging red flags."""
        insights = StructuredInsights(
            chief_complaints=["chest pain", "breathlessness"],
            investigations_results=[
                {"test": "CT Chest", "result": "Findings suggestive of pulmonary embolism"}
            ],
            specialty="medicine"
        )

        red_flags = self.engine._check_red_flags(insights, [])

        assert "Pulmonary Embolism" in red_flags

    def test_keyword_red_flags(self):
        """Test detection of keyword-based red flags."""
        insights = StructuredInsights(
            chief_complaints=["fever", "headache"],
            examination_findings={
                "general": "Confused, disoriented",
                "neck": "Neck stiffness present"
            },
            specialty="medicine"
        )

        red_flags = self.engine._check_red_flags(insights, [])

        assert "Altered Sensorium" in red_flags
        assert "Meningism" in red_flags

    def test_cauda_equina_red_flags(self):
        """Test detection of cauda equina syndrome (orthopedic emergency)."""
        insights = StructuredInsights(
            chief_complaints=["back pain", "leg weakness"],
            history_of_present_illness={
                "presenting_complaints": "Severe back pain with bilateral leg weakness and saddle anesthesia"
            },
            examination_findings={
                "neuro": "Decreased perianal sensation, urinary retention"
            },
            specialty="orthopedics"
        )

        red_flags = self.engine._check_red_flags(insights, [])

        assert "Cauda Equina" in red_flags

    def test_missing_segments_no_crash(self):
        """Test that missing segments don't cause crashes."""
        # Minimal insights with only specialty
        insights = StructuredInsights(
            specialty="medicine"
        )

        # Should not raise any exceptions
        red_flags = self.engine._check_red_flags(insights, [])

        # Should return empty or minimal list
        assert isinstance(red_flags, list)

    def test_extract_numeric_helper(self):
        """Test the _extract_numeric helper method."""
        assert self.engine._extract_numeric("120 mmHg") == 120.0
        assert self.engine._extract_numeric("98%") == 98.0
        assert self.engine._extract_numeric("37.5°C") == 37.5
        assert self.engine._extract_numeric(100) == 100.0
        assert self.engine._extract_numeric("N/A") is None
        assert self.engine._extract_numeric(None) is None

    def test_extract_lab_value_helper(self):
        """Test the _extract_lab_value helper method."""
        text = "cbc shows platelet count: 45000/cumm, hemoglobin: 8.5 g/dl"

        platelet_val = self.engine._extract_lab_value(text, ["platelet", "plt"])
        assert platelet_val == 45000.0

        hb_val = self.engine._extract_lab_value(text, ["hemoglobin", "hb"])
        assert hb_val == 8.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

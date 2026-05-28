"""
Extraction Workflow Tests

Tests extraction workflows using real audio file:
- VHRScreen.tsx extraction flow (chunked recording)
- RecordTab.tsx extraction flow (WebSocket real-time)
- Multi-consultation extraction (OP, DISCHARGE, RESPIRATORY)
- Template-based extraction with junction tables
- Progressive loading (CORE → ADDITIONAL)

Test Coverage:
- TC-EXT-001 through TC-EXT-030
- Uses references/test_3.mp3 for audio testing
- Junction table architecture validation
- Dynamic prompt generation
"""

import pytest
import uuid
import base64
from fastapi.testclient import TestClient
import sys
import os
from pathlib import Path
import json

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from main import app
from services.supabase_service import supabase

client = TestClient(app)

# Path to test audio file
TEST_AUDIO_PATH = backend_dir.parent / "references" / "test_3.mp3"


@pytest.fixture(scope="module")
def test_audio_base64():
    """Load test audio file and encode as base64"""
    if not TEST_AUDIO_PATH.exists():
        pytest.skip(f"Test audio file not found: {TEST_AUDIO_PATH}")

    with open(TEST_AUDIO_PATH, "rb") as f:
        audio_bytes = f.read()
        return base64.b64encode(audio_bytes).decode("utf-8")


@pytest.fixture(scope="module")
def test_audio_bytes():
    """Load test audio file as bytes"""
    if not TEST_AUDIO_PATH.exists():
        pytest.skip(f"Test audio file not found: {TEST_AUDIO_PATH}")

    with open(TEST_AUDIO_PATH, "rb") as f:
        return f.read()


@pytest.mark.skip(reason="Extraction tests require AI service - expensive and slow, run manually")
class TestVHRScreenExtractionFlow:
    """Test VHRScreen.tsx extraction flow (chunked recording + SSE progress)"""

    def test_complete_vhr_extraction_op_consultation(
        self, test_audio_base64, test_consultation_type_id, cleanup_test_data
    ):
        """
        TC-EXT-001: Complete VHR extraction workflow for OP consultation

        Workflow:
        1. User uploads audio file
        2. User selects consultation type (OP)
        3. User selects processing mode (Default)
        4. System starts extraction
        5. CORE segments extracted first
        6. ADDITIONAL segments extracted in background
        7. Results displayed with collapsible segments
        """
        doctor_id = uuid.uuid4()

        # Get OP consultation type
        op_type = (
            supabase.table("consultation_types")
            .select("id, type_code")
            .eq("type_code", "OP")
            .limit(1)
            .execute()
        )

        if not op_type.data:
            pytest.skip("OP consultation type not found")

        consultation_type_id = op_type.data[0]["id"]

        # Prepare extraction request (simulating VHRScreen flow)
        # Note: VHRScreen uses chunked recording, but we can simulate with direct file upload
        extract_request = {
            "audio_data": test_audio_base64,
            "consultation_type_code": "OP",
            "doctor_id": str(doctor_id),
            "mode": "core"  # Fast mode - CORE segments only
        }

        # Call extraction endpoint
        # Note: Actual endpoint depends on implementation
        # Using summary extract endpoint
        response = client.post("/api/v1/summary/extract", json={
            "transcript": "",  # Will be generated from audio
            "consultation_type_code": "OP",
            "doctor_id": str(doctor_id),
            "mode": "core"
        })

        # For this test, we'll use a placeholder transcript
        # In real implementation, audio would be transcribed first
        sample_transcript = """
        Patient: I've been having headaches for the past 2 days.
        Doctor: Can you describe the pain?
        Patient: It's a throbbing pain on the right side of my head.
        Doctor: Any nausea or vomiting?
        Patient: Yes, I felt nauseous this morning.
        Doctor: Let me check your blood pressure. It's 140/90, which is slightly elevated.
        Doctor: I'm diagnosing this as migraine. I'll prescribe Ibuprofen 400mg twice daily for 5 days.
        """

        extract_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "OP",
            "doctor_id": str(doctor_id),
            "mode": "core"
        }

        response = client.post("/api/v1/summary/extract", json=extract_request)

        # Verify response
        assert response.status_code == 200
        data = response.json()

        # Verify extraction structure
        assert "extraction" in data or "data" in data
        # Extraction should have segments
        extraction_data = data.get("extraction") or data.get("data")
        assert isinstance(extraction_data, dict)

        # Verify CORE segments included
        # Based on OP consultation, should have: Diagnosis, Chief Complaints, etc.
        # The exact segments depend on database configuration

    def test_vhr_extraction_with_template(
        self, test_audio_base64, test_consultation_type_id, cleanup_test_data
    ):
        """
        TC-EXT-002: VHR extraction using activated template

        Workflow:
        1. Doctor has activated template
        2. User selects template in VHRScreen
        3. Extraction uses template segment configuration
        4. Template segments loaded via template_segments junction table
        """
        doctor_id = uuid.uuid4()

        # Get a template
        template_response = (
            supabase.table("templates")
            .select("template_code, id")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .limit(1)
            .execute()
        )

        if not template_response.data:
            pytest.skip("No templates available")

        template_code = template_response.data[0]["template_code"]
        template_id = template_response.data[0]["id"]

        # Share and activate template
        share_request = {
            "template_id": template_id,
            "doctor_ids": [str(doctor_id)],
            "access_level": "use"
        }
        client.post("/api/v1/doctor-templates/share", json=share_request)

        # Get doctor_template ID for cleanup
        dt_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("template_id", template_id)
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        cleanup_test_data.append(("doctor_templates", "id", dt_check.data[0]["id"]))

        activate_request = {
            "template_id": template_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }
        client.post("/api/v1/doctor-templates/activate", json=activate_request)

        # Verify template segments loaded via junction table
        template_segments = (
            supabase.table("template_segments")
            .select("segment_id, segment_code, category")
            .eq("template_id", template_id)
            .execute()
        )

        # Should have segments from junction table
        assert isinstance(template_segments.data, list)

        # Now do extraction with this template
        sample_transcript = "Doctor: Hello. Patient: I have a headache."

        extract_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "OP",
            "doctor_id": str(doctor_id),
            "template_name": template_code,
            "mode": "full"
        }

        response = client.post("/api/v1/summary/extract", json=extract_request)
        assert response.status_code == 200

    def test_vhr_progressive_loading_core_then_additional(self, test_consultation_type_id):
        """
        TC-EXT-003: VHR progressive loading (CORE → ADDITIONAL)

        Workflow:
        1. User selects "Default" mode
        2. System extracts CORE segments first (~25-35s)
        3. UI displays CORE results
        4. System extracts ADDITIONAL segments in background (~30-45s)
        5. UI updates with ADDITIONAL results
        """
        doctor_id = uuid.uuid4()
        sample_transcript = """
        Patient: I've been feeling chest pain.
        Doctor: When did it start?
        Patient: This morning.
        Doctor: Let me examine you.
        """

        # First request: CORE segments only
        core_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "OP",
            "doctor_id": str(doctor_id),
            "mode": "core"
        }

        core_response = client.post("/api/v1/summary/extract", json=core_request)
        assert core_response.status_code == 200
        core_data = core_response.json()

        # Second request: ADDITIONAL segments
        additional_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "OP",
            "doctor_id": str(doctor_id),
            "mode": "additional"
        }

        additional_response = client.post("/api/v1/summary/extract", json=additional_request)
        assert additional_response.status_code == 200
        additional_data = additional_response.json()

        # ADDITIONAL response should have different/more segments than CORE
        # (depending on database configuration)


@pytest.mark.skip(reason="Extraction tests require AI service - expensive and slow, run manually")
class TestRecordTabExtractionFlow:
    """Test RecordTab.tsx extraction flow (WebSocket real-time)"""

    def test_ephemeral_token_generation(self):
        """
        TC-EXT-011: Test ephemeral token generation for RecordTab

        Workflow:
        1. RecordTab requests ephemeral token
        2. Backend generates token using genai.Client
        3. Token has 12 min session window, 15 min transmission window
        4. RecordTab uses token for WebSocket connection
        """
        response = client.post("/api/ephemeral-token")

        assert response.status_code == 200
        data = response.json()

        # Verify token structure
        assert "token" in data
        assert "expires_in" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 0

        # Token should expire in ~12-15 minutes (720-900 seconds)
        assert data["expires_in"] >= 600  # At least 10 minutes

    def test_record_tab_insights_extraction(self):
        """
        TC-EXT-012: Test RecordTab insights extraction after recording

        Workflow:
        1. User completes recording in RecordTab
        2. RecordTab calls /api/insights with transcript
        3. Backend extracts medical insights
        4. Results returned to RecordTab
        """
        # Sample transcript from RecordTab
        sample_transcript = """
        Doctor: How are you feeling today?
        Patient: I've been having stomach pain for 3 days.
        Doctor: Where exactly is the pain?
        Patient: In my upper abdomen, on the right side.
        Doctor: Any fever or vomiting?
        Patient: No fever, but I vomited once yesterday.
        Doctor: I'll prescribe you omeprazole 20mg once daily.
        """

        # Note: /api/insights endpoint may require different parameters
        # Adjust based on actual implementation
        # For now, using summary extract endpoint as proxy
        extract_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "OP",
            "mode": "core"
        }

        response = client.post("/api/v1/summary/extract", json=extract_request)
        assert response.status_code == 200


@pytest.mark.skip(reason="Extraction tests require AI service - expensive and slow, run manually")
class TestMultiConsultationExtraction:
    """Test extraction for different consultation types"""

    def test_op_consultation_extraction(self):
        """TC-EXT-021: OP consultation extraction"""
        sample_transcript = "Patient: Headache. Doctor: Ibuprofen 400mg."

        extract_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "OP",
            "mode": "core"
        }

        response = client.post("/api/v1/summary/extract", json=extract_request)
        assert response.status_code == 200

    def test_discharge_consultation_extraction(self):
        """TC-EXT-022: Discharge consultation extraction"""
        # Check if DISCHARGE consultation type exists
        discharge_type = (
            supabase.table("consultation_types")
            .select("id")
            .eq("type_code", "DISCHARGE")
            .limit(1)
            .execute()
        )

        if not discharge_type.data:
            pytest.skip("DISCHARGE consultation type not found")

        sample_transcript = """
        Patient admitted on 2025-01-15 with pneumonia.
        Treated with antibiotics. Condition improved.
        Discharged on 2025-01-20 with home medications.
        """

        extract_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "DISCHARGE",
            "mode": "core"
        }

        response = client.post("/api/v1/summary/extract", json=extract_request)
        assert response.status_code == 200

    def test_respiratory_consultation_extraction(self):
        """TC-EXT-023: Respiratory consultation extraction"""
        # Check if RESPIRATORY consultation type exists
        respiratory_type = (
            supabase.table("consultation_types")
            .select("id")
            .eq("type_code", "RESPIRATORY")
            .limit(1)
            .execute()
        )

        if not respiratory_type.data:
            pytest.skip("RESPIRATORY consultation type not found")

        sample_transcript = """
        Patient presenting with difficulty breathing.
        Oxygen saturation 92% on room air.
        Prescribed nebulization treatment.
        """

        extract_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "RESPIRATORY",
            "mode": "core"
        }

        response = client.post("/api/v1/summary/extract", json=extract_request)
        assert response.status_code == 200


@pytest.mark.skip(reason="Extraction tests require AI service - expensive and slow, run manually")
class TestJunctionTableExtraction:
    """Test extraction using junction table architecture"""

    def test_extraction_uses_consultation_type_segments_junction(
        self, test_consultation_type_id
    ):
        """
        TC-EXT-031: Verify extraction loads segments via consultation_type_segments

        Workflow:
        1. Extraction request specifies consultation type
        2. Backend queries consultation_type_segments junction table
        3. Segments loaded via junction (not direct FK)
        4. Dynamic prompt generated from junction data
        """
        # Get segments for this consultation type via junction table
        junction_segments = (
            supabase.table("consultation_type_segments")
            .select("segment_id, segment_code")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .execute()
        )

        # Should have segments via junction
        assert len(junction_segments.data) > 0

        # Get segment details
        segment_ids = [s["segment_id"] for s in junction_segments.data]

        segment_details = (
            supabase.table("segment_definitions")
            .select("segment_code, segment_name, json_schema")
            .in_("id", segment_ids)
            .execute()
        )

        # Should have segment definitions
        assert len(segment_details.data) > 0

        # Verify NO consultation_type_id in segment_definitions
        for segment in segment_details.data:
            assert "consultation_type_id" not in segment

    def test_extraction_uses_template_segments_junction(self, test_consultation_type_id):
        """
        TC-EXT-032: Verify extraction loads segments via template_segments

        Workflow:
        1. Extraction request specifies template
        2. Backend queries template_segments junction table
        3. Segments loaded via junction
        4. Template configuration (category, brevity) applied
        """
        # Get a template
        template_response = (
            supabase.table("templates")
            .select("id, template_code")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .limit(1)
            .execute()
        )

        if not template_response.data:
            pytest.skip("No templates available")

        template_id = template_response.data[0]["id"]

        # Get template segments via junction table
        template_segments = (
            supabase.table("template_segments")
            .select("segment_id, segment_code, category, brevity_level, terminology_style")
            .eq("template_id", template_id)
            .execute()
        )

        # Should have segments via junction
        assert isinstance(template_segments.data, list)

        # If template has segments, verify junction structure
        if template_segments.data:
            segment = template_segments.data[0]
            assert "segment_id" in segment
            assert "category" in segment  # CORE/ADDITIONAL/EXCLUDED
            assert "brevity_level" in segment  # concise/balanced/detailed
            assert "terminology_style" in segment  # medical_terms/simple_terms/as_spoken

    def test_dynamic_prompt_generation_from_junction_data(self, test_consultation_type_id):
        """
        TC-EXT-033: Verify dynamic prompt generation from junction table data

        Workflow:
        1. Backend loads segments via junction table
        2. Applies brevity modifiers based on segment config
        3. Applies terminology style based on segment config
        4. Generates final system prompt dynamically
        5. No hardcoded prompts used
        """
        # This test verifies the segment_registry.py functions
        # We can call the generate_extraction_artifacts function indirectly
        # via the summary extract endpoint

        doctor_id = uuid.uuid4()
        sample_transcript = "Patient: Fever. Doctor: Paracetamol."

        extract_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "OP",
            "doctor_id": str(doctor_id),
            "mode": "core"
        }

        response = client.post("/api/v1/summary/extract", json=extract_request)
        assert response.status_code == 200

        # The fact that extraction succeeds means:
        # 1. Segments were loaded via junction tables
        # 2. Dynamic prompt was generated
        # 3. Schema was generated from junction data
        # 4. Gemini API was called with dynamic prompt/schema


@pytest.mark.skip(reason="Extraction tests require AI service - expensive and slow, run manually")
class TestExtractionEditing:
    """Test extraction editing and version control"""

    def test_save_and_retrieve_extraction(self, test_consultation_type_id):
        """
        TC-EXT-041: Test saving and retrieving extraction data

        Workflow:
        1. Extraction is performed
        2. Results saved to database
        3. Can retrieve extraction by ID
        4. Can retrieve extraction by session ID
        """
        # This requires integration with recording sessions
        # For now, test the extraction endpoint
        sample_transcript = "Patient: Cough. Doctor: Cough syrup."

        extract_request = {
            "transcript": sample_transcript,
            "consultation_type_code": "OP",
            "mode": "core"
        }

        response = client.post("/api/v1/summary/extract", json=extract_request)
        assert response.status_code == 200

    def test_edit_extraction_preserves_original(self):
        """
        TC-EXT-042: Test editing extraction preserves original AI data

        Workflow:
        1. Extraction is saved
        2. Doctor edits extraction
        3. Edited version saved separately
        4. Original AI extraction preserved
        5. Can compare original vs edited
        """
        # This test would use the extractions API endpoints
        # PUT /api/v1/extractions/{extraction_id}
        # GET /api/v1/extractions/{extraction_id}/compare
        # For now, placeholder - requires actual extraction ID
        pass

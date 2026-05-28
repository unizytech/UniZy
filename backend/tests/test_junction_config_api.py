"""
Tests for Junction Table Configuration API Endpoints

Tests the association-specific configuration management for:
- Consultation Type <-> Segment associations (consultation_type_segments)
- Template <-> Segment associations (template_segments)
"""

import pytest
from services.supabase_service import supabase
import uuid

# Note: Uses 'client' fixture from conftest.py which sets TESTING=true for auth bypass


@pytest.fixture(scope="module")
def test_data():
    """Create test data for junction configuration tests"""

    # Create test consultation type
    consultation_type_data = {
        "type_code": "TEST_JUNCTION",
        "type_name": "Test Junction Config",
        "description": "Test consultation type for junction config tests",
        "is_active": True,
        "display_order": 999
    }
    ct_response = supabase.table("consultation_types").insert(consultation_type_data).execute()
    consultation_type_id = ct_response.data[0]["id"]

    # Create test segment
    segment_data = {
        "segment_code": f"TEST_JUNCTION_SEG_{uuid.uuid4().hex[:8].upper()}",
        "segment_name": "Test Junction Segment",
        "prompt_section_text": "Test prompt",
        "schema_definition_json": {"type": "object"},
        "default_category": "core",
        "display_order": 100,
        "default_brevity_level": "balanced",
        "default_terminology_style": "medical_terms",
        "is_active": True
    }
    seg_response = supabase.table("segment_definitions").insert(segment_data).execute()
    segment_id = seg_response.data[0]["id"]
    segment_code = seg_response.data[0]["segment_code"]

    # Create consultation_type_segments junction entry
    junction_data = {
        "consultation_type_id": consultation_type_id,
        "segment_id": segment_id,
        "segment_code": segment_code,
        "default_category": "core",
        "default_display_order": 100,
        "default_brevity_level": "balanced",
        "default_terminology_style": "medical_terms"
    }
    supabase.table("consultation_type_segments").insert(junction_data).execute()

    # Create test template
    template_data = {
        "template_code": f"TEST_JUNCTION_TPL_{uuid.uuid4().hex[:8].upper()}",
        "template_name": "Test Junction Template",
        "consultation_type_id": consultation_type_id,
        "is_active": True
    }
    tpl_response = supabase.table("templates").insert(template_data).execute()
    template_id = tpl_response.data[0]["id"]

    # Create template_segments junction entry
    template_junction_data = {
        "template_id": template_id,
        "segment_id": segment_id,
        "segment_code": segment_code,
        "category": "additional",
        "display_order": 200,
        "brevity_level": "concise",
        "terminology_style": "simple_terms"
    }
    supabase.table("template_segments").insert(template_junction_data).execute()

    yield {
        "consultation_type_id": consultation_type_id,
        "template_id": template_id,
        "segment_code": segment_code,
        "segment_id": segment_id
    }

    # Cleanup
    supabase.table("template_segments").delete().eq("template_id", template_id).execute()
    supabase.table("consultation_type_segments").delete().eq("consultation_type_id", consultation_type_id).execute()
    supabase.table("templates").delete().eq("id", template_id).execute()
    supabase.table("segment_definitions").delete().eq("id", segment_id).execute()
    supabase.table("consultation_types").delete().eq("id", consultation_type_id).execute()


class TestConsultationTypeSegmentConfig:
    """Test consultation_type_segments junction configuration endpoints"""

    def test_get_consultation_type_segment_config(self, client, test_data):
        """Test GET /api/v1/summary/admin/consultation-type-segments/{ct_id}/{segment_code}"""
        response = client.get(
            f"/api/v1/summary/admin/consultation-type-segments/{test_data['consultation_type_id']}/{test_data['segment_code']}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["category"] == "core"
        assert data["display_order"] == 100
        assert data["brevity_level"] == "balanced"
        assert data["terminology_style"] == "medical_terms"

    def test_get_consultation_type_segment_config_not_found(self, client):
        """Test GET with non-existent association"""
        fake_ct_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/summary/admin/consultation-type-segments/{fake_ct_id}/NONEXISTENT_SEG"
        )

        assert response.status_code == 404
        assert "No association found" in response.json()["detail"]

    def test_update_consultation_type_segment_config(self, client, test_data):
        """Test PUT /api/v1/summary/admin/consultation-type-segments/{ct_id}/{segment_code}"""
        update_data = {
            "category": "additional",
            "display_order": 150,
            "brevity_level": "detailed",
            "terminology_style": "as_spoken"
        }

        response = client.put(
            f"/api/v1/summary/admin/consultation-type-segments/{test_data['consultation_type_id']}/{test_data['segment_code']}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Configuration updated successfully"
        assert data["updated"]["category"] == "additional"
        assert data["updated"]["display_order"] == 150

        # Verify the update in database
        verify_response = client.get(
            f"/api/v1/summary/admin/consultation-type-segments/{test_data['consultation_type_id']}/{test_data['segment_code']}"
        )
        verify_data = verify_response.json()
        assert verify_data["category"] == "additional"
        assert verify_data["display_order"] == 150
        assert verify_data["brevity_level"] == "detailed"
        assert verify_data["terminology_style"] == "as_spoken"

    def test_update_consultation_type_segment_config_partial(self, client, test_data):
        """Test partial update (only some fields)"""
        update_data = {
            "brevity_level": "concise"
        }

        response = client.put(
            f"/api/v1/summary/admin/consultation-type-segments/{test_data['consultation_type_id']}/{test_data['segment_code']}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "brevity_level" in data["updated"]
        assert len(data["updated"]) == 1  # Only one field updated

    def test_update_consultation_type_segment_config_empty(self, client, test_data):
        """Test update with no fields"""
        response = client.put(
            f"/api/v1/summary/admin/consultation-type-segments/{test_data['consultation_type_id']}/{test_data['segment_code']}",
            json={}
        )

        assert response.status_code == 400
        assert "No fields to update" in response.json()["detail"]

    def test_update_consultation_type_segment_config_not_found(self, client):
        """Test update with non-existent association"""
        fake_ct_id = str(uuid.uuid4())
        update_data = {"category": "core"}

        response = client.put(
            f"/api/v1/summary/admin/consultation-type-segments/{fake_ct_id}/NONEXISTENT_SEG",
            json=update_data
        )

        assert response.status_code == 404
        assert "No association found" in response.json()["detail"]


class TestTemplateSegmentConfig:
    """Test template_segments junction configuration endpoints"""

    def test_get_template_segment_config(self, client, test_data):
        """Test GET /api/v1/summary/admin/template-segments/{tpl_id}/{segment_code}"""
        response = client.get(
            f"/api/v1/summary/admin/template-segments/{test_data['template_id']}/{test_data['segment_code']}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["category"] == "additional"
        assert data["display_order"] == 200
        assert data["brevity_level"] == "concise"
        assert data["terminology_style"] == "simple_terms"

    def test_get_template_segment_config_not_found(self, client):
        """Test GET with non-existent association"""
        fake_template_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/summary/admin/template-segments/{fake_template_id}/NONEXISTENT_SEG"
        )

        assert response.status_code == 404
        assert "No association found" in response.json()["detail"]

    def test_update_template_segment_config(self, client, test_data):
        """Test PUT /api/v1/summary/admin/template-segments/{tpl_id}/{segment_code}"""
        update_data = {
            "category": "core",
            "display_order": 50,
            "brevity_level": "balanced",
            "terminology_style": "medical_terms"
        }

        response = client.put(
            f"/api/v1/summary/admin/template-segments/{test_data['template_id']}/{test_data['segment_code']}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Configuration updated successfully"
        assert data["updated"]["category"] == "core"
        assert data["updated"]["display_order"] == 50

        # Verify the update in database
        verify_response = client.get(
            f"/api/v1/summary/admin/template-segments/{test_data['template_id']}/{test_data['segment_code']}"
        )
        verify_data = verify_response.json()
        assert verify_data["category"] == "core"
        assert verify_data["display_order"] == 50
        assert verify_data["brevity_level"] == "balanced"
        assert verify_data["terminology_style"] == "medical_terms"

    def test_update_template_segment_config_partial(self, client, test_data):
        """Test partial update (only display order)"""
        update_data = {
            "display_order": 999
        }

        response = client.put(
            f"/api/v1/summary/admin/template-segments/{test_data['template_id']}/{test_data['segment_code']}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated"]["display_order"] == 999
        assert len(data["updated"]) == 1

    def test_update_template_segment_config_empty(self, client, test_data):
        """Test update with no fields"""
        response = client.put(
            f"/api/v1/summary/admin/template-segments/{test_data['template_id']}/{test_data['segment_code']}",
            json={}
        )

        assert response.status_code == 400
        assert "No fields to update" in response.json()["detail"]

    def test_update_template_segment_config_not_found(self, client):
        """Test update with non-existent association"""
        fake_template_id = str(uuid.uuid4())
        update_data = {"category": "core"}

        response = client.put(
            f"/api/v1/summary/admin/template-segments/{fake_template_id}/NONEXISTENT_SEG",
            json=update_data
        )

        assert response.status_code == 404
        assert "No association found" in response.json()["detail"]


class TestConfigurationIsolation:
    """Test that configuration changes are isolated to specific associations"""

    def test_consultation_type_config_does_not_affect_template(self, client, test_data):
        """Verify updating consultation type config doesn't affect template config"""
        # Update consultation type config
        ct_update = {"category": "core", "brevity_level": "detailed"}
        client.put(
            f"/api/v1/summary/admin/consultation-type-segments/{test_data['consultation_type_id']}/{test_data['segment_code']}",
            json=ct_update
        )

        # Check template config is unchanged
        template_response = client.get(
            f"/api/v1/summary/admin/template-segments/{test_data['template_id']}/{test_data['segment_code']}"
        )
        template_data = template_response.json()

        # Template config should still have its original values
        assert template_data["category"] == "core"  # From previous test
        assert template_data["brevity_level"] == "balanced"  # From previous test

    def test_template_config_does_not_affect_consultation_type(self, client, test_data):
        """Verify updating template config doesn't affect consultation type config"""
        # Update template config
        tpl_update = {"category": "additional", "terminology_style": "as_spoken"}
        client.put(
            f"/api/v1/summary/admin/template-segments/{test_data['template_id']}/{test_data['segment_code']}",
            json=tpl_update
        )

        # Check consultation type config is unchanged
        ct_response = client.get(
            f"/api/v1/summary/admin/consultation-type-segments/{test_data['consultation_type_id']}/{test_data['segment_code']}"
        )
        ct_data = ct_response.json()

        # Consultation type config should still have its values from previous test
        assert ct_data["category"] == "core"  # From previous test
        assert ct_data["brevity_level"] == "detailed"  # From previous test

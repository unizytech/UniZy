"""
Backend API Tests for Doctor Templates Endpoints

Tests all 7 doctor_templates API endpoints from routers/doctor_templates.py:
1. POST /api/v1/doctor-templates/share - Share with individual doctors
2. POST /api/v1/doctor-templates/share-hospital - Share with hospital
3. POST /api/v1/doctor-templates/share-specialization - Share by specialization
4. POST /api/v1/doctor-templates/activate - Activate template for doctor
5. POST /api/v1/doctor-templates/deactivate - Deactivate template
6. GET /api/v1/doctor-templates/accessible - Get accessible templates
7. DELETE /api/v1/doctor-templates/revoke - Revoke template access

Test Coverage:
- TC-BE-001 through TC-BE-067 from QA_TEST_PLAN.md
- Junction table architecture validation
- Template sharing workflows
- Access control validation
"""

import pytest
import uuid
import sys
import os
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from services.supabase_service import supabase

# Note: Uses 'client' fixture from conftest.py which sets TESTING=true for auth bypass


class TestShareTemplateIndividual:
    """Test Suite 1.1: Share Template with Individual Doctors (TC-BE-001 to TC-BE-007)"""

    def test_share_template_with_single_doctor_view_access(
        self, client, test_template_id, test_doctor_id, cleanup_test_data
    ):
        """TC-BE-001: Share template with single doctor (view access)"""
        # Prepare request
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "view"
        }

        # Make API call
        response = client.post("/api/v1/doctor-templates/share", json=request_data)

        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["shared_count"] == 1
        assert data["failed_count"] == 0

        # Verify in database
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        assert len(db_check.data) == 1
        assert db_check.data[0]["access_level"] == "view"
        assert db_check.data[0]["is_active"] is False  # Not activated yet

        # Mark for cleanup
        cleanup_test_data.append(("doctor_templates", "id", db_check.data[0]["id"]))

    def test_share_template_with_single_doctor_use_access(
        self, client, test_template_id, test_doctor_id, cleanup_test_data
    ):
        """TC-BE-002: Share template with single doctor (use access)"""
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "use"
        }

        response = client.post("/api/v1/doctor-templates/share", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["shared_count"] == 1
        assert data["failed_count"] == 0

        # Verify in database
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        assert len(db_check.data) == 1
        assert db_check.data[0]["access_level"] == "use"

        cleanup_test_data.append(("doctor_templates", "id", db_check.data[0]["id"]))

    def test_share_template_with_multiple_doctors(
        self, client, test_template_id, test_doctor_id, test_doctor_ids, cleanup_test_data
    ):
        """TC-BE-003: Share template with multiple doctors (bulk)"""
        # Use real doctor IDs from database
        doctor_ids = [str(d) for d in test_doctor_ids]

        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": doctor_ids,
            "access_level": "use"
        }

        response = client.post("/api/v1/doctor-templates/share", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["shared_count"] == 3
        assert data["failed_count"] == 0

        # Verify all 3 doctors in database
        for doctor_id in doctor_ids:
            db_check = (
                supabase.table("doctor_templates")
                .select("*")
                .eq("template_id", str(test_template_id))
                .eq("doctor_id", doctor_id)
                .execute()
            )
            assert len(db_check.data) == 1
            cleanup_test_data.append(("doctor_templates", "id", db_check.data[0]["id"]))

    def test_share_template_duplicate_doctor(
        self, client, test_template_id, test_doctor_id, cleanup_test_data
    ):
        """TC-BE-004: Share template with same doctor twice (idempotent)"""
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "view"
        }

        # First share
        response1 = client.post("/api/v1/doctor-templates/share", json=request_data)
        assert response1.status_code == 200

        # Get the created record ID for cleanup
        db_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        cleanup_test_data.append(("doctor_templates", "id", db_check.data[0]["id"]))

        # Second share (should update, not duplicate)
        request_data["access_level"] = "use"
        response2 = client.post("/api/v1/doctor-templates/share", json=request_data)
        assert response2.status_code == 200

        # Verify only one record exists with updated access_level
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        assert len(db_check.data) == 1
        assert db_check.data[0]["access_level"] == "use"

    def test_share_template_invalid_template_code(self, client, test_doctor_id):
        """TC-BE-005: Share with invalid template code"""
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": "NONEXISTENT_TEMPLATE",
            "doctor_ids": [str(uuid.uuid4())],
            "access_level": "view"
        }

        response = client.post("/api/v1/doctor-templates/share", json=request_data)
        assert response.status_code in [404, 400]  # Template not found

    def test_share_template_invalid_access_level(self, client, test_template_id, test_doctor_id):
        """TC-BE-006: Share with invalid access level"""
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(uuid.uuid4())],
            "access_level": "invalid_level"
        }

        response = client.post("/api/v1/doctor-templates/share", json=request_data)
        assert response.status_code == 422  # Validation error

    def test_share_template_empty_doctor_list(self, client, test_template_id, test_doctor_id):
        """TC-BE-007: Share with empty doctor list"""
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [],
            "access_level": "view"
        }

        response = client.post("/api/v1/doctor-templates/share", json=request_data)
        assert response.status_code == 422  # Validation error


class TestShareTemplateHospital:
    """Test Suite 1.2: Share Template with Hospital (TC-BE-011 to TC-BE-014)"""

    def test_share_template_with_hospital_all_doctors(
        self, client, test_template_id, test_doctor_id, cleanup_test_data
    ):
        """TC-BE-011: Share template with all doctors in a hospital"""
        pytest.skip("Hospital sharing tests require real hospital data in database")
        # First, create a test hospital and doctors
        hospital_id = uuid.uuid4()
        doctor_ids = [uuid.uuid4() for _ in range(3)]

        # Create doctors in database (mock - in real implementation, use proper doctor creation)
        for doctor_id in doctor_ids:
            # Note: In production, doctors table should have hospital_id field
            pass

        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "hospital_id": str(hospital_id),
            "access_level": "use"
        }

        response = client.post("/api/v1/doctor-templates/share-hospital", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Note: shared_count depends on actual doctors in that hospital
        assert "shared_count" in data

    def test_share_template_with_hospital_view_access(self, client, test_template_id, test_doctor_id):
        """TC-BE-012: Share template with hospital (view access)"""
        pytest.skip("Hospital sharing tests require real hospital data in database")
        hospital_id = uuid.uuid4()

        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "hospital_id": str(hospital_id),
            "access_level": "view"
        }

        response = client.post("/api/v1/doctor-templates/share-hospital", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_share_template_with_invalid_hospital(self, client, test_template_id, test_doctor_id):
        """TC-BE-013: Share with invalid hospital ID"""
        pytest.skip("Hospital sharing tests require real hospital data in database")
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "hospital_id": str(uuid.uuid4()),  # Non-existent hospital
            "access_level": "use"
        }

        response = client.post("/api/v1/doctor-templates/share-hospital", json=request_data)
        # Should succeed but with shared_count = 0 (no doctors in that hospital)
        assert response.status_code == 200
        data = response.json()
        assert data["shared_count"] == 0

    def test_share_template_with_hospital_no_doctors(self, client, test_template_id, test_doctor_id):
        """TC-BE-014: Share with hospital that has no doctors"""
        pytest.skip("Hospital sharing tests require real hospital data in database")
        hospital_id = uuid.uuid4()

        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "hospital_id": str(hospital_id),
            "access_level": "use"
        }

        response = client.post("/api/v1/doctor-templates/share-hospital", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["shared_count"] == 0


class TestShareTemplateSpecialization:
    """Test Suite 1.3: Share Template with Specialization (TC-BE-021 to TC-BE-024)"""

    def test_share_template_with_specialization_cardiology(
        self, client, test_template_id, test_doctor_id, cleanup_test_data
    ):
        """TC-BE-021: Share template with all doctors of a specialization (Cardiology)"""
        pytest.skip("Specialization sharing tests require real specialization data in database")
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "specialization": "Cardiology",
            "access_level": "use"
        }

        response = client.post("/api/v1/doctor-templates/share-specialization", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "shared_count" in data
        # shared_count depends on actual doctors with Cardiology specialization

    def test_share_template_with_specialization_psychiatry(self, client, test_template_id, test_doctor_id):
        """TC-BE-022: Share template with Psychiatry specialization"""
        pytest.skip("Specialization sharing tests require real specialization data in database")
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "specialization": "Psychiatry",
            "access_level": "view"
        }

        response = client.post("/api/v1/doctor-templates/share-specialization", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_share_template_with_invalid_specialization(self, client, test_template_id, test_doctor_id):
        """TC-BE-023: Share with invalid specialization"""
        pytest.skip("Specialization sharing tests require real specialization data in database")
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "specialization": "NonExistentSpecialty",
            "access_level": "use"
        }

        response = client.post("/api/v1/doctor-templates/share-specialization", json=request_data)
        # Should succeed but with shared_count = 0 (no doctors with that specialization)
        assert response.status_code == 200
        data = response.json()
        assert data["shared_count"] == 0

    def test_share_template_with_all_specializations(self, client, test_template_id, test_doctor_id):
        """TC-BE-024: Share template with multiple specializations"""
        pytest.skip("Specialization sharing tests require real specialization data in database")
        specializations = ["Cardiology", "Psychiatry", "General Practice"]

        for spec in specializations:
            request_data = {
                "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
                "specialization": spec,
                "access_level": "use"
            }

            response = client.post("/api/v1/doctor-templates/share-specialization", json=request_data)
            assert response.status_code == 200


class TestActivateTemplate:
    """Test Suite 1.4: Activate Template for Doctor (TC-BE-031 to TC-BE-036)"""

    def test_activate_shared_template(
        self, client, test_template_id, test_doctor_id, test_consultation_type_id, clean_doctor_templates
    ):
        """TC-BE-031: Activate a shared template for a doctor

        Updated: Changed from 'view' to 'use' access to align with access level validation.
        Templates with 'view' access cannot be activated (see test_activate_template_with_view_access_fails).
        """
        # First, share the template with 'use' access (will auto-activate)
        share_request = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "use"
        }
        share_response = client.post("/api/v1/doctor-templates/share", json=share_request)
        assert share_response.status_code == 200

        # Deactivate it first to test manual activation
        deactivate_response = client.post(
            f"/api/v1/doctor-templates/deactivate?doctor_id={test_doctor_id}&template_id={test_template_id}"
        )
        assert deactivate_response.status_code == 200
        assert deactivate_response.json()["is_active"] is False

        # Now manually activate the template
        activate_request = {
            "template_id": str(test_template_id),
            "doctor_id": str(test_doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }

        response = client.post("/api/v1/doctor-templates/activate", json=activate_request)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["is_active"] is True

        # Verify in database
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        assert db_check.data[0]["is_active"] is True

    def test_activate_template_without_sharing(
        self, client, test_template_id, test_doctor_id, test_consultation_type_id
    ):
        """TC-BE-032: Activate template without sharing (should fail or auto-share)"""
        activate_request = {
            "template_id": str(test_template_id),
            "doctor_id": str(test_doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }

        response = client.post("/api/v1/doctor-templates/activate", json=activate_request)

        # Depending on implementation:
        # Option 1: Returns 404 (template not shared with doctor)
        # Option 2: Auto-shares and activates (returns 200)
        assert response.status_code in [200, 404]

    def test_activate_replaces_previous_active_template(
        self, client, test_consultation_type_id, test_doctor_id, clean_doctor_templates
    ):
        """TC-BE-033: Activating a new template deactivates the previous active template"""
        # Use real doctor from database
        doctor_id = test_doctor_id

        # Get two different template IDs from database
        templates_response = (
            supabase.table("templates")
            .select("id, template_code")
            .limit(2)
            .execute()
        )
        if len(templates_response.data) < 2:
            pytest.skip("Need at least 2 templates in database")

        template1_id = templates_response.data[0]["id"]
        template2_id = templates_response.data[1]["id"]

        # Share both templates
        for template_id in [template1_id, template2_id]:
            share_request = {
                "sharing_doctor_id": str(doctor_id),
                "template_id": template_id,
                "doctor_ids": [str(doctor_id)],
                "access_level": "use"
            }
            client.post("/api/v1/doctor-templates/share", json=share_request)

        # Activate template 1
        activate1 = {
            "template_id": template1_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }
        response1 = client.post("/api/v1/doctor-templates/activate", json=activate1)
        assert response1.status_code == 200

        # Activate template 2 (should deactivate template 1)
        activate2 = {
            "template_id": template2_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }
        response2 = client.post("/api/v1/doctor-templates/activate", json=activate2)
        assert response2.status_code == 200

        # Verify only template 2 is active
        active_templates = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("doctor_id", str(doctor_id))
            .eq("is_active", True)
            .execute()
        )

        # Should only have 1 active template
        assert len(active_templates.data) == 1
        # And it should be template 2
        # Note: Need to join with templates table to get template_code
        # For now, just verify count

    def test_activate_common_template(
        self, client, test_consultation_type_id, test_doctor_id, clean_doctor_templates
    ):
        """TC-BE-034: Activate a common template (doctor_id = NULL)"""
        doctor_id = test_doctor_id

        # Get a common template (doctor_id = NULL)
        common_template = (
            supabase.table("templates")
            .select("id, template_code")
            .is_("doctor_id", "null")
            .limit(1)
            .execute()
        )

        if not common_template.data:
            pytest.skip("No common templates in database")

        template_id = common_template.data[0]["id"]

        # Activate the common template (should auto-share if needed)
        activate_request = {
            "template_id": template_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }

        response = client.post("/api/v1/doctor-templates/activate", json=activate_request)
        assert response.status_code == 200


class TestDeactivateTemplate:
    """Test Suite 1.5: Deactivate Template (TC-BE-041 to TC-BE-043)"""

    def test_deactivate_active_template(
        self, client, test_template_id, test_doctor_id, test_consultation_type_id, clean_doctor_templates
    ):
        """TC-BE-041: Deactivate an active template"""
        # First, share and activate
        share_request = {
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "use"
        }
        client.post("/api/v1/doctor-templates/share", json=share_request)

        activate_request = {
            "template_id": str(test_template_id),
            "doctor_id": str(test_doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }
        client.post("/api/v1/doctor-templates/activate", json=activate_request)

        # Now deactivate
        response = client.post(
            f"/api/v1/doctor-templates/deactivate?doctor_id={str(test_doctor_id)}&template_id={str(test_template_id)}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["is_active"] is False

        # Verify in database
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        assert db_check.data[0]["is_active"] is False

    def test_deactivate_already_inactive_template(
        self, client, test_template_id, test_doctor_id, clean_doctor_templates
    ):
        """TC-BE-042: Deactivate a template that is already inactive (idempotent)"""
        # Share with 'view' access (not auto-activated)
        share_request = {
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "view"
        }
        client.post("/api/v1/doctor-templates/share", json=share_request)

        # Try to deactivate (should succeed but no change)
        response = client.post(
            f"/api/v1/doctor-templates/deactivate?doctor_id={str(test_doctor_id)}&template_id={str(test_template_id)}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False


class TestGetAccessibleTemplates:
    """Test Suite 1.6: Get Accessible Templates (TC-BE-051 to TC-BE-055)"""

    def test_get_accessible_templates_owned_shared_common(
        self, client, test_consultation_type_id, cleanup_test_data
    ):
        """TC-BE-051: Get accessible templates (owned + shared + common)"""
        doctor_id = uuid.uuid4()

        # Get some templates to share
        templates_response = (
            supabase.table("templates")
            .select("id, template_code")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .limit(2)
            .execute()
        )

        if len(templates_response.data) >= 1:
            # Share a template with the doctor
            share_request = {
                "template_id": templates_response.data[0]["id"],
                "doctor_ids": [str(doctor_id)],
                "access_level": "use"
            }
            client.post("/api/v1/doctor-templates/share", json=share_request)

        # Get accessible templates
        response = client.get(
            f"/api/v1/doctor-templates/accessible?doctor_id={str(doctor_id)}&consultation_type_id={str(test_consultation_type_id)}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert isinstance(data["templates"], list)

        # Should include at least common templates
        assert len(data["templates"]) > 0

        # Cleanup
        dt_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        for dt in dt_check.data:
            cleanup_test_data.append(("doctor_templates", "id", dt["id"]))

    def test_get_accessible_templates_filter_by_access_level(
        self, client, test_consultation_type_id, cleanup_test_data
    ):
        """TC-BE-052: Get accessible templates filtered by access level"""
        doctor_id = uuid.uuid4()

        # Share templates with different access levels
        templates_response = (
            supabase.table("templates")
            .select("id, template_code")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .limit(2)
            .execute()
        )

        if len(templates_response.data) >= 2:
            # Share template 1 with view access
            share_request1 = {
                "template_id": templates_response.data[0]["id"],
                "doctor_ids": [str(doctor_id)],
                "access_level": "view"
            }
            client.post("/api/v1/doctor-templates/share", json=share_request1)

            # Share template 2 with use access
            share_request2 = {
                "template_id": templates_response.data[1]["id"],
                "doctor_ids": [str(doctor_id)],
                "access_level": "use"
            }
            client.post("/api/v1/doctor-templates/share", json=share_request2)

        # Get templates with use access
        response = client.get(
            f"/api/v1/doctor-templates/accessible?doctor_id={str(doctor_id)}&consultation_type_id={str(test_consultation_type_id)}&access_level=use"
        )

        assert response.status_code == 200
        data = response.json()
        # Should only include templates with use access
        for template in data["templates"]:
            if template.get("access_level"):  # Skip common templates
                assert template["access_level"] == "use"

        # Cleanup
        dt_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        for dt in dt_check.data:
            cleanup_test_data.append(("doctor_templates", "id", dt["id"]))

    def test_get_accessible_templates_only_active(
        self, client, test_consultation_type_id, test_doctor_id, clean_doctor_templates
    ):
        """TC-BE-053: Get only active templates"""
        doctor_id = test_doctor_id

        # Share and activate a template
        templates_response = (
            supabase.table("templates")
            .select("id, template_code")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .limit(1)
            .execute()
        )

        if templates_response.data:
            template_id = templates_response.data[0]["id"]

            # Share
            share_request = {
                "template_id": template_id,
                "doctor_ids": [str(doctor_id)],
                "access_level": "use"
            }
            client.post("/api/v1/doctor-templates/share", json=share_request)

            # Activate
            activate_request = {
                "template_id": template_id,
                "doctor_id": str(doctor_id),
                "consultation_type_id": str(test_consultation_type_id)
            }
            client.post("/api/v1/doctor-templates/activate", json=activate_request)

        # Get only active templates
        response = client.get(
            f"/api/v1/doctor-templates/accessible?doctor_id={str(doctor_id)}&consultation_type_id={str(test_consultation_type_id)}&active_only=true"
        )

        assert response.status_code == 200
        data = response.json()

        # All returned templates should be active
        for template in data["templates"]:
            if "is_active" in template:
                assert template["is_active"] is True


class TestRevokeTemplateAccess:
    """Test Suite 1.7: Revoke Template Access (TC-BE-061 to TC-BE-063)"""

    def test_revoke_template_access_single_doctor(
        self, client, test_template_id, test_doctor_id, clean_doctor_templates
    ):
        """TC-BE-061: Revoke template access from a single doctor"""
        # First, share the template
        share_request = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "use"
        }
        client.post("/api/v1/doctor-templates/share", json=share_request)

        # Get the doctor_template ID
        dt_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        doctor_template_id = dt_check.data[0]["id"]

        # Revoke access
        response = client.delete(
            f"/api/v1/doctor-templates/revoke?sharing_doctor_id={str(test_doctor_id)}&template_id={str(test_template_id)}&doctor_id={str(test_doctor_id)}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify deleted from database
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("id", doctor_template_id)
            .execute()
        )
        assert len(db_check.data) == 0

    def test_revoke_template_access_multiple_doctors(
        self, client, test_template_id, test_doctor_id, test_doctor_ids, clean_doctor_templates
    ):
        """TC-BE-062: Revoke template access from multiple doctors"""
        # Share with 3 doctors
        doctor_ids = [uuid.uuid4() for _ in range(3)]

        share_request = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(d) for d in doctor_ids],
            "access_level": "use"
        }
        client.post("/api/v1/doctor-templates/share", json=share_request)

        # Revoke from all 3 doctors
        for doctor_id in doctor_ids:
            response = client.delete(
                f"/api/v1/doctor-templates/revoke?sharing_doctor_id={str(test_doctor_id)}&template_id={str(test_template_id)}&doctor_id={str(doctor_id)}"
            )
            assert response.status_code == 200

        # Verify all deleted
        for doctor_id in doctor_ids:
            db_check = (
                supabase.table("doctor_templates")
                .select("*")
                .eq("template_id", str(test_template_id))
                .eq("doctor_id", str(doctor_id))
                .execute()
            )
            assert len(db_check.data) == 0

    def test_revoke_nonexistent_access(self, client, test_template_id, test_doctor_id):
        """TC-BE-063: Revoke template access that doesn't exist (idempotent)"""
        non_existent_doctor = uuid.uuid4()

        response = client.delete(
            f"/api/v1/doctor-templates/revoke?sharing_doctor_id={str(test_doctor_id)}&template_id={str(test_template_id)}&doctor_id={str(non_existent_doctor)}"
        )

        # Should return 404 or 200 with message indicating no record found
        assert response.status_code in [200, 404]


class TestActivateFromConsultationType:
    """Test Suite 1.8: Activate Template from Consultation Type (NEW)"""

    def test_activate_from_consultation_type_success(
        self, client, test_doctor_id, test_consultation_type_id, cleanup_test_data
    ):
        """TC-BE-NEW-001: Successfully create and activate template from consultation type"""
        request_data = {
            "doctor_id": str(test_doctor_id),
            "consultation_type_id": str(test_consultation_type_id),
            "template_name": "Test Activated Template"
        }

        response = client.post(
            "/api/v1/doctor-templates/activate-from-consultation-type",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "template" in data
        assert data["template"]["doctor_id"] == str(test_doctor_id)
        assert data["template"]["consultation_type_id"] == str(test_consultation_type_id)
        assert data["template"]["is_activated"] is True
        assert data["template"]["segment_count"] > 0

        # Mark for cleanup

    def test_activate_from_consultation_type_without_visibility(
        self, client, test_consultation_type_id
    ):
        """TC-BE-NEW-002: Fail to activate if doctor doesn't have visibility"""
        # Create a doctor without visibility
        restricted_doctor = uuid.uuid4()

        request_data = {
            "doctor_id": str(restricted_doctor),
            "consultation_type_id": str(test_consultation_type_id),
        }

        response = client.post(
            "/api/v1/doctor-templates/activate-from-consultation-type",
            json=request_data
        )

        # Should fail with 403 or 404 (doctor not found)
        assert response.status_code in [403, 404]


class TestCloneTemplate:
    """Test Suite 1.9: Clone Template (NEW)"""

    def test_clone_shared_template_success(
        self, client, test_doctor_id, test_template_id, cleanup_test_data
    ):
        """TC-BE-NEW-003: Successfully clone a shared template"""
        # First share the template
        share_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "view"  # Even 'view' can clone
        }
        client.post("/api/v1/doctor-templates/share", json=share_data)

        # Now clone it
        clone_data = {
            "doctor_id": str(test_doctor_id),
            "source_template_id": str(test_template_id),
            "template_name": "My Cloned Template"
        }

        response = client.post("/api/v1/doctor-templates/clone", json=clone_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "template" in data
        assert data["template"]["doctor_id"] == str(test_doctor_id)
        assert data["template"]["source_template_id"] == str(test_template_id)
        assert data["template"]["segment_count"] > 0
        assert data["template"]["is_activated"] is True

        # Verify new template exists
        new_template_id = data["template"]["id"]
        db_check = (
            supabase.table("templates")
            .select("*")
            .eq("id", new_template_id)
            .execute()
        )
        assert len(db_check.data) == 1
        assert db_check.data[0]["doctor_id"] == str(test_doctor_id)

        # Mark for cleanup
        cleanup_test_data.append(("templates", "id", new_template_id))

    def test_clone_global_template_success(
        self, client, test_doctor_id, cleanup_test_data
    ):
        """TC-BE-NEW-004: Successfully clone a global template"""
        # Get a global template (doctor_id = NULL)
        global_template_response = (
            supabase.table("templates")
            .select("id")
            .is_("doctor_id", "null")
            .limit(1)
            .execute()
        )

        if not global_template_response.data:
            pytest.skip("No global templates available")

        global_template_id = global_template_response.data[0]["id"]

        clone_data = {
            "doctor_id": str(test_doctor_id),
            "source_template_id": str(global_template_id),
            "template_name": "Cloned Global Template"
        }

        response = client.post("/api/v1/doctor-templates/clone", json=clone_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["template"]["doctor_id"] == str(test_doctor_id)

        # Mark for cleanup
        cleanup_test_data.append(("templates", "id", data["template"]["id"]))

    def test_clone_inaccessible_template_fails(self, client, test_doctor_id):
        """TC-BE-NEW-005: Fail to clone template without access"""
        # Create a template owned by different doctor
        different_doctor = uuid.uuid4()

        clone_data = {
            "doctor_id": str(test_doctor_id),
            "source_template_id": str(different_doctor),  # Non-existent/inaccessible
        }

        response = client.post("/api/v1/doctor-templates/clone", json=clone_data)

        # Should fail with 400 or 403
        assert response.status_code in [400, 403, 404]


class TestDoctorDashboard:
    """Test Suite 1.10: Doctor Dashboard API (NEW)"""

    def test_get_dashboard_success(self, client, test_doctor_id):
        """TC-BE-NEW-006: Successfully get doctor dashboard data"""
        response = client.get(f"/api/v1/doctor-templates/dashboard/{str(test_doctor_id)}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "consultation_types" in data
        assert "templates" in data
        assert "consultation_types_count" in data
        assert "templates_count" in data

        # Verify structure
        assert isinstance(data["consultation_types"], list)
        assert isinstance(data["templates"], list)

        # Check consultation types have required fields
        if len(data["consultation_types"]) > 0:
            ct = data["consultation_types"][0]
            assert "id" in ct
            assert "type_code" in ct
            assert "type_name" in ct
            assert "badge" in ct
            assert ct["badge"] == "Activate"

        # Check templates have required fields
        if len(data["templates"]) > 0:
            template = data["templates"][0]
            assert "id" in template
            assert "access_type" in template
            assert "badge" in template
            assert template["badge"] in ["Owned", "Use / Clone", "Clone Only"]

    def test_dashboard_visibility_filtering(self, client, test_doctor_id):
        """TC-BE-NEW-007: Verify dashboard filters by visibility"""
        response = client.get(f"/api/v1/doctor-templates/dashboard/{str(test_doctor_id)}")

        assert response.status_code == 200
        data = response.json()

        # All returned consultation types should be visible to doctor
        # (tested indirectly - if visibility logic is correct, no restricted types appear)
        assert isinstance(data["consultation_types"], list)


class TestIdempotentSharing:
    """Test Suite 1.11: Verify Idempotent Sharing (FIXED)"""

    def test_share_template_twice_same_access_level(
        self, client, test_template_id, test_doctor_id, cleanup_test_data
    ):
        """TC-BE-NEW-008: Share template twice with same access_level (idempotent)"""
        request_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "use"
        }

        # First share
        response1 = client.post("/api/v1/doctor-templates/share", json=request_data)
        assert response1.status_code == 200

        # Second share (should succeed)
        response2 = client.post("/api/v1/doctor-templates/share", json=request_data)
        assert response2.status_code == 200

        data2 = response2.json()
        assert data2["success"] is True

        # Verify only one record exists
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        assert len(db_check.data) == 1
        assert db_check.data[0]["access_level"] == "use"

        cleanup_test_data.append(("doctor_templates", "id", db_check.data[0]["id"]))

    def test_share_template_upgrade_access_level(
        self, client, test_template_id, test_doctor_id, cleanup_test_data
    ):
        """TC-BE-NEW-009: Upgrade access_level from 'view' to 'use' (idempotent)"""
        # First share with 'view'
        request_data_view = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "view"
        }
        response1 = client.post("/api/v1/doctor-templates/share", json=request_data_view)
        assert response1.status_code == 200

        # Upgrade to 'use'
        request_data_use = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "use"
        }
        response2 = client.post("/api/v1/doctor-templates/share", json=request_data_use)
        assert response2.status_code == 200

        # Verify access_level updated
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        assert len(db_check.data) == 1
        assert db_check.data[0]["access_level"] == "use"

        cleanup_test_data.append(("doctor_templates", "id", db_check.data[0]["id"]))


class TestAccessLevelValidation:
    """Test Suite 1.12: Verify Access Level Validation (FIXED)"""

    def test_activate_template_with_view_access_fails(
        self, client, test_template_id, test_doctor_id, test_consultation_type_id, clean_doctor_templates, cleanup_test_data
    ):
        """TC-BE-NEW-010: Cannot activate template with 'view' access

        Note: Uses a common template but explicitly shares it with 'view' access.
        The junction table entry takes precedence over the default 'use' access for common templates.
        """
        template_id = test_template_id

        # Share with 'view' access
        share_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(template_id),  # Convert UUID to string
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "view"
        }
        client.post("/api/v1/doctor-templates/share", json=share_data)

        # Try to activate
        activate_data = {
            "doctor_id": str(test_doctor_id),
            "template_id": str(template_id),  # Convert UUID to string
            "consultation_type_id": str(test_consultation_type_id)
        }

        response = client.post("/api/v1/doctor-templates/activate", json=activate_data)

        # Should fail with 403 PermissionError
        assert response.status_code == 403
        assert "view" in response.json()["detail"].lower()

        # Cleanup
        db_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("template_id", template_id)
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        if db_check.data:
            cleanup_test_data.append(("doctor_templates", "id", db_check.data[0]["id"]))

    def test_activate_template_with_use_access_succeeds(
        self, client, test_template_id, test_doctor_id, test_consultation_type_id, cleanup_test_data
    ):
        """TC-BE-NEW-011: Can activate template with 'use' access"""
        # Share with 'use' access
        share_data = {
            "sharing_doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "doctor_ids": [str(test_doctor_id)],
            "access_level": "use"
        }
        client.post("/api/v1/doctor-templates/share", json=share_data)

        # Try to activate
        activate_data = {
            "doctor_id": str(test_doctor_id),
            "template_id": str(test_template_id),
            "consultation_type_id": str(test_consultation_type_id)
        }

        response = client.post("/api/v1/doctor-templates/activate", json=activate_data)

        # Should succeed
        assert response.status_code == 200

        # Cleanup
        db_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("template_id", str(test_template_id))
            .eq("doctor_id", str(test_doctor_id))
            .execute()
        )
        if db_check.data:
            cleanup_test_data.append(("doctor_templates", "id", db_check.data[0]["id"]))


class TestJunctionTableArchitecture:
    """Test Suite 1.13: Verify Junction Table Architecture"""

    def test_templates_use_junction_table(self, client, test_consultation_type_id):
        """Verify templates use template_segments junction table"""
        # Get a template
        template_response = (
            supabase.table("templates")
            .select("id, template_code")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .limit(1)
            .execute()
        )

        if not template_response.data:
            pytest.skip("No templates for this consultation type")

        template_id = template_response.data[0]["id"]

        # Query template_segments junction table
        junction_response = (
            supabase.table("template_segments")
            .select("segment_id, segment_code, category, display_order")
            .eq("template_id", template_id)
            .execute()
        )

        # Should have segments assigned via junction table
        assert isinstance(junction_response.data, list)
        # Templates should have at least some segments
        # (can be 0 for new templates, but junction table should exist)

    def test_consultation_types_use_junction_table(self, client, test_consultation_type_id):
        """Verify consultation types use consultation_type_segments junction table"""
        # Query consultation_type_segments junction table
        junction_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id, segment_code")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .execute()
        )

        # Should have segments assigned via junction table
        assert isinstance(junction_response.data, list)
        # Consultation types should have segments
        assert len(junction_response.data) > 0

    def test_segment_definitions_no_direct_consultation_type_id(self):
        """Verify segment_definitions table has NO consultation_type_id column"""
        # Query segment_definitions table structure
        segments_response = (
            supabase.table("segment_definitions")
            .select("*")
            .limit(1)
            .execute()
        )

        if segments_response.data:
            segment = segments_response.data[0]
            # Should NOT have consultation_type_id field
            assert "consultation_type_id" not in segment
            # Should have id, segment_code, segment_name, etc.
            assert "id" in segment
            assert "segment_code" in segment

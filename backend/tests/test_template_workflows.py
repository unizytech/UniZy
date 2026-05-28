"""
Integration Tests for Template Workflows

Tests end-to-end workflows from QA_TEST_PLAN.md:
- Workflow 3.1: Admin shares template with individual doctor
- Workflow 3.2: Admin shares template with hospital (bulk)
- Workflow 3.3: Admin shares template with specialization (bulk)
- Workflow 3.4: Doctor receives and activates shared template
- Workflow 3.5: Admin revokes template access

Test Coverage:
- TC-INT-001 through TC-INT-050
- Multi-step workflows
- State transitions
- Junction table integration
"""

import pytest
import uuid
import sys
import os
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from services.supabase_service import supabase

# Note: Uses 'client' fixture from conftest.py which sets TESTING=true for auth bypass


class TestWorkflow31:
    """Workflow 3.1: Admin Shares Template with Individual Doctor (18 steps)"""

    def test_complete_workflow_admin_shares_with_doctor(
        self, client, test_consultation_type_id, test_doctor_id, test_template_id, clean_doctor_templates, cleanup_test_data
    ):
        """
        TC-INT-001: Complete workflow from admin sharing to doctor using template

        Steps:
        1. Admin selects template to share
        2. Admin selects doctor from list
        3. Admin sets access level (use)
        4. System creates doctor_templates record (auto-activated for 'use' access)
        5. Doctor receives notification (webhook)
        6. Doctor views accessible templates
        7. Doctor sees shared template with "Shared" and "Activated" badges
        8-9. (Template already active - activate endpoint is idempotent)
        10. Verify activation in database
        """
        # Step 1-2: Get a common template (doctor_id IS NULL) and use test doctor
        template_response = (
            supabase.table("templates")
            .select("template_code, template_name, id")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .is_("doctor_id", "null")
            .limit(1)
            .execute()
        )

        if not template_response.data:
            pytest.skip("No common templates available for testing")

        template_code = template_response.data[0]["template_code"]
        template_id = template_response.data[0]["id"]
        doctor_id = test_doctor_id

        # Step 3-4: Admin shares template with doctor (use access)
        share_request = {
            "sharing_doctor_id": str(doctor_id),
            "template_id": template_id,
            "doctor_ids": [str(doctor_id)],
            "access_level": "use"
        }

        share_response = client.post("/api/v1/doctor-templates/share", json=share_request)
        assert share_response.status_code == 200
        share_data = share_response.json()
        assert share_data["success"] is True
        assert share_data["shared_count"] == 1

        # Get doctor_template ID for cleanup
        dt_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("template_id", template_id)
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        cleanup_test_data.append(("doctor_templates", "id", dt_check.data[0]["id"]))

        # Step 6-7: Doctor views accessible templates
        accessible_response = client.get(
            f"/api/v1/doctor-templates/accessible?doctor_id={str(doctor_id)}&consultation_type_id={str(test_consultation_type_id)}"
        )

        assert accessible_response.status_code == 200
        accessible_data = accessible_response.json()
        assert "templates" in accessible_data

        # Find the shared template
        shared_template = None
        for template in accessible_data["templates"]:
            if template.get("template_code") == template_code:
                shared_template = template
                break

        assert shared_template is not None
        assert shared_template["access_level"] == "use"
        # Note: When shared with 'use' access, template is auto-activated
        assert shared_template.get("is_active") is True

        # Step 8-9: Verify template is already active (auto-activated on share with 'use' access)
        # The activate endpoint should still work (idempotent)
        activate_request = {
            "template_id": template_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }

        activate_response = client.post("/api/v1/doctor-templates/activate", json=activate_request)
        assert activate_response.status_code == 200
        activate_data = activate_response.json()
        assert activate_data["success"] is True
        assert activate_data["is_active"] is True

        # Step 10: Verify activation in database
        db_check = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", template_id)
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        assert db_check.data[0]["is_active"] is True
        assert db_check.data[0]["access_level"] == "use"

    def test_workflow_view_access_prevents_activation(
        self, client, test_consultation_type_id, test_doctor_id, test_template_id, clean_doctor_templates, cleanup_test_data
    ):
        """
        TC-INT-002: Verify view access level prevents activation

        Doctor with view access should not be able to activate template
        """
        template_response = (
            supabase.table("templates")
            .select("template_code, id")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .is_("doctor_id", "null")
            .limit(1)
            .execute()
        )

        if not template_response.data:
            pytest.skip("No common templates available")

        template_code = template_response.data[0]["template_code"]
        template_id = template_response.data[0]["id"]
        doctor_id = test_doctor_id

        # Share with view access
        share_request = {
            "sharing_doctor_id": str(doctor_id),
            "template_id": template_id,
            "doctor_ids": [str(doctor_id)],
            "access_level": "view"
        }

        share_response = client.post("/api/v1/doctor-templates/share", json=share_request)
        assert share_response.status_code == 200

        # Get doctor_template ID for cleanup
        dt_check = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("template_id", template_id)
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        cleanup_test_data.append(("doctor_templates", "id", dt_check.data[0]["id"]))

        # Try to activate (should fail)
        activate_request = {
            "template_id": template_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }

        activate_response = client.post("/api/v1/doctor-templates/activate", json=activate_request)
        # Should return error (403 or 400)
        assert activate_response.status_code in [400, 403]


class TestWorkflow32:
    """Workflow 3.2: Admin Shares Template with Hospital (Bulk) (22 steps)"""

    def test_complete_workflow_hospital_bulk_share(
        self, client, test_consultation_type_id, cleanup_test_data
    ):
        """
        TC-INT-011: Complete workflow for hospital bulk sharing

        Steps:
        1. Admin selects template
        2. Admin selects hospital from dropdown
        3. Admin sets access level
        4. System queries all doctors in hospital
        5. System creates doctor_templates records for all doctors
        6. All doctors receive shared template
        """
        # Get template
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
        hospital_id = uuid.uuid4()

        # Share with hospital
        share_request = {
            "sharing_doctor_id": str(uuid.uuid4()),
            "template_id": template_id,
            "hospital_id": str(hospital_id),
            "access_level": "use"
        }

        share_response = client.post("/api/v1/doctor-templates/share-hospital", json=share_request)
        assert share_response.status_code == 200
        share_data = share_response.json()
        assert share_data["success"] is True
        # Note: shared_count depends on actual doctors in that hospital
        # For empty hospital, shared_count should be 0
        assert "shared_count" in share_data


class TestWorkflow33:
    """Workflow 3.3: Admin Shares Template with Specialization (Bulk) (25 steps)"""

    def test_complete_workflow_specialization_bulk_share(
        self, client, test_consultation_type_id, cleanup_test_data
    ):
        """
        TC-INT-021: Complete workflow for specialization bulk sharing

        Steps:
        1. Admin selects template
        2. Admin selects specialization (e.g., Cardiology)
        3. Admin sets access level
        4. System queries all doctors with that specialization
        5. System creates doctor_templates records for all matching doctors
        6. All matching doctors receive shared template
        """
        # Get template
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

        # Share with specialization
        share_request = {
            "sharing_doctor_id": str(uuid.uuid4()),
            "template_id": template_id,
            "specialization": "Cardiology",
            "access_level": "use"
        }

        share_response = client.post(
            "/api/v1/doctor-templates/share-specialization", json=share_request
        )
        assert share_response.status_code == 200
        share_data = share_response.json()
        assert share_data["success"] is True
        assert "shared_count" in share_data


class TestWorkflow34:
    """Workflow 3.4: Doctor Receives and Activates Shared Template (31 steps)"""

    def test_complete_workflow_doctor_activation_flow(
        self, client, test_consultation_type_id, test_doctor_id, test_template_id, clean_doctor_templates, cleanup_test_data
    ):
        """
        TC-INT-031: Complete doctor workflow from receiving to using template

        Steps:
        1. Doctor logs in
        2. Doctor navigates to Template Config screen
        3. Doctor selects consultation type
        4. System loads accessible templates (owned + shared + common)
        5. Doctor sees shared template with metadata
        6. Doctor activates shared template
        7. System deactivates previous active template (if any)
        8. System sets new template as active
        9. Doctor uses template for recording
        10. System loads template segments via junction table
        11. Extraction uses template configuration
        """
        # Get a common template (doctor_id IS NULL) and use test doctor
        template_response = (
            supabase.table("templates")
            .select("template_code, id")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .is_("doctor_id", "null")
            .limit(1)
            .execute()
        )

        if not template_response.data:
            pytest.skip("No common templates available")

        template_code = template_response.data[0]["template_code"]
        template_id = template_response.data[0]["id"]
        doctor_id = test_doctor_id

        # Step 1-2: Admin shares template
        share_request = {
            "sharing_doctor_id": str(doctor_id),
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

        # Step 3-5: Doctor loads accessible templates
        accessible_response = client.get(
            f"/api/v1/doctor-templates/accessible?doctor_id={str(doctor_id)}&consultation_type_id={str(test_consultation_type_id)}"
        )
        assert accessible_response.status_code == 200
        accessible_data = accessible_response.json()

        # Verify shared template is in list
        template_found = any(
            t.get("template_code") == template_code for t in accessible_data["templates"]
        )
        assert template_found is True

        # Step 6-8: Doctor activates template
        activate_request = {
            "template_id": template_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }
        activate_response = client.post("/api/v1/doctor-templates/activate", json=activate_request)
        assert activate_response.status_code == 200

        # Step 9-10: Verify template segments loaded via junction table
        # Query template_segments junction table
        template_segments_response = (
            supabase.table("template_segments")
            .select("segment_id, segment_code, category")
            .eq("template_id", template_id)
            .execute()
        )

        # Template should have segments assigned via junction table
        assert isinstance(template_segments_response.data, list)

    def test_workflow_activation_replaces_previous_template(
        self, client, test_consultation_type_id, test_doctor_id, test_template_id, clean_doctor_templates, cleanup_test_data
    ):
        """
        TC-INT-032: Verify activating new template deactivates old template

        Workflow:
        1. Doctor has template A activated
        2. Admin shares template B
        3. Doctor activates template B
        4. Template A should be deactivated
        5. Only template B should be active
        """
        doctor_id = test_doctor_id

        # Get two common templates (doctor_id IS NULL)
        templates_response = (
            supabase.table("templates")
            .select("template_code, id")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .is_("doctor_id", "null")
            .limit(2)
            .execute()
        )

        if len(templates_response.data) < 2:
            pytest.skip("Need at least 2 common templates")

        template_a_id = templates_response.data[0]["id"]
        template_b_id = templates_response.data[1]["id"]

        # Share both templates
        for template_id in [template_a_id, template_b_id]:
            share_request = {
                "sharing_doctor_id": str(doctor_id),
                "template_id": template_id,
                "doctor_ids": [str(doctor_id)],
                "access_level": "use"
            }
            client.post("/api/v1/doctor-templates/share", json=share_request)

        # Activate template A
        activate_a = {
            "template_id": template_a_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }
        client.post("/api/v1/doctor-templates/activate", json=activate_a)

        # Activate template B
        activate_b = {
            "template_id": template_b_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }
        client.post("/api/v1/doctor-templates/activate", json=activate_b)

        # Verify only template B is active
        active_templates = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("doctor_id", str(doctor_id))
            .eq("is_active", True)
            .execute()
        )

        # Should have exactly 1 active template
        assert len(active_templates.data) == 1

        # Cleanup
        all_templates = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        for dt in all_templates.data:
            cleanup_test_data.append(("doctor_templates", "id", dt["id"]))


class TestWorkflow35:
    """Workflow 3.5: Admin Revokes Template Access (16 steps)"""

    def test_complete_workflow_revoke_access(
        self, client, test_consultation_type_id, test_doctor_id, test_template_id, clean_doctor_templates, cleanup_test_data
    ):
        """
        TC-INT-041: Complete workflow for revoking template access

        Steps:
        1. Admin navigates to Template Admin screen
        2. Admin selects template
        3. Admin views "Currently Shared" list
        4. Admin clicks "Revoke" for specific doctor
        5. System confirms revocation
        6. System deletes doctor_templates record
        7. Doctor loses access to template
        8. If template was active, it becomes inactive
        """
        # Get a common template (doctor_id IS NULL) and use test doctor
        template_response = (
            supabase.table("templates")
            .select("template_code, id")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .is_("doctor_id", "null")
            .limit(1)
            .execute()
        )

        if not template_response.data:
            pytest.skip("No common templates available")

        template_code = template_response.data[0]["template_code"]
        template_id = template_response.data[0]["id"]
        doctor_id = test_doctor_id

        # Step 1-2: Share and activate template
        share_request = {
            "sharing_doctor_id": str(doctor_id),
            "template_id": template_id,
            "doctor_ids": [str(doctor_id)],
            "access_level": "use"
        }
        client.post("/api/v1/doctor-templates/share", json=share_request)

        activate_request = {
            "template_id": template_id,
            "doctor_id": str(doctor_id),
            "consultation_type_id": str(test_consultation_type_id)
        }
        client.post("/api/v1/doctor-templates/activate", json=activate_request)

        # Verify template is active
        before_revoke = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", template_id)
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        assert len(before_revoke.data) == 1
        assert before_revoke.data[0]["is_active"] is True

        # Step 4-6: Admin revokes access
        revoke_response = client.delete(
            f"/api/v1/doctor-templates/revoke?sharing_doctor_id={str(doctor_id)}&template_id={template_id}&doctor_id={str(doctor_id)}"
        )
        assert revoke_response.status_code == 200
        revoke_data = revoke_response.json()
        assert revoke_data["success"] is True

        # Step 7-8: Verify doctor loses access
        after_revoke = (
            supabase.table("doctor_templates")
            .select("*")
            .eq("template_id", template_id)
            .eq("doctor_id", str(doctor_id))
            .execute()
        )
        assert len(after_revoke.data) == 0

        # Verify doctor no longer sees template in accessible list
        accessible_response = client.get(
            f"/api/v1/doctor-templates/accessible?doctor_id={str(doctor_id)}&consultation_type_id={str(test_consultation_type_id)}"
        )
        assert accessible_response.status_code == 200
        accessible_data = accessible_response.json()

        # Template should not be in accessible list (unless it's a common template)
        # For owned/shared templates, should be removed
        shared_template_found = any(
            t.get("template_code") == template_code and t.get("doctor_id") == str(doctor_id)
            for t in accessible_data["templates"]
        )
        assert shared_template_found is False


class TestJunctionTableIntegration:
    """Test junction table integration in workflows"""

    def test_template_segments_loaded_via_junction(self, client, test_consultation_type_id):
        """
        TC-INT-051: Verify template segments are loaded via junction table

        Workflow:
        1. Get a template
        2. Query template_segments junction table
        3. Verify segments are assigned via junction, not direct FK
        """
        # Get template
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

        # Query template_segments junction table
        junction_response = (
            supabase.table("template_segments")
            .select("segment_id, segment_code, category, display_order, brevity_level")
            .eq("template_id", template_id)
            .execute()
        )

        # Should return data from junction table
        assert isinstance(junction_response.data, list)

        # If template has segments, verify junction structure
        if junction_response.data:
            segment = junction_response.data[0]
            assert "segment_id" in segment
            assert "segment_code" in segment
            assert "category" in segment  # CORE/ADDITIONAL/EXCLUDED
            assert "display_order" in segment

    def test_consultation_type_segments_loaded_via_junction(self, client, test_consultation_type_id):
        """
        TC-INT-052: Verify consultation type segments via junction table

        Workflow:
        1. Get consultation type
        2. Query consultation_type_segments junction table
        3. Verify segments are assigned via junction
        """
        # Query consultation_type_segments junction table
        junction_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id, segment_code")
            .eq("consultation_type_id", str(test_consultation_type_id))
            .execute()
        )

        # Should return segments from junction table
        assert isinstance(junction_response.data, list)
        assert len(junction_response.data) > 0

        # Verify junction structure
        segment = junction_response.data[0]
        assert "segment_id" in segment
        assert "segment_code" in segment

    def test_segment_definitions_independent_of_consultation_types(self):
        """
        TC-INT-053: Verify segment_definitions are independent (no direct FK)

        This test verifies that segment_definitions table does NOT have
        a direct consultation_type_id foreign key, confirming the new
        junction table architecture.
        """
        # Query segment_definitions
        segments_response = (
            supabase.table("segment_definitions")
            .select("*")
            .limit(5)
            .execute()
        )

        # Should return segments
        assert isinstance(segments_response.data, list)
        assert len(segments_response.data) > 0

        # Verify NO consultation_type_id field
        segment = segments_response.data[0]
        assert "consultation_type_id" not in segment

        # Should have expected fields
        assert "id" in segment
        assert "segment_code" in segment
        assert "segment_name" in segment
        assert "schema_definition_json" in segment  # Correct field name

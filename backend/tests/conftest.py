"""
Pytest Configuration and Fixtures for Backend Testing

This file provides shared fixtures and configuration for all test modules.
"""

import pytest
import sys
import os
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Set TESTING environment variable BEFORE importing app
# This enables auth bypass in the middleware
os.environ["TESTING"] = "true"

from services.supabase_service import supabase
import uuid
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    """
    Create a TestClient for the FastAPI app.

    The TESTING=true environment variable enables auth bypass,
    so requests will be authenticated as test_admin automatically.
    """
    from main import app
    return TestClient(app)


@pytest.fixture(scope="session")
def sharing_doctor_id(test_doctor_id):
    """
    Get a doctor ID to use as the sharing_doctor_id in share requests.

    In real usage, this would be the admin or template owner making the share.
    For tests, we use the same test_doctor_id for simplicity.
    """
    return test_doctor_id


@pytest.fixture(scope="session")
def test_consultation_type_id():
    """Get OP consultation type ID for testing."""
    response = supabase.table("consultation_types").select("id").eq("type_code", "OP").limit(1).execute()
    if response.data:
        return uuid.UUID(response.data[0]["id"])
    raise ValueError("OP consultation type not found in database")


@pytest.fixture(scope="session")
def test_template_id():
    """Get a test template ID (common template with doctor_id = NULL)."""
    response = (
        supabase.table("templates")
        .select("id")
        .is_("doctor_id", "null")
        .limit(1)
        .execute()
    )
    if response.data:
        return uuid.UUID(response.data[0]["id"])
    raise ValueError("No common templates found in database")


@pytest.fixture(scope="session")
def test_segment_codes():
    """Get list of segment codes for testing."""
    response = supabase.table("segment_definitions").select("segment_code").limit(10).execute()
    return [seg["segment_code"] for seg in response.data]


@pytest.fixture(scope="session")
def test_doctor_id():
    """Get Dr. Prakash Kumar's ID from the database for testing."""
    # Use Dr. Prakash Kumar from Guru hospital for consistent testing
    return uuid.UUID("83b3eb65-6801-4bc5-b565-dd3dee2be70a")


@pytest.fixture(scope="session")
def test_doctor_ids():
    """Get multiple real doctor IDs from the database for testing."""
    response = supabase.table("doctors").select("id").eq("is_active", True).limit(5).execute()
    if response.data and len(response.data) >= 3:
        return [uuid.UUID(d["id"]) for d in response.data[:3]]
    raise ValueError("Need at least 3 active doctors in database for testing.")


@pytest.fixture(scope="function")
def cleanup_test_data():
    """
    Fixture to cleanup test data after each test.

    Usage:
        def test_something(cleanup_test_data):
            cleanup_test_data.append(("table_name", "id", test_id))
    """
    cleanup_list = []

    yield cleanup_list

    # Cleanup after test
    for table_name, id_column, record_id in cleanup_list:
        try:
            supabase.table(table_name).delete().eq(id_column, str(record_id)).execute()
        except Exception as e:
            print(f"Warning: Failed to cleanup {table_name} record {record_id}: {e}")


@pytest.fixture(scope="function")
def clean_doctor_templates(test_doctor_id, test_template_id):
    """
    Fixture to cleanup doctor_templates records before and after test.

    Ensures clean state for tests that use test_doctor_id and test_template_id.
    """
    # Cleanup before test
    try:
        supabase.table("doctor_templates").delete().eq("doctor_id", str(test_doctor_id)).execute()
    except Exception as e:
        print(f"Warning: Pre-test cleanup failed: {e}")

    yield

    # Cleanup after test
    try:
        supabase.table("doctor_templates").delete().eq("doctor_id", str(test_doctor_id)).execute()
    except Exception as e:
        print(f"Warning: Post-test cleanup failed: {e}")


@pytest.fixture(scope="session")
def sample_segment_schema():
    """Sample JSON schema for custom segment testing."""
    return {
        "type": "object",
        "properties": {
            "field1": {"type": "string", "description": "Test field 1"},
            "field2": {"type": "number", "description": "Test field 2"},
            "field3": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Test array field"
            }
        },
        "required": ["field1"]
    }


@pytest.fixture(scope="session")
def sample_transcript():
    """Sample medical transcript for testing extraction."""
    return """
    Doctor: Hello, how can I help you today?
    Patient: I've been having headaches for the past 2 days.
    Doctor: Can you describe the pain?
    Patient: It's a throbbing pain on the right side of my head.
    Doctor: Any nausea or vomiting?
    Patient: Yes, I felt nauseous this morning.
    Doctor: Okay, let me check your blood pressure. It's 140/90, which is slightly elevated.
    Doctor: I'm diagnosing this as migraine. I'll prescribe you some medication.
    Doctor: Take Ibuprofen 400mg twice daily for 5 days.
    Doctor: Please come back if symptoms worsen or don't improve in 3 days.
    """


def pytest_configure(config):
    """Pytest configuration hook."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )

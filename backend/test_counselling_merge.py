"""
Unit tests for the schema-driven counselling merge re-wire.

Covers the pure, domain-agnostic pieces that power both the continuation auto-merge and the
manual /extractions/merge endpoint:
  - merge_metadata_service.derive_merge_metadata  (schema -> merge metadata)
  - extraction_service._deep_merge_object / _union_string_list / _is_scalar_list
  - extraction_service._get_item_name / _is_merge_list_key / _extract_list_segments
    (schema-driven via the _merge_meta_ctx ContextVar)

No DB or LLM needed — schemas are provided as fixtures.

Run: cd backend && source venv/bin/activate && pytest test_counselling_merge.py -v
"""

import pytest

from services.merge_metadata_service import derive_merge_metadata
from services import extraction_service as es


# Representative counselling segment schemas (shape verified against the dev DB).
COUNSELLING_SCHEMA = {
    "type": "object",
    "properties": {
        "keyFacts": {"type": "array", "items": {"type": "string"}},
        "tasks": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "task_name": {"type": "string"},
                "end_date": {"type": "string"},
                "start_date": {"type": "string"},
            }},
        },
        "supercurricularActivities": {"type": "object", "properties": {
            "Planned Activities": {"type": "object", "properties": {
                "Activities": {"type": "array", "items": {"type": "string"}},
                "Summer Programs To Start": {"type": "string"},
            }},
        }},
        "assessmentMeters": {"type": "object", "properties": {
            "Student Anxiety Levels": {"type": "object", "properties": {
                "Pre-Session Anxiety": {"type": "string"},
                "Post-Session Anxiety": {"type": "string"},
            }},
        }},
        "nextSteps": {"type": "object", "properties": {
            "Date": {"type": "string"},
            "Books": {"type": "array", "items": {"type": "string"}},
        }},
        "counsellorRemarks": {"type": "string"},
    },
}


# --------------------------------------------------------------------------------------
# derive_merge_metadata
# --------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def meta():
    return derive_merge_metadata(COUNSELLING_SCHEMA)


def test_keyfacts_is_scalar_list(meta):
    m = meta["keyFacts"]
    assert m.is_list and m.item_is_scalar and m.item_identity_field is None


def test_tasks_identity_is_task_name(meta):
    m = meta["tasks"]
    assert m.is_list and m.item_is_scalar is False and m.item_identity_field == "task_name"


def test_supercurricular_nested_array_paths(meta):
    m = meta["supercurricularActivities"]
    assert m.is_object
    assert ("Planned Activities", "Activities") in m.nested_array_paths


def test_assessment_meters_is_scalar_object(meta):
    m = meta["assessmentMeters"]
    assert m.is_object and m.is_scalar_object and m.nested_array_paths == []


def test_next_steps_mixed_shape(meta):
    m = meta["nextSteps"]
    assert m.is_object and not m.is_scalar_object
    assert ("Books",) in m.nested_array_paths


def test_counsellor_remarks_is_free_string(meta):
    assert meta["counsellorRemarks"].is_free_string


def test_malformed_schema_returns_empty():
    assert derive_merge_metadata(None) == {}
    assert derive_merge_metadata({"type": "object"}) == {}


# --------------------------------------------------------------------------------------
# _union_string_list / _is_scalar_list
# --------------------------------------------------------------------------------------

def test_union_preserves_current_first_then_parent_extras():
    assert es._union_string_list(["A", "B"], ["b", "C"]) == ["b", "C", "A"]


def test_union_keeps_status_prefixed_items_distinct():
    assert es._union_string_list(["Ongoing: X"], ["Completed: X"]) == ["Completed: X", "Ongoing: X"]


def test_is_scalar_list():
    assert es._is_scalar_list(["a", 1, True])
    assert es._is_scalar_list([])
    assert not es._is_scalar_list([{"a": 1}])


# --------------------------------------------------------------------------------------
# _deep_merge_object  (the continuation safety-net deep merge)
# --------------------------------------------------------------------------------------

def test_deep_merge_unions_nested_arrays_and_latest_wins_scalars():
    parent = {
        "Planned Activities": {"Activities": ["Robotics", "Debate"], "Summer": "NASA"},
        "Anx": {"Pre": "5", "Post": "5"},
    }
    current = {
        "Planned Activities": {"Activities": ["Maths Olympiad"]},
        "Anx": {"Post": "3"},
    }
    merged = es._deep_merge_object(parent, current, set())
    # nested array unioned (no drop), current first
    assert merged["Planned Activities"]["Activities"] == ["Maths Olympiad", "Robotics", "Debate"]
    # empty-in-current scalar inherits parent
    assert merged["Planned Activities"]["Summer"] == "NASA"
    # parent-only key retained
    assert merged["Anx"]["Pre"] == "5"
    # current scalar wins (latest)
    assert merged["Anx"]["Post"] == "3"


def test_deep_merge_object_list_of_objects_current_wins():
    parent = {"items": [{"id": 1}]}
    current = {"items": [{"id": 2}]}
    merged = es._deep_merge_object(parent, current, set())
    assert merged["items"] == [{"id": 2}]  # object-lists are not blindly unioned


# --------------------------------------------------------------------------------------
# schema-driven helpers via the ContextVar
# --------------------------------------------------------------------------------------

@pytest.fixture
def meta_ctx(meta):
    token = es._merge_meta_ctx.set(meta)
    yield
    es._merge_meta_ctx.reset(token)


def test_get_item_name_uses_identity_field(meta_ctx):
    assert es._get_item_name({"task_name": "Essay", "x": 1}, "tasks") == "Essay"


def test_get_item_name_string_item(meta_ctx):
    assert es._get_item_name("A fact", "keyFacts") == "A fact"


def test_is_merge_list_key_schema_driven(meta_ctx):
    assert es._is_merge_list_key("tasks")
    assert es._is_merge_list_key("keyFacts")
    assert not es._is_merge_list_key("counsellorRemarks")


def test_extract_list_segments_only_lists(meta_ctx):
    data = {"tasks": [{"task_name": "A"}], "keyFacts": ["f"], "counsellorRemarks": "x", "assessmentMeters": {"a": 1}}
    assert set(es._extract_list_segments(data).keys()) == {"tasks", "keyFacts"}


def test_medical_fallback_without_meta():
    # No ContextVar set → falls back to the static medical list keys (main branch safety).
    assert es._is_merge_list_key("prescription")
    assert not es._is_merge_list_key("tasks")

"""
Unit tests for gap_analysis_service.

Key invariant: for the four legacy segments (vitals, nutritionalScreening,
allergy, comorbidities) with the seeded field lists, analyse_segment must
produce the exact same dict shape that the old _check_flat_segment /
_check_comorbidities helpers produced — byte-for-byte — so the public
extraction-gaps API stays backward-compatible for the external webapp.
"""
import sys
from pathlib import Path

# Ensure backend on path even if conftest isn't loaded
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.gap_analysis_service import (
    analyse_segment,
    classify_segment_shape,
    default_leaves_for_shape,
    walk_schema_leaves,
)
from routers.ehr_integration import (
    _check_flat_segment,
    _check_comorbidities,
    _VITALS_FIELDS,
    _NUTRITIONAL_FIELDS,
    _ALLERGY_FIELDS,
    _COMORBIDITY_KEYS,
    _COMORBIDITY_WITH_SINCE,
)


# ----------------------------- walk_schema_leaves -----------------------------

def test_walk_schema_leaves_flat():
    schema = {
        "type": "object",
        "properties": {
            "spo2": {"type": "string"},
            "pulse": {"type": "string"},
            "blood_pressure": {"type": "string"},
        },
    }
    assert set(walk_schema_leaves(schema)) == {"spo2", "pulse", "blood_pressure"}


def test_walk_schema_leaves_nested_presence():
    schema = {
        "type": "object",
        "properties": {
            "pnd": {
                "type": "object",
                "properties": {
                    "present": {"type": "string"},
                    "duration": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
    }
    assert set(walk_schema_leaves(schema)) == {
        "pnd.present", "pnd.duration", "pnd.description"
    }


def test_walk_schema_leaves_comorbidity():
    schema = {
        "type": "object",
        "properties": {
            "dm": {
                "type": "object",
                "properties": {"status": {"type": "string"}, "since": {"type": "string"}},
            },
            "smoking": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
            },
        },
    }
    assert set(walk_schema_leaves(schema)) == {
        "dm.status", "dm.since", "smoking.status"
    }


def test_walk_schema_leaves_skips_array():
    schema = {
        "type": "object",
        "properties": {
            "diagnoses": {"type": "array", "items": {"type": "object"}},
        },
    }
    assert walk_schema_leaves(schema) == ["diagnoses"]  # root path only


# --------------------------- classify_segment_shape ---------------------------

def test_classify_flat_vitals():
    schema = {
        "type": "object",
        "properties": {k: {"type": "string"} for k in _VITALS_FIELDS},
    }
    assert classify_segment_shape(schema) == "flat"


def test_classify_comorbidity():
    schema = {
        "type": "object",
        "properties": {
            "dm": {"type": "object", "properties": {"status": {"type": "string"}, "since": {"type": "string"}}},
            "ht": {"type": "object", "properties": {"status": {"type": "string"}, "since": {"type": "string"}}},
            "smoking": {"type": "object", "properties": {"status": {"type": "string"}}},
        },
    }
    assert classify_segment_shape(schema) == "comorbidity"


def test_classify_nested_presence():
    schema = {
        "type": "object",
        "properties": {
            "chest_pain": {"type": "object", "properties": {"present": {"type": "string"}, "duration": {"type": "string"}}},
            "pnd": {"type": "object", "properties": {"present": {"type": "string"}, "description": {"type": "string"}}},
        },
    }
    assert classify_segment_shape(schema) == "nested_presence"


def test_classify_array():
    assert classify_segment_shape({"type": "array", "items": {}}) == "array"


# ------------------------ default_leaves_for_shape ---------------------------

def test_default_leaves_flat_matches_properties():
    schema = {"type": "object", "properties": {"spo2": {}, "pulse": {}}}
    assert set(default_leaves_for_shape("flat", schema)) == {"spo2", "pulse"}


def test_default_leaves_comorbidity_matches_legacy_four():
    # A minimal comorbidity schema with both with-since and status-only entries
    schema = {
        "type": "object",
        "properties": {
            "dm": {"type": "object", "properties": {"status": {}, "since": {}}},
            "smoking": {"type": "object", "properties": {"status": {}}},
        },
    }
    leaves = default_leaves_for_shape("comorbidity", schema)
    assert set(leaves) == {"dm.status", "dm.since", "smoking.status"}


# --------------------------- analyse_segment (legacy parity) ------------------

def _vitals_fixture():
    return {
        "temperature": "",
        "pulse": "80",
        "respiratory_rate": "",
        "blood_pressure": "120/80",
        "spo2": "99",
    }


def test_analyse_flat_matches_legacy_check_flat_segment():
    data = _vitals_fixture()
    legacy = _check_flat_segment(data, _VITALS_FIELDS)
    new = analyse_segment("flat", data, _VITALS_FIELDS)
    assert new == legacy


def test_analyse_nutritional_matches_legacy():
    data = {"height": "170", "weight": "", "bmi": "", "bmi_flag": ""}
    legacy = _check_flat_segment(data, _NUTRITIONAL_FIELDS)
    new = analyse_segment("flat", data, _NUTRITIONAL_FIELDS)
    assert new == legacy


def test_analyse_allergy_matches_legacy():
    data = {"has_allergy": "Yes", "details": ""}
    legacy = _check_flat_segment(data, _ALLERGY_FIELDS)
    new = analyse_segment("flat", data, _ALLERGY_FIELDS)
    assert new == legacy


def _comorbidity_fixture():
    # DM: Yes but missing since => partial
    # HT: No (captured, not partial)
    # DLP: empty status => missing
    # smoking: "Current" => captured
    # previous_mi: "" => missing
    return {
        "dm": {"status": "Yes", "since": ""},
        "ht": {"status": "No"},
        "dlp": {"status": ""},
        "smoking": {"status": "Current"},
        "previous_mi": {"status": ""},
        "previous_stent": {"status": "No"},
        "renal_failure": {"status": "No"},
        "history_of_cva": {"status": "No"},
        "peripheral_vascular_disease": {"status": "No"},
        "history_of_copd": {"status": "Yes", "since": "2 years"},
        "tobacco_chewing": {"status": "No"},
        "alcohol_intake": {"status": "Occasional"},
    }


def test_analyse_comorbidity_matches_legacy():
    data = _comorbidity_fixture()
    legacy = _check_comorbidities(data)

    # Build the same leaves list the migration seeds
    leaves = []
    for key in _COMORBIDITY_KEYS:
        leaves.append(f"{key}.status")
        if key in _COMORBIDITY_WITH_SINCE:
            leaves.append(f"{key}.since")

    new = analyse_segment("comorbidity", data, leaves)

    assert new["total_fields"] == legacy["total_fields"]
    assert new["missing_count"] == legacy["missing_count"]
    assert set(new["missing_fields"]) == set(legacy["missing_fields"])
    assert set(new["captured_fields"]) == set(legacy["captured_fields"])
    assert set(new.get("partial_fields", [])) == set(legacy.get("partial_fields", []))


# --------------------------- nested_presence semantics -----------------------

def test_analyse_nested_presence_missing_when_empty_present():
    data = {"pnd": {"present": "", "duration": "", "description": ""}}
    out = analyse_segment("nested_presence", data, ["pnd.present"])
    assert out["missing_fields"] == ["pnd"]
    assert out["captured_fields"] == []
    assert out["total_fields"] == 1


def test_analyse_nested_presence_partial_when_yes_and_extra_missing():
    data = {"chest_pain": {"present": "Yes", "duration": "", "description": ""}}
    out = analyse_segment(
        "nested_presence",
        data,
        ["chest_pain.present", "chest_pain.description"],
    )
    assert out["captured_fields"] == ["chest_pain"]
    assert out["partial_fields"] == ["chest_pain"]


def test_analyse_nested_presence_no_partial_when_present_equals_no():
    data = {"chest_pain": {"present": "No", "duration": "", "description": ""}}
    out = analyse_segment(
        "nested_presence",
        data,
        ["chest_pain.present", "chest_pain.description"],
    )
    assert out["captured_fields"] == ["chest_pain"]
    assert out["partial_fields"] == []


# --------------------------- array semantics ---------------------------------

def test_analyse_array_opt_in_missing_when_empty():
    out = analyse_segment("array", [], ["diagnoses"])
    assert out["missing_fields"] == ["diagnoses"]
    assert out["missing_count"] == 1


def test_analyse_array_opt_in_captured_when_populated():
    out = analyse_segment("array", [{"name": "foo"}], ["diagnoses"])
    assert out["captured_fields"] == ["diagnoses"]
    assert out["missing_count"] == 0


def test_analyse_array_no_leaves_means_no_tracking():
    out = analyse_segment("array", [], [])
    assert out["total_fields"] == 0
    assert out["missing_fields"] == []

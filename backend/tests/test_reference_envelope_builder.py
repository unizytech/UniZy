"""Contract test: the envelope builder output MUST match references/updated_meeting_response_structure.json.

This is the anti-drift guard. If anyone changes the envelope shape (renames a field,
drops value/parsedValue, changes a valueType tag, alters the media wrapper), this test
fails. The reference file is the single source of truth for the web app's expected
structure — the builder is asserted against it field-for-field.
"""
from __future__ import annotations

import json
import os

from services.reference_envelope_builder import (
    build_reference_envelope,
    build_custom_business_insights,
    applies_to_template,
    envelope_to_keyed,
    _infer_value_type,
    _build_value_field,
)

_REF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "references", "updated_meeting_response_structure.json",
)

# Top-level media-object keys the web app receives.
_EXPECTED_ENVELOPE_KEYS = {
    "id", "name", "mediaType", "mediaFormat", "mediaSize", "storagePath",
    "status", "metadata", "transcription", "customBusinessInsights",
}
# Keys every customBusinessInsights item must carry.
_EXPECTED_ITEM_KEYS = {
    "id", "mediaId", "key", "label", "ordinal", "valueType",
    "value", "parsedValue", "enabled",
}


def _load_reference() -> dict:
    with open(_REF_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _seq_ids():
    """Deterministic id factory so assertions are stable."""
    counter = {"n": 0}

    def factory() -> str:
        counter["n"] += 1
        return f"id-{counter['n']:04d}"

    return factory


# ---------------------------------------------------------------------------
# valueType / value-field unit checks (the bits most likely to silently drift)
# ---------------------------------------------------------------------------

def test_template_gate_career_prefix_only():
    # career_* templates get the envelope...
    assert applies_to_template("CAREER_DISCUSSION") is True
    assert applies_to_template("career_discussion") is True
    assert applies_to_template("CAREER_PLANNING") is True
    # ...everything else keeps the keyed-insights shape.
    assert applies_to_template("RADIOLOGY") is False
    assert applies_to_template("PSYCHOLOGY") is False
    assert applies_to_template("OP_DISCHARGE") is False
    assert applies_to_template(None) is False
    assert applies_to_template("") is False


def test_media_format_and_transcript_populated():
    from services.reference_envelope_builder import build_envelope_for_extraction, _format_from_mime
    assert _format_from_mime("audio/mpeg") == "MP3"
    assert _format_from_mime("audio/webm;codecs=opus") == "WEBM"
    assert _format_from_mime("mp3") == "MP3"
    assert _format_from_mime(None) == ""
    # media_format + transcript flow into the envelope wrapper (no DB; explicit args)
    env = build_envelope_for_extraction(
        {"participants": {"a": 1}}, media_id="m1",
        transcript="hello world", media_format="audio/mpeg",
        id_factory=_seq_ids(),
    )
    assert env["mediaFormat"] == "MP3"
    assert env["transcription"]["originalTranscription"] == "hello world"


def test_value_type_inference():
    assert _infer_value_type({"a": 1}) == "OBJECT"
    assert _infer_value_type([{"task_name": "x"}]) == "OBJECT_ARRAY"
    assert _infer_value_type(["a", "b"]) == "STRING_ARRAY"
    assert _infer_value_type("hi") == "STRING"
    assert _infer_value_type(42) == "LONG"
    assert _infer_value_type(True) == "BOOLEAN"


def test_value_field_shapes():
    # OBJECT -> single JSON string element
    v = _build_value_field({"Counselor Name": "Ms. Rao"}, "OBJECT")
    assert v == ['{"Counselor Name": "Ms. Rao"}']
    # STRING_ARRAY -> list of plain strings
    assert _build_value_field(["a", "b"], "STRING_ARRAY") == ["a", "b"]
    # STRING -> single plain-string element
    assert _build_value_field("confident student", "STRING") == ["confident student"]
    # OBJECT_ARRAY -> single JSON string element
    v = _build_value_field([{"task_name": "x"}], "OBJECT_ARRAY")
    assert v == ['[{"task_name": "x"}]']


# ---------------------------------------------------------------------------
# Full envelope structural contract vs the reference file
# ---------------------------------------------------------------------------

def test_envelope_matches_reference_structure():
    ref = _load_reference()

    # Reconstruct the keyed-insights input + segment_meta straight from the
    # reference items, so the builder is exercised on the real key set.
    insights = {}
    segment_meta = {}
    for item in ref["customBusinessInsights"]:
        key = item["key"]
        segment_meta[key] = {
            "label": item["label"],
            "ordinal": item["ordinal"],
            "valueType": item["valueType"],
        }
        # Use parsedValue as the native content where it is shape-consistent;
        # fall back to the stringified value otherwise (the reference sample has
        # a couple of artifact parsedValues that we don't reproduce).
        insights[key] = item.get("parsedValue")

    out = build_reference_envelope(
        insights,
        transcript=ref["transcription"]["originalTranscription"],
        segment_meta=segment_meta,
        media_info={
            "id": ref["id"],
            "name": ref["name"],
            "mediaType": ref["mediaType"],
            "mediaFormat": ref["mediaFormat"],
            "mediaSize": ref["mediaSize"],
            "storagePath": ref["storagePath"],
            "status": ref["status"],
            "mediaDuration": ref["metadata"][0]["value"],
        },
        id_factory=_seq_ids(),
    )

    # 1. Media envelope carries exactly the reference's top-level field set.
    assert set(out.keys()) == _EXPECTED_ENVELOPE_KEYS

    # 2. Media-level scalar fields preserved verbatim.
    for f in ("id", "name", "mediaType", "mediaFormat", "mediaSize", "storagePath", "status"):
        assert out[f] == ref[f], f

    # 3. metadata is an array of {id,key,value,valueType}; mediaDuration present.
    assert isinstance(out["metadata"], list)
    md = {m["key"]: m for m in out["metadata"]}
    assert "mediaDuration" in md
    assert md["mediaDuration"]["valueType"] == "LONG"
    assert md["mediaDuration"]["value"] == str(ref["metadata"][0]["value"])

    # 4. transcription object shape.
    assert set(out["transcription"].keys()) == {
        "id", "mediaId", "originalTranscription", "editedTranscription",
        "originalTimestampedTranscription", "editedTimestampedTranscription",
    }
    assert out["transcription"]["originalTranscription"] == ref["transcription"]["originalTranscription"]

    # 5. customBusinessInsights: same key set, same per-item shape + tags.
    out_by_key = {it["key"]: it for it in out["customBusinessInsights"]}
    ref_by_key = {it["key"]: it for it in ref["customBusinessInsights"]}
    assert set(out_by_key.keys()) == set(ref_by_key.keys())

    for key, ref_item in ref_by_key.items():
        got = out_by_key[key]
        assert set(got.keys()) == _EXPECTED_ITEM_KEYS, key
        assert got["label"] == ref_item["label"], key
        assert got["ordinal"] == ref_item["ordinal"], key
        assert got["valueType"] == ref_item["valueType"], key
        assert got["mediaId"] == out["id"], key
        assert got["enabled"] is True, key
        assert isinstance(got["value"], list), key
        # parsedValue round-trips the native content we fed in.
        assert got["parsedValue"] == insights[key], key


def test_envelope_to_keyed_roundtrip():
    """Edit boundary: envelope -> keyed must recover the original keyed insights."""
    keyed = {
        "participants": {"Student Name": "", "Parent(s) Present": "No"},
        "keyFacts": ["a", "b"],
        "tasks": [{"task_name": "x", "bucket_id": 1}],
        "counselorRemarks": "some remark",
    }
    meta = {
        "participants": {"label": "Participants", "ordinal": 0, "valueType": "OBJECT"},
        "keyFacts": {"label": "Key Facts", "ordinal": 5, "valueType": "STRING_ARRAY"},
        "tasks": {"label": "Tasks", "ordinal": 65, "valueType": "OBJECT_ARRAY"},
        "counselorRemarks": {"label": "Remarks", "ordinal": 100, "valueType": "STRING"},
    }
    env = build_reference_envelope(keyed, segment_meta=meta, media_info={"id": "m1"}, id_factory=_seq_ids())
    back = envelope_to_keyed(env)
    assert back == keyed


def test_envelope_to_keyed_is_idempotent_on_keyed_input():
    keyed = {"participants": {"a": 1}, "keyFacts": ["x"]}
    # Already-keyed input (no customBusinessInsights) is returned unchanged.
    assert envelope_to_keyed(keyed) == keyed


def test_envelope_to_keyed_falls_back_to_value_when_no_parsedvalue():
    env = {"customBusinessInsights": [
        {"key": "participants", "valueType": "OBJECT", "value": ['{"Name": "A"}']},
        {"key": "keyFacts", "valueType": "STRING_ARRAY", "value": ["f1", "f2"]},
        {"key": "counselorRemarks", "valueType": "STRING", "value": ["hi"]},
    ]}
    assert envelope_to_keyed(env) == {
        "participants": {"Name": "A"},
        "keyFacts": ["f1", "f2"],
        "counselorRemarks": "hi",
    }


def test_items_sorted_by_ordinal():
    insights = {"counselorRemarks": "x", "participants": {"a": 1}, "keyFacts": ["f"]}
    meta = {
        "counselorRemarks": {"label": "Remarks", "ordinal": 100, "valueType": "STRING"},
        "participants": {"label": "Participants", "ordinal": 0, "valueType": "OBJECT"},
        "keyFacts": {"label": "Key Facts", "ordinal": 5, "valueType": "STRING_ARRAY"},
    }
    items = build_custom_business_insights(insights, "media-1", segment_meta=meta, id_factory=_seq_ids())
    assert [it["key"] for it in items] == ["participants", "keyFacts", "counselorRemarks"]

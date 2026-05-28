"""Tests for _build_radiology_continuation_context.

The helper injects a compact prior-visit snapshot (PLAN + toxicity ids) into
the radiology user prompt during continuations. Verifies:
- Gating: only fires for RADIOLOGY + is_continuation + parent_extraction_ids.
- DB lookup is mocked; no live network calls.
- Block contains the prior plan_template_id, additional_phases, modifications,
  and toxicity library_ids in well-formed text.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.segment_registry import _build_radiology_continuation_context  # noqa: E402


def _mock_supabase_response(parent_data: dict):
    """Returns a mocked supabase chain that yields one parent extraction row."""
    row = {"id": "11111111-1111-1111-1111-111111111111", "original_extraction_json": parent_data, "edited_extraction_json": None}

    class _Q:
        def select(self, *a, **kw): return self
        def in_(self, *a, **kw): return self
        def order(self, *a, **kw): return self
        def limit(self, *a, **kw): return self
        def execute(self):
            return SimpleNamespace(data=[row])

    class _T:
        def table(self, *a, **kw): return _Q()

    return _T()


def _full_parent_extraction() -> dict:
    return {
        "PLAN": {
            "plan_template_id": "RC_PLAN_LCRT",
            "rt_intent": "Neoadjuvant",
            "rt_dose_gy": "50.4",
            "rt_fractions": "28",
            "rt_technique": "VMAT/IMRT",
            "additional_phases": ["Brachy 7 Gy x 4 fractions"],
            "patient_specific_modifications": "DIBH for cardiac sparing",
        },
        "TOXICITY": {
            "early_toxicities": [
                {"library_id": "RC_E01", "text": "Fatigue, weight loss..."},
                {"library_id": "RC_E03", "text": "Anorexia..."},
                {"library_id": "RC_E04", "text": "Diarrhea..."},
            ],
            "late_toxicities": [
                {"library_id": "RC_L03", "text": "Bowel changes..."},
                {"library_id": "RC_L10", "text": "Secondary malignancy..."},
            ],
        },
    }


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------

def test_returns_empty_for_non_radiology():
    assert _build_radiology_continuation_context("OP", True, ["x"]) == ""
    assert _build_radiology_continuation_context("DISCHARGE_PSG", True, ["x"]) == ""
    assert _build_radiology_continuation_context(None, True, ["x"]) == ""
    assert _build_radiology_continuation_context("", True, ["x"]) == ""


def test_returns_empty_for_first_visit():
    assert _build_radiology_continuation_context("RADIOLOGY", False, ["x"]) == ""


def test_returns_empty_when_no_parent_ids():
    assert _build_radiology_continuation_context("RADIOLOGY", True, None) == ""
    assert _build_radiology_continuation_context("RADIOLOGY", True, []) == ""


def test_case_insensitive_radiology():
    """Lowercase 'radiology' should also trigger the snapshot."""
    with patch("services.segment_registry.supabase", _mock_supabase_response(_full_parent_extraction())) if False else \
         patch("services.supabase_service.supabase", _mock_supabase_response(_full_parent_extraction())):
        out = _build_radiology_continuation_context("radiology", True, ["pid"])
    assert "RADIOLOGY CONTINUATION SNAPSHOT" in out


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

def test_full_snapshot_contains_all_fields():
    with patch("services.supabase_service.supabase", _mock_supabase_response(_full_parent_extraction())):
        out = _build_radiology_continuation_context("RADIOLOGY", True, ["pid"])
    assert "RADIOLOGY CONTINUATION SNAPSHOT" in out
    assert 'plan_template_id: "RC_PLAN_LCRT"' in out
    assert "Brachy 7 Gy x 4 fractions" in out
    assert "DIBH for cardiac sparing" in out
    assert "RC_E01" in out and "RC_E03" in out and "RC_E04" in out
    assert "RC_L03" in out and "RC_L10" in out
    # Carry-forward instructions present
    assert "RE-EMIT all prior phases" in out
    assert "deliberate swap" in out


def test_partial_snapshot_only_plan_no_toxicity():
    parent = {
        "PLAN": {
            "plan_template_id": "PR_PLAN_MODHYPO_60_20",
            "additional_phases": [],
            "patient_specific_modifications": "",
        },
        "TOXICITY": {"early_toxicities": [], "late_toxicities": []},
    }
    with patch("services.supabase_service.supabase", _mock_supabase_response(parent)):
        out = _build_radiology_continuation_context("RADIOLOGY", True, ["pid"])
    assert 'plan_template_id: "PR_PLAN_MODHYPO_60_20"' in out
    assert "early: []" in out
    assert "late:  []" in out


def test_returns_empty_when_parent_has_nothing_useful():
    """If the parent extraction has no PLAN data and no toxicity ids, skip the
    snapshot entirely — no point bloating the prompt."""
    parent = {"PLAN": {}, "TOXICITY": {}}
    with patch("services.supabase_service.supabase", _mock_supabase_response(parent)):
        out = _build_radiology_continuation_context("RADIOLOGY", True, ["pid"])
    assert out == ""


def test_returns_empty_when_db_returns_no_rows():
    class _EmptyQ:
        def select(self, *a, **kw): return self
        def in_(self, *a, **kw): return self
        def order(self, *a, **kw): return self
        def limit(self, *a, **kw): return self
        def execute(self):
            return SimpleNamespace(data=[])

    class _T:
        def table(self, *a, **kw): return _EmptyQ()

    with patch("services.supabase_service.supabase", _T()):
        out = _build_radiology_continuation_context("RADIOLOGY", True, ["pid"])
    assert out == ""


def test_returns_empty_on_exception():
    """Render bug must never break extraction — fall back to empty snapshot."""
    class _BoomQ:
        def select(self, *a, **kw): return self
        def in_(self, *a, **kw): return self
        def order(self, *a, **kw): return self
        def limit(self, *a, **kw): return self
        def execute(self):
            raise RuntimeError("DB down")

    class _T:
        def table(self, *a, **kw): return _BoomQ()

    with patch("services.supabase_service.supabase", _T()):
        out = _build_radiology_continuation_context("RADIOLOGY", True, ["pid"])
    assert out == ""


def test_snapshot_size_under_2kb_for_typical_input():
    """Prompt-bloat guard: typical snapshot should stay well under 2 KB."""
    with patch("services.supabase_service.supabase", _mock_supabase_response(_full_parent_extraction())):
        out = _build_radiology_continuation_context("RADIOLOGY", True, ["pid"])
    assert len(out) < 2048

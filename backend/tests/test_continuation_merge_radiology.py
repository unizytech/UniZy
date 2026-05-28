"""Tests for radiology-shaped continuation merge.

Covers the three merge enhancements added 2026-04-28:
- Field-by-field merge for dict segments (PLAN, EXAMINATION_<SITE>, RT_CONSIDERATIONS).
- TOXICITY array union by library_id with current-wins semantics.
- Validator routing for toxicity arrays (carry_forward + confirm_removed).
- Radiology gate that skips medicine/investigation/patient-context injection.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.extraction_service import (  # noqa: E402
    _DICT_FIELD_MERGE_KEYS,
    _TOXICITY_KEY,
    _TOXICITY_ARRAY_KEYS,
    _get_item_name,
    _is_segment_empty,
    _lift_toxicity_arrays,
    _merge_dict_fields,
    _merge_toxicity_segment,
    _radiology_site_from_insights,
    _smart_merge_continuation,
    _toxicity_item_id,
    _union_toxicity_array,
)
from services.segment_registry import _should_skip_doctor_lists_and_context  # noqa: E402


# ---------------------------------------------------------------------------
# Constant integrity
# ---------------------------------------------------------------------------

def test_dict_field_merge_keys_cover_all_radiology_dict_segments():
    expected = {
        "PLAN",
        "EXAMINATION_BREAST", "EXAMINATION_GYN", "EXAMINATION_HN",
        "EXAMINATION_PROSTATE", "EXAMINATION_RECTUM",
        "RT_CONSIDERATIONS",
    }
    assert _DICT_FIELD_MERGE_KEYS == expected


# ---------------------------------------------------------------------------
# _merge_dict_fields
# ---------------------------------------------------------------------------

def test_merge_dict_fields_current_wins_parent_fills_gaps():
    parent = {"rt_intent": "Curative", "rt_dose_gy": "78", "rt_fractions": "39", "rt_technique": "VMAT"}
    current = {"rt_dose_gy": "60", "rt_fractions": "20"}  # doctor refined dose/fractions only
    merged = _merge_dict_fields(parent, current)
    assert merged["rt_dose_gy"] == "60"        # current wins
    assert merged["rt_fractions"] == "20"
    assert merged["rt_intent"] == "Curative"   # parent fills
    assert merged["rt_technique"] == "VMAT"


def test_merge_dict_fields_treats_empty_string_as_gap():
    parent = {"a": "x", "b": "y"}
    current = {"a": "", "b": "Y2"}
    merged = _merge_dict_fields(parent, current)
    assert merged["a"] == "x"   # current's empty got filled by parent
    assert merged["b"] == "Y2"  # current wins


def test_merge_dict_fields_handles_non_dict_inputs():
    assert _merge_dict_fields(None, {"a": 1}) == {"a": 1}
    assert _merge_dict_fields({"a": 1}, None) == {"a": 1}
    assert _merge_dict_fields(None, None) == {}


# ---------------------------------------------------------------------------
# Toxicity union
# ---------------------------------------------------------------------------

def test_toxicity_item_id_uses_library_id():
    assert _toxicity_item_id({"library_id": "RC_E03", "text": "x"}) == "id:RC_E03"


def test_toxicity_item_id_falls_back_to_text():
    assert _toxicity_item_id({"library_id": "", "text": "Hello World"}).startswith("text:hello world")


def test_union_toxicity_array_dedupes_by_library_id_current_wins():
    parent = [
        {"library_id": "RC_E01", "text": "PARENT v1"},
        {"library_id": "RC_E04", "text": "Diarrhea"},
    ]
    current = [
        {"library_id": "RC_E01", "text": "CURRENT v2"},  # same id; current wins
        {"library_id": "RC_E07", "text": "Cytopenia"},   # new
    ]
    result = _union_toxicity_array(parent, current)
    by_id = {it["library_id"]: it["text"] for it in result}
    assert by_id["RC_E01"] == "CURRENT v2"
    assert by_id["RC_E04"] == "Diarrhea"
    assert by_id["RC_E07"] == "Cytopenia"
    assert len(result) == 3


def test_union_toxicity_array_drops_removed_ids():
    parent = [{"library_id": "RC_E01", "text": "x"}, {"library_id": "RC_E02", "text": "y"}]
    current = [{"library_id": "RC_E03", "text": "z"}]
    result = _union_toxicity_array(parent, current, removed_ids={"RC_E01"})
    ids = {it["library_id"] for it in result}
    assert "RC_E01" not in ids
    assert ids == {"RC_E02", "RC_E03"}


def test_merge_toxicity_segment_unions_both_arrays():
    parent = {
        "early_toxicities": [{"library_id": "RC_E01", "text": "Fatigue"}, {"library_id": "RC_E04", "text": "Diarrhea"}],
        "late_toxicities": [{"library_id": "RC_L03", "text": "Bowel changes"}],
    }
    current = {
        "early_toxicities": [{"library_id": "RC_E07", "text": "Cytopenia"}],
        "late_toxicities": [],
    }
    merged = _merge_toxicity_segment(parent, current)
    early_ids = {it["library_id"] for it in merged["early_toxicities"]}
    late_ids = {it["library_id"] for it in merged["late_toxicities"]}
    assert early_ids == {"RC_E01", "RC_E04", "RC_E07"}
    assert late_ids == {"RC_L03"}


# ---------------------------------------------------------------------------
# _smart_merge_continuation: radiology behaviors
# ---------------------------------------------------------------------------

def _radiology_template_keys() -> set:
    return {
        "PRESENTING_COMPLAINTS", "ASSOCIATED_SYMPTOMS", "PAST_MEDICAL_HISTORY",
        "FAMILY_HISTORY", "SOCIAL_HISTORY", "INVESTIGATION_IMAGING",
        "INVESTIGATIONS_BIOPSY", "INVESTIGATIONS_BLOODWORKS", "INITIAL_OUTSIDE_TREATMENT",
        "RT_CONSIDERATIONS", "COMMON_EXAM", "IMPRESSION_AND_PLAN",
        "DISCUSSION_CONSENT_CLOSING",
        "EXAMINATION_RECTUM", "PLAN", "TOXICITY",
    }


def test_smart_merge_field_by_field_for_plan():
    parent = {
        "PLAN": {
            "plan_template_id": "RC_PLAN_LCRT",
            "rt_intent": "Neoadjuvant",
            "rt_dose_gy": "50.4",
            "rt_fractions": "28",
            "rt_dose_per_fraction_gy": "1.8",
            "rt_weeks": "5.5",
            "rt_technique": "VMAT/IMRT",
            "concurrent_systemic_therapy": "Concurrent capecitabine",
        },
    }
    current = {
        "PLAN": {
            "rt_dose_gy": "45",        # doctor refined dose only
            "rt_fractions": "25",
            "rt_intent": "",
            "rt_technique": "",
        },
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    plan = merged["PLAN"]
    assert plan["rt_dose_gy"] == "45"                                      # current wins
    assert plan["rt_fractions"] == "25"
    assert plan["rt_intent"] == "Neoadjuvant"                              # parent fills
    assert plan["rt_technique"] == "VMAT/IMRT"
    assert plan["plan_template_id"] == "RC_PLAN_LCRT"
    assert plan["concurrent_systemic_therapy"] == "Concurrent capecitabine"


def test_smart_merge_field_by_field_for_rt_considerations():
    parent = {"RT_CONSIDERATIONS": {"pacemaker": "No", "diabetes_or_kidney_disease": "Yes", "previous_radiation_exposure": "No"}}
    current = {"RT_CONSIDERATIONS": {"pacemaker": "Yes"}}  # doctor flagged a new one
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    rt = merged["RT_CONSIDERATIONS"]
    assert rt["pacemaker"] == "Yes"
    assert rt["diabetes_or_kidney_disease"] == "Yes"
    assert rt["previous_radiation_exposure"] == "No"


def test_smart_merge_field_by_field_for_examination_rectum():
    parent = {
        "EXAMINATION_RECTUM": {
            "digital_rectal_exam": "Mass at 5 cm, mobile",
            "inguinal_lymph_node_exam": "No palpable nodes",
            "lower_limb_edema": "No edema",
            "distance_from_anal_verge_cm": "5",
            "circumferential_extent": "1/3 circumference",
        },
    }
    current = {
        "EXAMINATION_RECTUM": {
            "circumferential_extent": "1/2 circumference",  # doctor updated
        },
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    exam = merged["EXAMINATION_RECTUM"]
    assert exam["circumferential_extent"] == "1/2 circumference"
    assert exam["digital_rectal_exam"] == "Mass at 5 cm, mobile"
    assert exam["distance_from_anal_verge_cm"] == "5"


def test_smart_merge_toxicity_union_no_clobber():
    parent = {
        "TOXICITY": {
            "early_toxicities": [
                {"library_id": "RC_E01", "text": "Fatigue"},
                {"library_id": "RC_E03", "text": "Anorexia"},
                {"library_id": "RC_E04", "text": "Diarrhea"},
            ],
            "late_toxicities": [
                {"library_id": "RC_L03", "text": "Bowel changes"},
                {"library_id": "RC_L10", "text": "Secondary malignancy risk"},
            ],
        },
    }
    current = {
        "TOXICITY": {
            "early_toxicities": [{"library_id": "RC_E07", "text": "Cytopenia"}],
            "late_toxicities": [],
        },
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    early_ids = {it["library_id"] for it in merged["TOXICITY"]["early_toxicities"]}
    late_ids = {it["library_id"] for it in merged["TOXICITY"]["late_toxicities"]}
    # All parent items preserved + new current item added
    assert early_ids == {"RC_E01", "RC_E03", "RC_E04", "RC_E07"}
    assert late_ids == {"RC_L03", "RC_L10"}


def test_smart_merge_toxicity_empty_current_carries_parent_wholesale():
    parent = {
        "TOXICITY": {
            "early_toxicities": [{"library_id": "RC_E01", "text": "Fatigue"}],
            "late_toxicities": [{"library_id": "RC_L01", "text": "Skin atrophy"}],
        },
    }
    current = {"TOXICITY": {}}
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    assert merged["TOXICITY"] == parent["TOXICITY"]


# ---------------------------------------------------------------------------
# Validator routing for toxicity
# ---------------------------------------------------------------------------

def test_validator_carry_forward_toxicity_routed_into_array():
    """Validator says 'parent toxicity item missing — re-add it'."""
    parent = {
        "TOXICITY": {
            "early_toxicities": [{"library_id": "RC_E04", "text": "Diarrhea"}],
            "late_toxicities": [],
        },
    }
    current = {
        "TOXICITY": {
            # Current only mentions a different toxicity; would normally trigger union,
            # but if doctor accidentally dropped RC_E04 the validator carries it forward.
            "early_toxicities": [{"library_id": "RC_E07", "text": "Cytopenia"}],
            "late_toxicities": [],
        },
    }
    validator_result = {
        "carry_forward": [
            {
                "segment": "early_toxicities",
                "item": {"library_id": "RC_E04", "text": "Diarrhea"},
                "reason": "Not mentioned in transcript; should continue.",
            }
        ],
        "confirm_removed": [],
        "cross_segment_patches": [],
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=validator_result,
    )
    early_ids = {it["library_id"] for it in merged["TOXICITY"]["early_toxicities"]}
    # Phase 1.6 union already includes RC_E04 from parent; carry_forward is a no-op dedupe here.
    assert early_ids == {"RC_E04", "RC_E07"}


def test_validator_confirm_removed_toxicity_drops_item():
    """Doctor explicitly disclaimed a toxicity — validator confirms removal."""
    parent = {
        "TOXICITY": {
            "early_toxicities": [
                {"library_id": "RC_E03", "text": "Anorexia"},
                {"library_id": "RC_E04", "text": "Diarrhea"},
            ],
            "late_toxicities": [],
        },
    }
    current = {
        "TOXICITY": {
            "early_toxicities": [{"library_id": "RC_E04", "text": "Diarrhea"}],
            "late_toxicities": [],
        },
    }
    validator_result = {
        "carry_forward": [],
        "confirm_removed": [
            {
                "segment": "early_toxicities",
                "item_name": "RC_E03",
                "reason": "Doctor said 'no concerns about anorexia'.",
            }
        ],
        "cross_segment_patches": [],
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=validator_result,
    )
    early_ids = {it["library_id"] for it in merged["TOXICITY"]["early_toxicities"]}
    # Phase 1.6 unioned RC_E03 + RC_E04; Phase 2 confirm_removed strips RC_E03.
    assert early_ids == {"RC_E04"}


# ---------------------------------------------------------------------------
# _lift_toxicity_arrays + _get_item_name for validator visibility
# ---------------------------------------------------------------------------

def test_lift_toxicity_arrays_surfaces_arrays():
    data = {
        "TOXICITY": {
            "early_toxicities": [{"library_id": "RC_E01", "text": "Fatigue"}],
            "late_toxicities": [{"library_id": "RC_L03", "text": "Bowel changes"}],
        },
    }
    target: dict = {}
    _lift_toxicity_arrays(data, target)
    assert "early_toxicities" in target
    assert "late_toxicities" in target
    assert target["early_toxicities"][0]["library_id"] == "RC_E01"


def test_lift_toxicity_arrays_no_op_when_empty():
    target: dict = {}
    _lift_toxicity_arrays({"TOXICITY": {}}, target)
    assert target == {}
    _lift_toxicity_arrays({}, target)
    assert target == {}


def test_get_item_name_uses_library_id_for_toxicity():
    item = {"library_id": "RC_E03", "text": "Anorexia, nausea, and occasional vomiting."}
    assert _get_item_name(item, "early_toxicities") == "RC_E03"
    assert _get_item_name(item, "late_toxicities") == "RC_E03"


def test_get_item_name_falls_back_to_text_for_toxicity():
    item = {"library_id": "", "text": "Doctor-specific item."}
    assert _get_item_name(item, "early_toxicities") == "Doctor-specific item."


# ---------------------------------------------------------------------------
# Radiology prompt-injection gate
# ---------------------------------------------------------------------------

def test_radiology_gate_skips_doctor_lists_and_context():
    assert _should_skip_doctor_lists_and_context("RADIOLOGY") is True
    assert _should_skip_doctor_lists_and_context("radiology") is True  # case-insensitive
    assert _should_skip_doctor_lists_and_context("OP") is False
    assert _should_skip_doctor_lists_and_context("DISCHARGE_PSG") is False
    assert _should_skip_doctor_lists_and_context(None) is False
    assert _should_skip_doctor_lists_and_context("") is False


def test_smart_merge_plan_swap_keeps_current_intact():
    """Doctor switches plan choice (LCRT → TNT). Field-merge would contaminate
    the new plan with the old plan's dose/fractions/technique. Swap detection
    short-circuits that and leaves current PLAN exactly as the LLM emitted it."""
    parent = {
        "PLAN": {
            "plan_template_id": "RC_PLAN_LCRT",
            "rt_intent": "Neoadjuvant",
            "rt_dose_gy": "50.4",
            "rt_fractions": "28",
            "rt_dose_per_fraction_gy": "1.8",
            "rt_weeks": "5.5",
            "rt_technique": "VMAT/IMRT",
            "concurrent_systemic_therapy": "Concurrent capecitabine 825 mg/m2 BD on RT days",
        },
    }
    current = {
        "PLAN": {
            "plan_template_id": "RC_PLAN_TNT",
            "rt_intent": "Neoadjuvant",
            "rt_dose_gy": "50.4",
            "rt_fractions": "28",
            "rt_technique": "VMAT/IMRT",
            "concurrent_systemic_therapy": "Concurrent capecitabine; sequential FOLFOX",
        },
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    # Plan swap: current PLAN preserved as-is, no fields filled from parent.
    assert merged["PLAN"] == current["PLAN"]


def test_smart_merge_plan_swap_with_sparse_current_does_not_inherit_from_parent():
    """Worst case: doctor switched plan but LLM emitted only the new id.
    Without swap detection, parent's dose/fractions would silently bleed in.
    With detection, the sparse current PLAN survives intact."""
    parent = {
        "PLAN": {
            "plan_template_id": "RC_PLAN_LCRT",
            "rt_dose_gy": "50.4",
            "rt_fractions": "28",
            "rt_technique": "VMAT/IMRT",
        },
    }
    current = {"PLAN": {"plan_template_id": "RC_PLAN_TNT"}}
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    assert merged["PLAN"] == {"plan_template_id": "RC_PLAN_TNT"}
    assert "rt_dose_gy" not in merged["PLAN"]
    assert "rt_fractions" not in merged["PLAN"]
    assert "rt_technique" not in merged["PLAN"]


def test_smart_merge_plan_refinement_still_field_merges_when_template_id_unchanged():
    """Same plan_template_id (or current's blank) with sparse fields should
    still field-merge from parent — regression guard for swap detection."""
    parent = {
        "PLAN": {
            "plan_template_id": "RC_PLAN_LCRT",
            "rt_intent": "Neoadjuvant",
            "rt_dose_gy": "50.4",
            "rt_fractions": "28",
            "rt_technique": "VMAT/IMRT",
        },
    }
    current = {
        "PLAN": {
            "plan_template_id": "RC_PLAN_LCRT",  # unchanged
            "rt_dose_gy": "45",                    # doctor refined
        },
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    plan = merged["PLAN"]
    assert plan["rt_dose_gy"] == "45"
    assert plan["rt_fractions"] == "28"
    assert plan["rt_technique"] == "VMAT/IMRT"
    assert plan["rt_intent"] == "Neoadjuvant"


def test_smart_merge_plan_refinement_field_merges_when_current_lacks_template_id():
    """If the current PLAN omits plan_template_id entirely (LLM was sparse),
    swap detection should NOT fire. Field-merge proceeds as usual."""
    parent = {
        "PLAN": {
            "plan_template_id": "RC_PLAN_LCRT",
            "rt_dose_gy": "50.4",
            "rt_fractions": "28",
        },
    }
    current = {"PLAN": {"rt_dose_gy": "45"}}  # no plan_template_id at all
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    plan = merged["PLAN"]
    assert plan["rt_dose_gy"] == "45"
    assert plan["rt_fractions"] == "28"
    assert plan["plan_template_id"] == "RC_PLAN_LCRT"  # parent fills


# ---------------------------------------------------------------------------
# Radiology site detection + cross-site continuation guard
# ---------------------------------------------------------------------------

def test_radiology_site_helper_returns_correct_site():
    assert _radiology_site_from_insights({"EXAMINATION_BREAST": {}}) == "BREAST"
    assert _radiology_site_from_insights({"EXAMINATION_GYN": {}}) == "GYN"
    assert _radiology_site_from_insights({"EXAMINATION_HN": {}}) == "HN"
    assert _radiology_site_from_insights({"EXAMINATION_PROSTATE": {}}) == "PROSTATE"
    assert _radiology_site_from_insights({"EXAMINATION_RECTUM": {}}) == "RECTUM"
    assert _radiology_site_from_insights({"PLAN": {}, "TOXICITY": {}}) is None
    assert _radiology_site_from_insights({"prescription": []}) is None
    assert _radiology_site_from_insights(None) is None
    assert _radiology_site_from_insights("not a dict") is None


def test_smart_merge_skips_cross_site_continuation():
    """Parent RS_BREAST → current RS_PROSTATE should not bleed BR_* toxicity
    library_ids into the prostate consult."""
    parent = {
        "EXAMINATION_BREAST": {"laterality": "Left"},
        "PLAN": {
            "plan_template_id": "BR_PLAN_WB_HYPO_40_15",
            "rt_dose_gy": "40", "rt_fractions": "15", "rt_technique": "VMAT",
        },
        "TOXICITY": {
            "early_toxicities": [
                {"library_id": "BR_E01", "text": "Fatigue (breast)"},
                {"library_id": "BR_SCF_E01", "text": "Odynophagia"},
            ],
            "late_toxicities": [
                {"library_id": "BR_LH_L01", "text": "Cardiac dose risk"},
            ],
        },
        "RT_CONSIDERATIONS": {"pacemaker": "No", "previous_radiation_exposure": "No"},
    }
    current = {
        "EXAMINATION_PROSTATE": {"digital_rectal_exam": "Mass at apex"},
        "PLAN": {
            "plan_template_id": "PR_PLAN_MODHYPO_60_20",
            "rt_dose_gy": "60", "rt_fractions": "20", "rt_technique": "VMAT/IMRT",
        },
        "TOXICITY": {"early_toxicities": [], "late_toxicities": []},
        "RT_CONSIDERATIONS": {"pacemaker": "Yes"},  # different — should NOT be filled by parent
    }
    snapshot = {k: (dict(v) if isinstance(v, dict) else v) for k, v in current.items()}

    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys={"EXAMINATION_PROSTATE", "PLAN", "TOXICITY", "RT_CONSIDERATIONS"},
        validator_result=None,
    )
    # Result equals current input — no merge occurred.
    assert merged["EXAMINATION_PROSTATE"] == snapshot["EXAMINATION_PROSTATE"]
    assert merged["PLAN"] == snapshot["PLAN"]
    assert merged["TOXICITY"]["early_toxicities"] == []
    assert merged["TOXICITY"]["late_toxicities"] == []
    assert merged["RT_CONSIDERATIONS"] == snapshot["RT_CONSIDERATIONS"]
    # Most importantly — no breast toxicity ids leaked.
    breast_ids = {"BR_E01", "BR_SCF_E01", "BR_LH_L01"}
    flat_ids = {it.get("library_id") for arr in (merged["TOXICITY"]["early_toxicities"], merged["TOXICITY"]["late_toxicities"]) for it in arr}
    assert flat_ids.isdisjoint(breast_ids)
    # Parent's breast exam never lands in current.
    assert "EXAMINATION_BREAST" not in merged


def test_smart_merge_proceeds_when_both_sides_same_site():
    """Same-site continuation should still field-merge / union normally —
    regression guard for the cross-site short-circuit."""
    parent = {
        "EXAMINATION_RECTUM": {"digital_rectal_exam": "Mass at 5 cm", "circumferential_extent": "1/3"},
        "PLAN": {"plan_template_id": "RC_PLAN_LCRT", "rt_dose_gy": "50.4", "rt_fractions": "28", "rt_technique": "VMAT"},
        "TOXICITY": {"early_toxicities": [{"library_id": "RC_E01", "text": "Fatigue"}], "late_toxicities": []},
    }
    current = {
        "EXAMINATION_RECTUM": {"circumferential_extent": "1/2"},  # doctor refined
        "PLAN": {"plan_template_id": "RC_PLAN_LCRT", "rt_dose_gy": "45"},  # refinement
        "TOXICITY": {"early_toxicities": [], "late_toxicities": []},
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    # Field-merge worked
    assert merged["EXAMINATION_RECTUM"]["circumferential_extent"] == "1/2"
    assert merged["EXAMINATION_RECTUM"]["digital_rectal_exam"] == "Mass at 5 cm"
    assert merged["PLAN"]["rt_dose_gy"] == "45"
    assert merged["PLAN"]["rt_fractions"] == "28"
    # Toxicity union'd
    early_ids = {it["library_id"] for it in merged["TOXICITY"]["early_toxicities"]}
    assert "RC_E01" in early_ids


def test_smart_merge_proceeds_when_one_side_missing_site_marker():
    """If the LLM didn't emit any EXAMINATION_<SITE> on current (sparse), the
    cross-site guard cannot fire and the merge should proceed normally."""
    parent = {
        "EXAMINATION_RECTUM": {"digital_rectal_exam": "Mass"},
        "PLAN": {"plan_template_id": "RC_PLAN_LCRT", "rt_dose_gy": "50.4"},
    }
    current = {
        # No EXAMINATION_<SITE> at all
        "PLAN": {"plan_template_id": "RC_PLAN_LCRT", "rt_dose_gy": "45"},
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys={"PLAN", "EXAMINATION_RECTUM"},
        validator_result=None,
    )
    # Field-merge proceeded
    assert merged["PLAN"]["rt_dose_gy"] == "45"
    # Parent's EXAMINATION_RECTUM was carried wholesale (Phase 1 wholesale-copy)
    assert merged["EXAMINATION_RECTUM"]["digital_rectal_exam"] == "Mass"


# ---------------------------------------------------------------------------
# Validator add_to_examination patch routing for radiology
# ---------------------------------------------------------------------------

def test_validator_add_to_examination_lands_in_radiology_exam():
    """Validator emits add_to_examination patch — for a radiology current,
    the entry should land in EXAMINATION_<SITE>, not in some unrelated key."""
    parent = {
        "EXAMINATION_RECTUM": {"digital_rectal_exam": "Mass"},
        "investigations": [{"name": "MRI pelvis"}],
    }
    current = {
        "EXAMINATION_RECTUM": {"digital_rectal_exam": "Mass, mobile"},  # non-empty dict
        "investigations": [{"name": "MRI pelvis"}],
    }
    validator_result = {
        "carry_forward": [],
        "confirm_removed": [
            {"segment": "investigations", "item_name": "MRI pelvis",
             "reason": "Results discussed in transcript"},
        ],
        "cross_segment_patches": [
            {
                "type": "investigation_result",
                "segment": "examination",                # validator's generic name
                "action": "add_to_examination",
                "item": {"name": "MRI pelvis", "value": "T3 mid rectum, threatening MRF"},
                "reason": "MRI results reviewed in transcript",
            },
        ],
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys={"EXAMINATION_RECTUM", "investigations"},
        validator_result=validator_result,
    )
    exam = merged["EXAMINATION_RECTUM"]
    # Patch landed in the radiology exam dict via the investigation_results key
    # (the dict-shape branch's last-resort fallback).
    serialized = " ".join(str(v) for v in exam.values())
    assert "MRI pelvis" in serialized
    assert "T3 mid rectum" in serialized


# ---------------------------------------------------------------------------
# Conditional toxicity removal via validator (locks the contract)
# ---------------------------------------------------------------------------

def test_conditional_toxicity_removal_via_validator():
    """Doctor disclaims brachytherapy — validator confirms removal of GY_BR_*.
    Without the validator, our toxicity union would re-add them from parent.
    With confirm_removed routing, they get dropped after the union."""
    parent = {
        "EXAMINATION_GYN": {"per_vaginal_exam": "Cervix involvement"},
        "TOXICITY": {
            "early_toxicities": [
                {"library_id": "GY_E01", "text": "Fatigue"},
                {"library_id": "GY_BR_E01", "text": "Brachy under anaesthesia"},
                {"library_id": "GY_BR_E02", "text": "Brachy infection risk"},
            ],
            "late_toxicities": [],
        },
    }
    current = {
        "EXAMINATION_GYN": {"per_vaginal_exam": "Cervix involvement"},
        "TOXICITY": {
            # Doctor said "skipping brachy" — LLM omitted GY_BR_*
            "early_toxicities": [{"library_id": "GY_E01", "text": "Fatigue"}],
            "late_toxicities": [],
        },
    }
    validator_result = {
        "carry_forward": [],
        "confirm_removed": [
            {"segment": "early_toxicities", "item_name": "GY_BR_E01",
             "reason": "Doctor said 'skipping brachy this round'"},
            {"segment": "early_toxicities", "item_name": "GY_BR_E02",
             "reason": "Doctor said 'skipping brachy this round'"},
        ],
        "cross_segment_patches": [],
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys={"EXAMINATION_GYN", "TOXICITY"},
        validator_result=validator_result,
    )
    early_ids = {it["library_id"] for it in merged["TOXICITY"]["early_toxicities"]}
    assert "GY_E01" in early_ids
    assert "GY_BR_E01" not in early_ids
    assert "GY_BR_E02" not in early_ids


def test_smart_merge_does_not_clobber_consult_letter_or_standard_texts():
    """Letter render runs AFTER merge; merge should not interfere with later attachment."""
    parent = {
        "TOXICITY": {"early_toxicities": [{"library_id": "RC_E01", "text": "Fatigue"}], "late_toxicities": []},
        "consult_letter": "Old letter from parent — should NOT carry forward",
        "standard_texts": {"CLOSING": "old"},
    }
    current = {
        "TOXICITY": {"early_toxicities": [], "late_toxicities": []},
    }
    merged = _smart_merge_continuation(
        current, parent,
        current_template_keys=_radiology_template_keys(),
        validator_result=None,
    )
    # Letter / standard_texts are NOT in current_template_keys; should be skipped.
    assert "consult_letter" not in merged
    assert "standard_texts" not in merged

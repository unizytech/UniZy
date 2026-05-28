"""End-to-end tests for letter_render_service.

Hits the live Supabase main-dev instance (read-only) since the layouts and
standard texts live there. Tests verify:
- Standard text fragments resolve patient + plan placeholders correctly.
- The full Jinja layout renders with greetings, plan lines, toxicity bullets,
  and closing in the expected order.
- Empty fields collapse cleanly (no orphan labels).
- Conditional toxicity items (BR_SCF_*, BR_LH_*, GY_BR_*) only appear when the
  toxicity arrays include them — the renderer just iterates whatever is
  passed; condition logic is the LLM's job.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import letter_render_service as svc  # noqa: E402
from services.supabase_service import supabase  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RADIOLOGY_TEMPLATE_CODES = ("RS_RECTUM", "RS_PROSTATE", "RS_HN", "RS_GYN", "RS_BREAST")


@pytest.fixture(scope="module")
def template_ids() -> dict:
    rows = (
        supabase.table("templates")
        .select("id, template_code")
        .in_("template_code", list(RADIOLOGY_TEMPLATE_CODES))
        .execute()
        .data
        or []
    )
    return {r["template_code"]: uuid.UUID(r["id"]) for r in rows}


def _patient_male():
    return {"full_name": "John Doe", "gender": "Male", "date_of_birth": "1965-01-15"}


def _patient_female():
    return {"full_name": "Jane Smith", "gender": "Female", "date_of_birth": "1970-06-01"}


def _rectum_insights():
    return {
        "PRESENTING_COMPLAINTS": {"presenting_complaints": "Bleeding per rectum × 4 weeks."},
        "ASSOCIATED_SYMPTOMS": {"associated_symptoms": "Tenesmus, urgency."},
        "PAST_MEDICAL_HISTORY": {"comorbidities": "Type 2 DM."},
        "FAMILY_HISTORY": {"family_history": "Father - colon cancer at 70."},
        "INVESTIGATION_IMAGING": {"imaging": ["MRI pelvis: T3N1 mid rectum"]},
        "INVESTIGATIONS_BIOPSY": {"biopsy_details": "Adenocarcinoma, moderately differentiated."},
        "INVESTIGATIONS_BLOODWORKS": {
            "hb_g_dl": "11.2",
            "platelets_lakhs_mm3": "2.4",
            "creatinine_mg_dl": "0.9",
        },
        "RT_CONSIDERATIONS": {
            "pacemaker": "No",
            "connective_tissue_disorder": "No",
            "previous_radiation_exposure": "No",
            "contrast_allergy_ct_mri": "No",
            "mr_contraindication": "No",
            "diabetes_or_kidney_disease": "Yes",
        },
        "EXAMINATION_RECTUM": {
            "digital_rectal_exam": "Mass at 5 cm from anal verge, mobile.",
            "inguinal_lymph_node_exam": "No palpable inguinal lymphadenopathy bilaterally.",
            "lower_limb_edema": "No lower limb edema.",
            "distance_from_anal_verge_cm": "5",
            "circumferential_extent": "1/3 circumference",
        },
        "IMPRESSION_AND_PLAN": {
            "impression": "Locally advanced rectal cancer, cT3N1.",
            "cancer_staging": "cT3N1M0",
            "discussion_summary": "Discussed long-course CRT.",
        },
        "PLAN": {
            "plan_template_id": "RC_PLAN_LCRT",
            "rt_intent": "Neoadjuvant",
            "rt_dose_gy": "50.4",
            "rt_fractions": "28",
            "rt_dose_per_fraction_gy": "1.8",
            "rt_weeks": "5.5",
            "rt_technique": "VMAT/IMRT",
            "concurrent_systemic_therapy": "Concurrent capecitabine 825 mg/m2 BD on RT days",
            "additional_phases": [],
            "patient_specific_modifications": "",
        },
        "TOXICITY": {
            "early_toxicities": [
                {"library_id": "RC_E01", "text": "Fatigue, weight loss, and discomfort or pain at the site of radiation."},
                {"library_id": "RC_E04", "text": "Abdominal distension, change in bowel habits, loose stools, and diarrhea."},
            ],
            "late_toxicities": [
                {"library_id": "RC_L03", "text": "Chronic changes in bowel movement, intermittent diarrhea, cramps, colic, and bloating."},
                {"library_id": "RC_L10", "text": "Small but real risk of radiation-induced secondary malignancy."},
            ],
        },
        "REFERRAL_DETAILS": {"referred_by": "Smith"},
        "DIAGNOSIS": [{"name": "Rectal adenocarcinoma", "type": "Primary", "code": "C20"}],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_honorific_from_sex():
    assert svc._derive_honorific("Male") == "Mr."
    assert svc._derive_honorific("Female") == "Mrs."
    assert svc._derive_honorific("") == ""
    assert svc._derive_honorific(None) == ""


def test_compute_age_from_dob():
    age = svc._compute_age("1990-04-28")
    assert age and int(age) >= 35


def test_flatten_insights_promotes_subfields():
    flat = svc._flatten_insights(_rectum_insights())
    assert flat["rt_dose_gy"] == "50.4"
    assert flat["pacemaker"] == "No"
    assert flat["digital_rectal_exam"].startswith("Mass at 5")
    # Segment-keyed access still works
    assert flat["TOXICITY"]["early_toxicities"][0]["text"].startswith("Fatigue")


def test_flatten_insights_aliases_camelcase_scalars():
    """LLM emits single-field segments as camelCase scalars (not dicts).

    Layouts reference snake_case, so the flattener must alias both directions.
    Regression test for the bug where {{ presenting_complaints }} rendered
    empty even though the data was captured under `presentingComplaints`.
    """
    insights = {
        "presentingComplaints": "Bleeding per rectum × 4 weeks.",
        "associatedSymptoms": "Tenesmus, urgency.",
        "familyHistory": "Father - colon cancer at 70.",
        "socialHistory": "Non-smoker.",
        "pastMedicalHistory": {"comorbidities": "DM", "allergies": [], "current_medications": []},
    }
    flat = svc._flatten_insights(insights)
    assert flat["presenting_complaints"] == "Bleeding per rectum × 4 weeks."
    assert flat["associated_symptoms"] == "Tenesmus, urgency."
    assert flat["family_history"] == "Father - colon cancer at 70."
    assert flat["social_history"] == "Non-smoker."
    # Dict-valued segments still spread their inner snake_case keys
    assert flat["comorbidities"] == "DM"
    # Original camelCase keys preserved alongside aliases
    assert flat["presentingComplaints"] == "Bleeding per rectum × 4 weeks."


def test_camel_to_snake_handles_both_shapes():
    assert svc._camel_to_snake("presentingComplaints") == "presenting_complaints"
    assert svc._camel_to_snake("PRESENTING_COMPLAINTS") == "presenting_complaints"
    assert svc._camel_to_snake("rtConsiderations") == "rt_considerations"
    assert svc._camel_to_snake("already_snake") == "already_snake"


def test_primary_diagnosis_extraction():
    assert svc._primary_diagnosis(_rectum_insights()) == "Rectal adenocarcinoma"


def test_referring_doctor_extraction():
    assert svc._referring_doctor(_rectum_insights()) == "Smith"


# ---------------------------------------------------------------------------
# Standard-text resolution (live DB read)
# ---------------------------------------------------------------------------

def test_resolve_standard_texts_fills_placeholders(template_ids):
    tid = template_ids["RS_RECTUM"]
    ctx = svc.build_letter_context(_rectum_insights(), _patient_male())
    resolved = svc.resolve_standard_texts(tid, ctx)
    # GREETING_SALUTATION seed is `Dear {{ referring_doctor }},` — referring_doctor
    # values typically include the title (e.g. "Dr. Smith") so the standard text
    # avoids hard-coding "Dr.".
    assert resolved["GREETING_SALUTATION"] == "Dear Smith,"
    assert "Mr. John Doe" in resolved["GREETING_OPENING"]
    assert "Rectal adenocarcinoma" in resolved["GREETING_OPENING"]
    assert "Mr. John Doe" in resolved["DISCUSSION_PREAMBLE"]
    assert resolved["RT_DOSE_LINE"] == "RT dose: 50.4 Gy in 28 fractions, over 5.5 weeks."
    assert resolved["RT_INTENT_LINE"] == "RT intent: Neoadjuvant"
    assert resolved["EXAM_HEADER"] == "**ASSESSMENT AND EXAMINATION:**"
    assert resolved["CLOSING"] == "Thanks for involving me in the care of this patient."


def test_resolve_handles_missing_placeholders_silently(template_ids):
    """Missing context vars should resolve to empty string, never raise."""
    tid = template_ids["RS_RECTUM"]
    insights = _rectum_insights()
    insights.pop("REFERRAL_DETAILS", None)
    ctx = svc.build_letter_context(insights, _patient_male())
    resolved = svc.resolve_standard_texts(tid, ctx)
    assert resolved["GREETING_SALUTATION"] == "Dear ,"  # var resolved to ""


# ---------------------------------------------------------------------------
# Full letter render (live DB read)
# ---------------------------------------------------------------------------

def test_render_full_letter_rectum_contains_all_sections(template_ids):
    tid = template_ids["RS_RECTUM"]
    ctx = svc.build_letter_context(_rectum_insights(), _patient_male())
    ctx.update(svc.resolve_standard_texts(tid, ctx))
    letter = svc.render_full_letter(tid, ctx)
    assert letter is not None and letter.strip()
    # Headers + closing in correct positions
    assert letter.startswith("Dear Smith,")
    assert "Mr. John Doe" in letter
    assert "ASSESSMENT AND EXAMINATION:" in letter
    assert "PLAN OF MANAGEMENT:" in letter
    # Plan line resolved
    assert "RT dose: 50.4 Gy in 28 fractions, over 5.5 weeks." in letter
    # Toxicity bullets
    assert "Fatigue, weight loss" in letter
    assert "Small but real risk of radiation-induced secondary malignancy." in letter
    # Site-specific exam fields
    assert "DRE: Mass at 5 cm" in letter
    # Closing at end
    assert letter.rstrip().endswith("Thanks for involving me in the care of this patient.")


def test_render_collapses_empty_optional_blocks(template_ids):
    tid = template_ids["RS_RECTUM"]
    insights = _rectum_insights()
    # Drop optional blocks
    insights["INVESTIGATIONS_BLOODWORKS"] = {}
    insights["FAMILY_HISTORY"] = {"family_history": ""}
    ctx = svc.build_letter_context(insights, _patient_male())
    ctx.update(svc.resolve_standard_texts(tid, ctx))
    letter = svc.render_full_letter(tid, ctx)
    assert letter is not None
    # Empty bloodworks => "Blood works:" header should not appear
    assert "Blood works:" not in letter
    # Empty family_history => no "Family History:" label
    assert "Family History:" not in letter


def test_render_each_site(template_ids):
    """Smoke-test each of the 5 sites — layouts must render without error
    and produce a non-empty letter even with sparse insights."""
    minimal_insights = {
        "PRESENTING_COMPLAINTS": {"presenting_complaints": "Test."},
        "PLAN": {"rt_intent": "Curative", "rt_dose_gy": "50", "rt_fractions": "25", "rt_weeks": "5", "rt_technique": "VMAT"},
        "TOXICITY": {"early_toxicities": [{"text": "Test early"}], "late_toxicities": [{"text": "Test late"}]},
        "REFERRAL_DETAILS": {"referred_by": "Adams"},
        "DIAGNOSIS": [{"name": "Cancer", "type": "Primary"}],
        "IMPRESSION_AND_PLAN": {"impression": "Test impression."},
    }
    for code, tid in template_ids.items():
        ctx = svc.build_letter_context(minimal_insights, _patient_female())
        ctx.update(svc.resolve_standard_texts(tid, ctx))
        letter = svc.render_full_letter(tid, ctx)
        assert letter is not None, f"render returned None for {code}"
        assert "Dear Adams," in letter, f"greeting missing for {code}"
        assert "Mrs. Jane Smith" in letter, f"honorific missing for {code}"
        assert "RT dose: 50 Gy in 25 fractions" in letter, f"RT dose line missing for {code}"
        assert letter.rstrip().endswith("Thanks for involving me in the care of this patient."), \
            f"closing missing for {code}"


# ---------------------------------------------------------------------------
# attach_letter_artifacts (mutation contract)
# ---------------------------------------------------------------------------

def test_attach_letter_artifacts_mutates_insights(template_ids):
    tid = template_ids["RS_RECTUM"]
    insights = _rectum_insights()
    # Bypass real patient lookup; supply via patch
    with patch.object(svc, "_fetch_patient", return_value=_patient_male()):
        svc.attach_letter_artifacts(insights, tid, patient_id="00000000-0000-0000-0000-000000000000")
    assert "standard_texts" in insights
    assert "consult_letter" in insights
    assert insights["standard_texts"]["GREETING_SALUTATION"] == "Dear Smith,"
    assert insights["consult_letter"].startswith("Dear Smith,")
    assert "RT dose: 50.4 Gy in 28 fractions" in insights["consult_letter"]


def test_attach_no_layout_is_noop():
    """Templates without a layout should leave insights untouched."""
    # Pick any non-radiology template id from DB if available; otherwise skip.
    rows = (
        supabase.table("templates")
        .select("id, template_code, letter_template_jinja")
        .is_("letter_template_jinja", "null")
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        pytest.skip("No templates without a layout to test against")
    tid = uuid.UUID(rows[0]["id"])
    insights = {"FOO": {"bar": "baz"}}
    svc.attach_letter_artifacts(insights, tid, patient_id=None)
    assert "consult_letter" not in insights
    assert "standard_texts" not in insights

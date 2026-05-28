-- Radiology consult-letter rendering: per-template Jinja2 layout column +
-- seed of 25 standard text fragments × 5 RS_* templates (125 rows).
-- Source of truth: references/dharan prompts/07_letter_template.md.
-- Idempotent: ON CONFLICT DO NOTHING for fragment seeds, no-op IF NOT EXISTS for column add.

ALTER TABLE templates
    ADD COLUMN IF NOT EXISTS letter_template_jinja TEXT;

COMMENT ON COLUMN templates.letter_template_jinja IS
    'Optional Jinja2 layout used by letter_render_service to produce consult_letter at extraction tail. NULL => no rendering.';

-- ============================================================================
-- 25 standard text fragments × 5 RS_* templates
-- ============================================================================

INSERT INTO template_standard_texts (template_id, key, label, text, display_order)
SELECT t.id, v.key, v.label, v.text, v.display_order
FROM templates t
CROSS JOIN (VALUES
  (1, 'GREETING_SALUTATION', 'Greeting salutation', 'Dear Dr. {{ referring_doctor }},'),
  (2, 'GREETING_OPENING', 'Greeting opening', 'Thanks for referring {{ honorific }} {{ patient_name }}, {{ patient_age }} years old, diagnosed to have {{ primary_diagnosis }}, for evaluation and management.'),
  (3, 'EXAM_HEADER', 'Examination header', 'ASSESSMENT AND EXAMINATION:'),
  (4, 'EXAM_CONSENT_DEFAULT', 'Default exam consent', 'Consent was provided to proceed with the physical examination.'),
  (5, 'EXAM_GENERAL_DEFAULT', 'Default general exam', 'Fully conscious with no acute distress. Cooperative and answering questions appropriately.'),
  (6, 'EXAM_NECK_DEFAULT', 'Default neck exam', 'No palpable cervical or supraclavicular lymph nodes on both sides.'),
  (7, 'EXAM_ABDOMEN_DEFAULT', 'Default abdomen exam', 'Soft, not tender, no palpable mass or organomegaly.'),
  (8, 'EXAM_SPINE_DEFAULT', 'Default spine exam', 'No tenderness in spine.'),
  (9, 'IMPRESSION_HEADER', 'Impression header', 'IMPRESSION:'),
  (10, 'PLAN_HEADER', 'Plan header', 'PLAN OF MANAGEMENT:'),
  (11, 'DISCUSSION_PREAMBLE', 'Discussion preamble', 'We had a lengthy discussion with {{ honorific }} {{ patient_name }} today regarding prognosis, treatment options, and the role of radiation therapy in the management.'),
  (12, 'TREATMENT_DECISION_PREAMBLE', 'Treatment decision preamble', 'Given the patient''s performance status, disease stage, and risk stratification, we recommend proceeding with radiation therapy as part of the overall treatment plan. The logistics, risks, benefits, and alternatives were discussed in great detail during our consultation visit today.'),
  (13, 'RT_BLOCK_HEADER', 'Radiation block header', 'Radiation Therapy:'),
  (14, 'RT_INTENT_LINE', 'RT intent line', 'RT intent: {{ rt_intent }}'),
  (15, 'RT_DOSE_LINE', 'RT dose line', 'RT dose: {{ rt_dose_gy }} Gy in {{ rt_fractions }} fractions, over {{ rt_weeks }} weeks.'),
  (16, 'RT_TECHNIQUE_LINE', 'RT technique line', 'RT technique: {{ rt_technique }}'),
  (17, 'RT_CONCURRENT_LINE', 'RT concurrent therapy line', 'Concurrent systemic therapy: {{ concurrent_systemic_therapy }}'),
  (18, 'EARLY_TOX_PREAMBLE', 'Early toxicity preamble', 'Expected early toxicity of radiation: Patient will be seen weekly in the radiation review clinic and toxicities will be actively managed. Patient will also have access to assessment at radiation nursing clinic during radiation treatment whenever needed. Potential early toxicities were discussed and may include, but are not limited to:'),
  (19, 'LATE_TOX_PREAMBLE', 'Late toxicity preamble', 'Expected late toxicity of radiation: potential late toxicities were discussed, and may include but are not limited to:'),
  (20, 'RT_PREPARATION', 'RT preparation', 'Radiation preparation: the principles of the radiation therapy preparation and simulation were reviewed along with the immobilization. Imaging for the purpose of RT simulation was booked.'),
  (21, 'FINAL_CONSENT', 'Final consent', 'Consent: {{ honorific }} {{ patient_name }} has verbalized understanding of the preparation for treatment, rationale, treatment course, expected outcomes, and potential side effects and has agreed to proceed with treatment. All of {{ honorific }} {{ patient_name }}''s questions and concerns were addressed during our consultation visit, and we have encouraged {{ honorific }} {{ patient_name }} to please contact our department in the future with any further questions that arise.'),
  (22, 'ORDERS_HEADER', 'Orders header', 'Orders: We are arranging for the following:'),
  (23, 'REFERRALS_HEADER', 'Referrals header', 'Consultations: we are arranging for the following referrals:'),
  (24, 'ADVICE_HEADER', 'Advice header', 'Advice:'),
  (25, 'CLOSING', 'Closing', 'Thanks for involving me in the care of this patient.')
) AS v(display_order, key, label, text)
WHERE t.template_code IN ('RS_RECTUM','RS_PROSTATE','RS_HN','RS_GYN','RS_BREAST')
ON CONFLICT (template_id, key) DO NOTHING;


-- ============================================================================
-- Per-template Jinja2 layouts (07_letter_template.md, with each site's exam
-- partial inlined where the {% include site_specific_exam_partial %} marker is).
-- ============================================================================

-- ---- RS_RECTUM ----
UPDATE templates SET letter_template_jinja = $LAYOUT$
{# === HEADER === #}
{{ GREETING_SALUTATION }}

{{ GREETING_OPENING }}

{# === HISTORY === #}
Presenting complaints:
{{ presenting_complaints }}

{% if associated_symptoms %}
Associated symptoms:
{{ associated_symptoms }}
{% endif %}

Comorbidities:
{{ comorbidities or "Nil." }}

{% if current_medications %}
Medications:
{% for med in current_medications %}- {{ med }}
{% endfor %}
{% endif %}

{% if allergies %}
Allergies:
{% for a in allergies %}- {{ a }}
{% endfor %}
{% endif %}

{% if family_history %}
Family History:
{{ family_history }}
{% endif %}

{% if social_history %}
Social History:
{{ social_history }}
{% endif %}

{# === INVESTIGATIONS === #}
Investigations:

{% if imaging %}
Imaging:
{% for i in imaging %}- {{ i }}
{% endfor %}
{% endif %}

{% if biopsy_details or hpr_findings %}
Biopsy of primary / lymph node:
{% if biopsy_details %}{{ biopsy_details }}{% endif %}
{% if hpr_findings %}HPR: {{ hpr_findings }}{% endif %}
{% endif %}

{% if has_any_blood_value %}
Blood works:
{% if hb_g_dl %}- Hb: {{ hb_g_dl }} g/dL{% endif %}
{% if platelets_lakhs_mm3 %}- Platelets: {{ platelets_lakhs_mm3 }} lakhs/mm3{% endif %}
{% if wbc_cells_mm3 %}- WBC: {{ wbc_cells_mm3 }} cells/mm3{% endif %}
{% if anc_cells_mm3 %}- ANC: {{ anc_cells_mm3 }} cells/mm3{% endif %}
{% if neutrophils_pct %}- Neutrophils: {{ neutrophils_pct }} %{% endif %}
{% if creatinine_mg_dl %}- Creatinine: {{ creatinine_mg_dl }} mg/dL{% endif %}
{% if albumin_mg_dl %}- Albumin: {{ albumin_mg_dl }} mg/dL{% endif %}
{% if sodium_meq_l %}- Sodium: {{ sodium_meq_l }} mEq/L{% endif %}
{% if potassium_meq_l %}- Potassium: {{ potassium_meq_l }} mEq/L{% endif %}
{% if calcium_mg_dl %}- Calcium: {{ calcium_mg_dl }} mg/dL{% endif %}
{% endif %}

{# === INITIAL/OUTSIDE TREATMENT === #}
{% if prior_treatment_summary or chemotherapy_details or surgery_details or prior_radiation %}
Initial / Outside Treatment:
{% if prior_treatment_summary %}{{ prior_treatment_summary }}{% endif %}
{% if chemotherapy_details %}Chemotherapy:
{% for c in chemotherapy_details %}- {{ c }}
{% endfor %}{% endif %}
{% if surgery_details %}Surgery: {{ surgery_details }}{% endif %}
{% if prior_radiation %}Prior radiation: {{ prior_radiation }}{% endif %}
{% endif %}

{# === RT CONSIDERATIONS === #}
Radiation Therapy considerations:
- Pacemaker: {{ pacemaker or "Not assessed" }}
- Connective tissue disorders (e.g. SLE, scleroderma): {{ connective_tissue_disorder or "Not assessed" }}
- Previous radiation exposure: {{ previous_radiation_exposure or "Not assessed" }}
- Allergy to CT/MRI contrast: {{ contrast_allergy_ct_mri or "Not assessed" }}
- Contraindication to MR (e.g. implants): {{ mr_contraindication or "Not assessed" }}
- Diabetes / Kidney disease: {{ diabetes_or_kidney_disease or "Not assessed" }}
{% if additional_notes %}- Additional: {{ additional_notes }}{% endif %}

{# === EXAMINATION === #}
{{ EXAM_HEADER }}
Consent: {{ consent_status or EXAM_CONSENT_DEFAULT }}
General: {{ general_appearance or EXAM_GENERAL_DEFAULT }}
Overall performance status: {% if ecog %}ECOG {{ ecog }}{% endif %}{% if ecog and kps %} / {% endif %}{% if kps %}KPS {{ kps }}{% endif %}
Neck: {{ neck_exam or EXAM_NECK_DEFAULT }}
Abdomen: {{ abdomen_exam or EXAM_ABDOMEN_DEFAULT }}
Spine: {{ spine_exam or EXAM_SPINE_DEFAULT }}

{# === SITE-SPECIFIC EXAM (rectum) === #}
{% if digital_rectal_exam %}DRE: {{ digital_rectal_exam }}{% endif %}
{% if inguinal_lymph_node_exam %}Inguinal area: {{ inguinal_lymph_node_exam }}{% endif %}
{% if lower_limb_edema %}Lower limb: {{ lower_limb_edema }}{% endif %}
{% if distance_from_anal_verge_cm %}Distance from anal verge: {{ distance_from_anal_verge_cm }} cm{% endif %}
{% if circumferential_extent %}Circumferential extent: {{ circumferential_extent }}{% endif %}
{% if mesorectal_fascia_status %}Mesorectal fascia: {{ mesorectal_fascia_status }}{% endif %}
{% if additional_site_notes %}{{ additional_site_notes }}{% endif %}

{# === IMPRESSION === #}
{{ IMPRESSION_HEADER }}
{{ impression }}
{% if cancer_staging %}Stage: {{ cancer_staging }}{% endif %}
{% if risk_stratification %}Risk: {{ risk_stratification }}{% endif %}

{# === PLAN === #}
{{ PLAN_HEADER }}

{{ DISCUSSION_PREAMBLE }}

{% if discussion_summary %}{{ discussion_summary }}{% endif %}

{{ TREATMENT_DECISION_PREAMBLE }}

{% if treatment_decision_summary %}{{ treatment_decision_summary }}{% endif %}

{{ RT_BLOCK_HEADER }}
{% if rt_intent %}{{ RT_INTENT_LINE }}{% endif %}
{% if rt_dose_gy and rt_fractions %}{{ RT_DOSE_LINE }}{% endif %}
{% if rt_technique %}{{ RT_TECHNIQUE_LINE }}{% endif %}
{% if concurrent_systemic_therapy %}{{ RT_CONCURRENT_LINE }}{% endif %}
{% for phase in additional_phases %}- {{ phase }}
{% endfor %}
{% if patient_specific_modifications %}Note: {{ patient_specific_modifications }}{% endif %}

{# === TOXICITIES === #}
{{ EARLY_TOX_PREAMBLE }}
{% for t in early_toxicities %}- {{ t.text }}
{% endfor %}

{{ LATE_TOX_PREAMBLE }}
{% for t in late_toxicities %}- {{ t.text }}
{% endfor %}

{# === RADIATION PREPARATION === #}
{{ RT_PREPARATION }}

{% if simulation_status %}{{ simulation_status }}{% endif %}

{# === FINAL CONSENT === #}
{{ FINAL_CONSENT }}

{# === ORDERS / REFERRALS / ADVICE === #}
{% if orders %}
{{ ORDERS_HEADER }}
{% for o in orders %}- {{ o }}
{% endfor %}
{% endif %}

{% if onward_referrals %}
{{ REFERRALS_HEADER }}
{% for r in onward_referrals %}- {{ r }}
{% endfor %}
{% endif %}

{% if advice %}
{{ ADVICE_HEADER }}
{% for a in advice %}- {{ a }}
{% endfor %}
{% endif %}

{# === CLOSING === #}
{{ CLOSING }}
$LAYOUT$
WHERE template_code = 'RS_RECTUM';

-- ---- RS_PROSTATE ----
UPDATE templates SET letter_template_jinja = $LAYOUT$
{# === HEADER === #}
{{ GREETING_SALUTATION }}

{{ GREETING_OPENING }}

{# === HISTORY === #}
Presenting complaints:
{{ presenting_complaints }}

{% if associated_symptoms %}
Associated symptoms:
{{ associated_symptoms }}
{% endif %}

Comorbidities:
{{ comorbidities or "Nil." }}

{% if current_medications %}
Medications:
{% for med in current_medications %}- {{ med }}
{% endfor %}
{% endif %}

{% if allergies %}
Allergies:
{% for a in allergies %}- {{ a }}
{% endfor %}
{% endif %}

{% if family_history %}
Family History:
{{ family_history }}
{% endif %}

{% if social_history %}
Social History:
{{ social_history }}
{% endif %}

{# === INVESTIGATIONS === #}
Investigations:

{% if imaging %}
Imaging:
{% for i in imaging %}- {{ i }}
{% endfor %}
{% endif %}

{% if biopsy_details or hpr_findings %}
Biopsy of primary / lymph node:
{% if biopsy_details %}{{ biopsy_details }}{% endif %}
{% if hpr_findings %}HPR: {{ hpr_findings }}{% endif %}
{% endif %}

{% if has_any_blood_value %}
Blood works:
{% if hb_g_dl %}- Hb: {{ hb_g_dl }} g/dL{% endif %}
{% if platelets_lakhs_mm3 %}- Platelets: {{ platelets_lakhs_mm3 }} lakhs/mm3{% endif %}
{% if wbc_cells_mm3 %}- WBC: {{ wbc_cells_mm3 }} cells/mm3{% endif %}
{% if anc_cells_mm3 %}- ANC: {{ anc_cells_mm3 }} cells/mm3{% endif %}
{% if neutrophils_pct %}- Neutrophils: {{ neutrophils_pct }} %{% endif %}
{% if creatinine_mg_dl %}- Creatinine: {{ creatinine_mg_dl }} mg/dL{% endif %}
{% if albumin_mg_dl %}- Albumin: {{ albumin_mg_dl }} mg/dL{% endif %}
{% if sodium_meq_l %}- Sodium: {{ sodium_meq_l }} mEq/L{% endif %}
{% if potassium_meq_l %}- Potassium: {{ potassium_meq_l }} mEq/L{% endif %}
{% if calcium_mg_dl %}- Calcium: {{ calcium_mg_dl }} mg/dL{% endif %}
{% endif %}

{% if prior_treatment_summary or chemotherapy_details or surgery_details or prior_radiation %}
Initial / Outside Treatment:
{% if prior_treatment_summary %}{{ prior_treatment_summary }}{% endif %}
{% if chemotherapy_details %}Chemotherapy:
{% for c in chemotherapy_details %}- {{ c }}
{% endfor %}{% endif %}
{% if surgery_details %}Surgery: {{ surgery_details }}{% endif %}
{% if prior_radiation %}Prior radiation: {{ prior_radiation }}{% endif %}
{% endif %}

Radiation Therapy considerations:
- Pacemaker: {{ pacemaker or "Not assessed" }}
- Connective tissue disorders (e.g. SLE, scleroderma): {{ connective_tissue_disorder or "Not assessed" }}
- Previous radiation exposure: {{ previous_radiation_exposure or "Not assessed" }}
- Allergy to CT/MRI contrast: {{ contrast_allergy_ct_mri or "Not assessed" }}
- Contraindication to MR (e.g. implants): {{ mr_contraindication or "Not assessed" }}
- Diabetes / Kidney disease: {{ diabetes_or_kidney_disease or "Not assessed" }}
{% if additional_notes %}- Additional: {{ additional_notes }}{% endif %}

{{ EXAM_HEADER }}
Consent: {{ consent_status or EXAM_CONSENT_DEFAULT }}
General: {{ general_appearance or EXAM_GENERAL_DEFAULT }}
Overall performance status: {% if ecog %}ECOG {{ ecog }}{% endif %}{% if ecog and kps %} / {% endif %}{% if kps %}KPS {{ kps }}{% endif %}
Neck: {{ neck_exam or EXAM_NECK_DEFAULT }}
Abdomen: {{ abdomen_exam or EXAM_ABDOMEN_DEFAULT }}
Spine: {{ spine_exam or EXAM_SPINE_DEFAULT }}

{# === SITE-SPECIFIC EXAM (prostate) === #}
{% if digital_rectal_exam %}DRE: {{ digital_rectal_exam }}{% endif %}
{% if urinary_function_baseline %}Urinary baseline: {{ urinary_function_baseline }}{% endif %}
{% if bowel_function_baseline %}Bowel baseline: {{ bowel_function_baseline }}{% endif %}
{% if sexual_function_baseline %}Sexual function baseline: {{ sexual_function_baseline }}{% endif %}
{% if psa_value_ng_ml %}PSA: {{ psa_value_ng_ml }} ng/mL{% if psa_date %} ({{ psa_date }}){% endif %}{% endif %}
{% if gleason_score %}Gleason score: {{ gleason_score }}{% endif %}
{% if isup_grade_group %}ISUP grade group: {{ isup_grade_group }}{% endif %}
{% if d_amico_or_nccn_risk %}Risk: {{ d_amico_or_nccn_risk }}{% endif %}
{% if adt_status %}ADT: {{ adt_status }}{% endif %}
{% if additional_site_notes %}{{ additional_site_notes }}{% endif %}

{{ IMPRESSION_HEADER }}
{{ impression }}
{% if cancer_staging %}Stage: {{ cancer_staging }}{% endif %}
{% if risk_stratification %}Risk: {{ risk_stratification }}{% endif %}

{{ PLAN_HEADER }}

{{ DISCUSSION_PREAMBLE }}

{% if discussion_summary %}{{ discussion_summary }}{% endif %}

{{ TREATMENT_DECISION_PREAMBLE }}

{% if treatment_decision_summary %}{{ treatment_decision_summary }}{% endif %}

{{ RT_BLOCK_HEADER }}
{% if rt_intent %}{{ RT_INTENT_LINE }}{% endif %}
{% if rt_dose_gy and rt_fractions %}{{ RT_DOSE_LINE }}{% endif %}
{% if rt_technique %}{{ RT_TECHNIQUE_LINE }}{% endif %}
{% if concurrent_systemic_therapy %}{{ RT_CONCURRENT_LINE }}{% endif %}
{% for phase in additional_phases %}- {{ phase }}
{% endfor %}
{% if patient_specific_modifications %}Note: {{ patient_specific_modifications }}{% endif %}

{{ EARLY_TOX_PREAMBLE }}
{% for t in early_toxicities %}- {{ t.text }}
{% endfor %}

{{ LATE_TOX_PREAMBLE }}
{% for t in late_toxicities %}- {{ t.text }}
{% endfor %}

{{ RT_PREPARATION }}

{% if simulation_status %}{{ simulation_status }}{% endif %}

{{ FINAL_CONSENT }}

{% if orders %}
{{ ORDERS_HEADER }}
{% for o in orders %}- {{ o }}
{% endfor %}
{% endif %}

{% if onward_referrals %}
{{ REFERRALS_HEADER }}
{% for r in onward_referrals %}- {{ r }}
{% endfor %}
{% endif %}

{% if advice %}
{{ ADVICE_HEADER }}
{% for a in advice %}- {{ a }}
{% endfor %}
{% endif %}

{{ CLOSING }}
$LAYOUT$
WHERE template_code = 'RS_PROSTATE';

-- ---- RS_HN ----
UPDATE templates SET letter_template_jinja = $LAYOUT$
{{ GREETING_SALUTATION }}

{{ GREETING_OPENING }}

Presenting complaints:
{{ presenting_complaints }}

{% if associated_symptoms %}
Associated symptoms:
{{ associated_symptoms }}
{% endif %}

Comorbidities:
{{ comorbidities or "Nil." }}

{% if current_medications %}
Medications:
{% for med in current_medications %}- {{ med }}
{% endfor %}
{% endif %}

{% if allergies %}
Allergies:
{% for a in allergies %}- {{ a }}
{% endfor %}
{% endif %}

{% if family_history %}
Family History:
{{ family_history }}
{% endif %}

{% if social_history %}
Social History:
{{ social_history }}
{% endif %}

Investigations:

{% if imaging %}
Imaging:
{% for i in imaging %}- {{ i }}
{% endfor %}
{% endif %}

{% if biopsy_details or hpr_findings %}
Biopsy of primary / lymph node:
{% if biopsy_details %}{{ biopsy_details }}{% endif %}
{% if hpr_findings %}HPR: {{ hpr_findings }}{% endif %}
{% endif %}

{% if has_any_blood_value %}
Blood works:
{% if hb_g_dl %}- Hb: {{ hb_g_dl }} g/dL{% endif %}
{% if platelets_lakhs_mm3 %}- Platelets: {{ platelets_lakhs_mm3 }} lakhs/mm3{% endif %}
{% if wbc_cells_mm3 %}- WBC: {{ wbc_cells_mm3 }} cells/mm3{% endif %}
{% if anc_cells_mm3 %}- ANC: {{ anc_cells_mm3 }} cells/mm3{% endif %}
{% if neutrophils_pct %}- Neutrophils: {{ neutrophils_pct }} %{% endif %}
{% if creatinine_mg_dl %}- Creatinine: {{ creatinine_mg_dl }} mg/dL{% endif %}
{% if albumin_mg_dl %}- Albumin: {{ albumin_mg_dl }} mg/dL{% endif %}
{% if sodium_meq_l %}- Sodium: {{ sodium_meq_l }} mEq/L{% endif %}
{% if potassium_meq_l %}- Potassium: {{ potassium_meq_l }} mEq/L{% endif %}
{% if calcium_mg_dl %}- Calcium: {{ calcium_mg_dl }} mg/dL{% endif %}
{% endif %}

{% if prior_treatment_summary or chemotherapy_details or surgery_details or prior_radiation %}
Initial / Outside Treatment:
{% if prior_treatment_summary %}{{ prior_treatment_summary }}{% endif %}
{% if chemotherapy_details %}Chemotherapy:
{% for c in chemotherapy_details %}- {{ c }}
{% endfor %}{% endif %}
{% if surgery_details %}Surgery: {{ surgery_details }}{% endif %}
{% if prior_radiation %}Prior radiation: {{ prior_radiation }}{% endif %}
{% endif %}

Radiation Therapy considerations:
- Pacemaker: {{ pacemaker or "Not assessed" }}
- Connective tissue disorders (e.g. SLE, scleroderma): {{ connective_tissue_disorder or "Not assessed" }}
- Previous radiation exposure: {{ previous_radiation_exposure or "Not assessed" }}
- Allergy to CT/MRI contrast: {{ contrast_allergy_ct_mri or "Not assessed" }}
- Contraindication to MR (e.g. implants): {{ mr_contraindication or "Not assessed" }}
- Diabetes / Kidney disease: {{ diabetes_or_kidney_disease or "Not assessed" }}
{% if additional_notes %}- Additional: {{ additional_notes }}{% endif %}

{{ EXAM_HEADER }}
Consent: {{ consent_status or EXAM_CONSENT_DEFAULT }}
General: {{ general_appearance or EXAM_GENERAL_DEFAULT }}
Overall performance status: {% if ecog %}ECOG {{ ecog }}{% endif %}{% if ecog and kps %} / {% endif %}{% if kps %}KPS {{ kps }}{% endif %}
Neck: {{ neck_exam or EXAM_NECK_DEFAULT }}
Abdomen: {{ abdomen_exam or EXAM_ABDOMEN_DEFAULT }}
Spine: {{ spine_exam or EXAM_SPINE_DEFAULT }}

{# === SITE-SPECIFIC EXAM (head & neck) === #}
{% if swallowing %}Swallowing: {{ swallowing }}{% endif %}
{% if speech %}Speech: {{ speech }}{% endif %}
{% if oral_cavity_oropharynx_exam %}Oral cavity / oropharynx: {{ oral_cavity_oropharynx_exam }}{% endif %}
{% if fibreoptic_endoscopy_findings %}Fibreoptic endoscopy: {{ fibreoptic_endoscopy_findings }}{% endif %}
{% if jaw_movement %}Jaw movement: {{ jaw_movement }}{% endif %}
{% if shoulder_movement %}Shoulder movement: {{ shoulder_movement }}{% endif %}
{% if facial_nerve_exam %}Facial nerve: {{ facial_nerve_exam }}{% endif %}
{% if neck_node_findings_detailed %}Neck nodes (detail): {{ neck_node_findings_detailed }}{% endif %}
{% if dental_status %}Dental status: {{ dental_status }}{% endif %}
{% if additional_site_notes %}{{ additional_site_notes }}{% endif %}

{{ IMPRESSION_HEADER }}
{{ impression }}
{% if cancer_staging %}Stage: {{ cancer_staging }}{% endif %}
{% if risk_stratification %}Risk: {{ risk_stratification }}{% endif %}

{{ PLAN_HEADER }}

{{ DISCUSSION_PREAMBLE }}

{% if discussion_summary %}{{ discussion_summary }}{% endif %}

{{ TREATMENT_DECISION_PREAMBLE }}

{% if treatment_decision_summary %}{{ treatment_decision_summary }}{% endif %}

{{ RT_BLOCK_HEADER }}
{% if rt_intent %}{{ RT_INTENT_LINE }}{% endif %}
{% if rt_dose_gy and rt_fractions %}{{ RT_DOSE_LINE }}{% endif %}
{% if rt_technique %}{{ RT_TECHNIQUE_LINE }}{% endif %}
{% if concurrent_systemic_therapy %}{{ RT_CONCURRENT_LINE }}{% endif %}
{% for phase in additional_phases %}- {{ phase }}
{% endfor %}
{% if patient_specific_modifications %}Note: {{ patient_specific_modifications }}{% endif %}

{{ EARLY_TOX_PREAMBLE }}
{% for t in early_toxicities %}- {{ t.text }}
{% endfor %}

{{ LATE_TOX_PREAMBLE }}
{% for t in late_toxicities %}- {{ t.text }}
{% endfor %}

{{ RT_PREPARATION }}

{% if simulation_status %}{{ simulation_status }}{% endif %}

{{ FINAL_CONSENT }}

{% if orders %}
{{ ORDERS_HEADER }}
{% for o in orders %}- {{ o }}
{% endfor %}
{% endif %}

{% if onward_referrals %}
{{ REFERRALS_HEADER }}
{% for r in onward_referrals %}- {{ r }}
{% endfor %}
{% endif %}

{% if advice %}
{{ ADVICE_HEADER }}
{% for a in advice %}- {{ a }}
{% endfor %}
{% endif %}

{{ CLOSING }}
$LAYOUT$
WHERE template_code = 'RS_HN';

-- ---- RS_GYN ----
UPDATE templates SET letter_template_jinja = $LAYOUT$
{{ GREETING_SALUTATION }}

{{ GREETING_OPENING }}

Presenting complaints:
{{ presenting_complaints }}

{% if associated_symptoms %}
Associated symptoms:
{{ associated_symptoms }}
{% endif %}

Comorbidities:
{{ comorbidities or "Nil." }}

{% if current_medications %}
Medications:
{% for med in current_medications %}- {{ med }}
{% endfor %}
{% endif %}

{% if allergies %}
Allergies:
{% for a in allergies %}- {{ a }}
{% endfor %}
{% endif %}

{% if family_history %}
Family History:
{{ family_history }}
{% endif %}

{% if social_history %}
Social History:
{{ social_history }}
{% endif %}

Investigations:

{% if imaging %}
Imaging:
{% for i in imaging %}- {{ i }}
{% endfor %}
{% endif %}

{% if biopsy_details or hpr_findings %}
Biopsy of primary / lymph node:
{% if biopsy_details %}{{ biopsy_details }}{% endif %}
{% if hpr_findings %}HPR: {{ hpr_findings }}{% endif %}
{% endif %}

{% if has_any_blood_value %}
Blood works:
{% if hb_g_dl %}- Hb: {{ hb_g_dl }} g/dL{% endif %}
{% if platelets_lakhs_mm3 %}- Platelets: {{ platelets_lakhs_mm3 }} lakhs/mm3{% endif %}
{% if wbc_cells_mm3 %}- WBC: {{ wbc_cells_mm3 }} cells/mm3{% endif %}
{% if anc_cells_mm3 %}- ANC: {{ anc_cells_mm3 }} cells/mm3{% endif %}
{% if neutrophils_pct %}- Neutrophils: {{ neutrophils_pct }} %{% endif %}
{% if creatinine_mg_dl %}- Creatinine: {{ creatinine_mg_dl }} mg/dL{% endif %}
{% if albumin_mg_dl %}- Albumin: {{ albumin_mg_dl }} mg/dL{% endif %}
{% if sodium_meq_l %}- Sodium: {{ sodium_meq_l }} mEq/L{% endif %}
{% if potassium_meq_l %}- Potassium: {{ potassium_meq_l }} mEq/L{% endif %}
{% if calcium_mg_dl %}- Calcium: {{ calcium_mg_dl }} mg/dL{% endif %}
{% endif %}

{% if prior_treatment_summary or chemotherapy_details or surgery_details or prior_radiation %}
Initial / Outside Treatment:
{% if prior_treatment_summary %}{{ prior_treatment_summary }}{% endif %}
{% if chemotherapy_details %}Chemotherapy:
{% for c in chemotherapy_details %}- {{ c }}
{% endfor %}{% endif %}
{% if surgery_details %}Surgery: {{ surgery_details }}{% endif %}
{% if prior_radiation %}Prior radiation: {{ prior_radiation }}{% endif %}
{% endif %}

Radiation Therapy considerations:
- Pacemaker: {{ pacemaker or "Not assessed" }}
- Connective tissue disorders (e.g. SLE, scleroderma): {{ connective_tissue_disorder or "Not assessed" }}
- Previous radiation exposure: {{ previous_radiation_exposure or "Not assessed" }}
- Allergy to CT/MRI contrast: {{ contrast_allergy_ct_mri or "Not assessed" }}
- Contraindication to MR (e.g. implants): {{ mr_contraindication or "Not assessed" }}
- Diabetes / Kidney disease: {{ diabetes_or_kidney_disease or "Not assessed" }}
{% if additional_notes %}- Additional: {{ additional_notes }}{% endif %}

{{ EXAM_HEADER }}
Consent: {{ consent_status or EXAM_CONSENT_DEFAULT }}
General: {{ general_appearance or EXAM_GENERAL_DEFAULT }}
Overall performance status: {% if ecog %}ECOG {{ ecog }}{% endif %}{% if ecog and kps %} / {% endif %}{% if kps %}KPS {{ kps }}{% endif %}
Neck: {{ neck_exam or EXAM_NECK_DEFAULT }}
Abdomen: {{ abdomen_exam or EXAM_ABDOMEN_DEFAULT }}
Spine: {{ spine_exam or EXAM_SPINE_DEFAULT }}

{# === SITE-SPECIFIC EXAM (gyn) === #}
{% if per_vaginal_exam %}Per vaginal examination: {{ per_vaginal_exam }}{% endif %}
{% if per_rectal_exam %}Per rectal examination: {{ per_rectal_exam }}{% endif %}
{% if parametrial_involvement %}Parametrial involvement: {{ parametrial_involvement }}{% endif %}
{% if vaginal_extension_cm %}Vaginal extension: {{ vaginal_extension_cm }} cm{% endif %}
{% if examination_under_anaesthesia == "Yes" %}EUA performed.{% endif %}
{% if brachytherapy_planned == "Yes" %}Brachytherapy planned: {{ brachytherapy_modality }}, {{ brachytherapy_fractions_planned }} fractions.{% endif %}
{% if menopausal_status %}Menopausal status: {{ menopausal_status }}.{% endif %}
{% if additional_site_notes %}{{ additional_site_notes }}{% endif %}

{{ IMPRESSION_HEADER }}
{{ impression }}
{% if cancer_staging %}Stage: {{ cancer_staging }}{% endif %}
{% if risk_stratification %}Risk: {{ risk_stratification }}{% endif %}

{{ PLAN_HEADER }}

{{ DISCUSSION_PREAMBLE }}

{% if discussion_summary %}{{ discussion_summary }}{% endif %}

{{ TREATMENT_DECISION_PREAMBLE }}

{% if treatment_decision_summary %}{{ treatment_decision_summary }}{% endif %}

{{ RT_BLOCK_HEADER }}
{% if rt_intent %}{{ RT_INTENT_LINE }}{% endif %}
{% if rt_dose_gy and rt_fractions %}{{ RT_DOSE_LINE }}{% endif %}
{% if rt_technique %}{{ RT_TECHNIQUE_LINE }}{% endif %}
{% if concurrent_systemic_therapy %}{{ RT_CONCURRENT_LINE }}{% endif %}
{% for phase in additional_phases %}- {{ phase }}
{% endfor %}
{% if patient_specific_modifications %}Note: {{ patient_specific_modifications }}{% endif %}

{{ EARLY_TOX_PREAMBLE }}
{% for t in early_toxicities %}- {{ t.text }}
{% endfor %}

{{ LATE_TOX_PREAMBLE }}
{% for t in late_toxicities %}- {{ t.text }}
{% endfor %}

{{ RT_PREPARATION }}

{% if simulation_status %}{{ simulation_status }}{% endif %}

{{ FINAL_CONSENT }}

{% if orders %}
{{ ORDERS_HEADER }}
{% for o in orders %}- {{ o }}
{% endfor %}
{% endif %}

{% if onward_referrals %}
{{ REFERRALS_HEADER }}
{% for r in onward_referrals %}- {{ r }}
{% endfor %}
{% endif %}

{% if advice %}
{{ ADVICE_HEADER }}
{% for a in advice %}- {{ a }}
{% endfor %}
{% endif %}

{{ CLOSING }}
$LAYOUT$
WHERE template_code = 'RS_GYN';

-- ---- RS_BREAST ----
UPDATE templates SET letter_template_jinja = $LAYOUT$
{{ GREETING_SALUTATION }}

{{ GREETING_OPENING }}

Presenting complaints:
{{ presenting_complaints }}

{% if associated_symptoms %}
Associated symptoms:
{{ associated_symptoms }}
{% endif %}

Comorbidities:
{{ comorbidities or "Nil." }}

{% if current_medications %}
Medications:
{% for med in current_medications %}- {{ med }}
{% endfor %}
{% endif %}

{% if allergies %}
Allergies:
{% for a in allergies %}- {{ a }}
{% endfor %}
{% endif %}

{% if family_history %}
Family History:
{{ family_history }}
{% endif %}

{% if social_history %}
Social History:
{{ social_history }}
{% endif %}

Investigations:

{% if imaging %}
Imaging:
{% for i in imaging %}- {{ i }}
{% endfor %}
{% endif %}

{% if biopsy_details or hpr_findings %}
Biopsy of primary / lymph node:
{% if biopsy_details %}{{ biopsy_details }}{% endif %}
{% if hpr_findings %}HPR: {{ hpr_findings }}{% endif %}
{% endif %}

{% if has_any_blood_value %}
Blood works:
{% if hb_g_dl %}- Hb: {{ hb_g_dl }} g/dL{% endif %}
{% if platelets_lakhs_mm3 %}- Platelets: {{ platelets_lakhs_mm3 }} lakhs/mm3{% endif %}
{% if wbc_cells_mm3 %}- WBC: {{ wbc_cells_mm3 }} cells/mm3{% endif %}
{% if anc_cells_mm3 %}- ANC: {{ anc_cells_mm3 }} cells/mm3{% endif %}
{% if neutrophils_pct %}- Neutrophils: {{ neutrophils_pct }} %{% endif %}
{% if creatinine_mg_dl %}- Creatinine: {{ creatinine_mg_dl }} mg/dL{% endif %}
{% if albumin_mg_dl %}- Albumin: {{ albumin_mg_dl }} mg/dL{% endif %}
{% if sodium_meq_l %}- Sodium: {{ sodium_meq_l }} mEq/L{% endif %}
{% if potassium_meq_l %}- Potassium: {{ potassium_meq_l }} mEq/L{% endif %}
{% if calcium_mg_dl %}- Calcium: {{ calcium_mg_dl }} mg/dL{% endif %}
{% endif %}

{% if prior_treatment_summary or chemotherapy_details or surgery_details or prior_radiation %}
Initial / Outside Treatment:
{% if prior_treatment_summary %}{{ prior_treatment_summary }}{% endif %}
{% if chemotherapy_details %}Chemotherapy:
{% for c in chemotherapy_details %}- {{ c }}
{% endfor %}{% endif %}
{% if surgery_details %}Surgery: {{ surgery_details }}{% endif %}
{% if prior_radiation %}Prior radiation: {{ prior_radiation }}{% endif %}
{% endif %}

Radiation Therapy considerations:
- Pacemaker: {{ pacemaker or "Not assessed" }}
- Connective tissue disorders (e.g. SLE, scleroderma): {{ connective_tissue_disorder or "Not assessed" }}
- Previous radiation exposure: {{ previous_radiation_exposure or "Not assessed" }}
- Allergy to CT/MRI contrast: {{ contrast_allergy_ct_mri or "Not assessed" }}
- Contraindication to MR (e.g. implants): {{ mr_contraindication or "Not assessed" }}
- Diabetes / Kidney disease: {{ diabetes_or_kidney_disease or "Not assessed" }}
{% if additional_notes %}- Additional: {{ additional_notes }}{% endif %}

{{ EXAM_HEADER }}
Consent: {{ consent_status or EXAM_CONSENT_DEFAULT }}
General: {{ general_appearance or EXAM_GENERAL_DEFAULT }}
Overall performance status: {% if ecog %}ECOG {{ ecog }}{% endif %}{% if ecog and kps %} / {% endif %}{% if kps %}KPS {{ kps }}{% endif %}
Neck: {{ neck_exam or EXAM_NECK_DEFAULT }}
Abdomen: {{ abdomen_exam or EXAM_ABDOMEN_DEFAULT }}
Spine: {{ spine_exam or EXAM_SPINE_DEFAULT }}

{# === SITE-SPECIFIC EXAM (breast) === #}
{% if laterality %}Laterality: {{ laterality }}{% endif %}
{% if treatment_phase %}Treatment phase: {{ treatment_phase }}{% endif %}
{% if right_breast_exam %}Right breast: {{ right_breast_exam }}{% endif %}
{% if left_breast_exam %}Left breast: {{ left_breast_exam }}{% endif %}
{% if axillary_exam %}Axilla: {{ axillary_exam }}{% endif %}
{% if post_op_site_exam %}Post-op site: {{ post_op_site_exam }}{% endif %}
{% if lymphedema_status %}Lymphedema: {{ lymphedema_status }}{% endif %}
{% if receptor_status_summary %}Receptor status: {{ receptor_status_summary }}{% endif %}
{% if nodal_pathological_status %}Nodal pathology: {{ nodal_pathological_status }}{% endif %}
{% if field_components_planned %}Field components planned: {{ field_components_planned }}{% endif %}
{% if additional_site_notes %}{{ additional_site_notes }}{% endif %}

{{ IMPRESSION_HEADER }}
{{ impression }}
{% if cancer_staging %}Stage: {{ cancer_staging }}{% endif %}
{% if risk_stratification %}Risk: {{ risk_stratification }}{% endif %}

{{ PLAN_HEADER }}

{{ DISCUSSION_PREAMBLE }}

{% if discussion_summary %}{{ discussion_summary }}{% endif %}

{{ TREATMENT_DECISION_PREAMBLE }}

{% if treatment_decision_summary %}{{ treatment_decision_summary }}{% endif %}

{{ RT_BLOCK_HEADER }}
{% if rt_intent %}{{ RT_INTENT_LINE }}{% endif %}
{% if rt_dose_gy and rt_fractions %}{{ RT_DOSE_LINE }}{% endif %}
{% if rt_technique %}{{ RT_TECHNIQUE_LINE }}{% endif %}
{% if concurrent_systemic_therapy %}{{ RT_CONCURRENT_LINE }}{% endif %}
{% for phase in additional_phases %}- {{ phase }}
{% endfor %}
{% if patient_specific_modifications %}Note: {{ patient_specific_modifications }}{% endif %}

{{ EARLY_TOX_PREAMBLE }}
{% for t in early_toxicities %}- {{ t.text }}
{% endfor %}

{{ LATE_TOX_PREAMBLE }}
{% for t in late_toxicities %}- {{ t.text }}
{% endfor %}

{{ RT_PREPARATION }}

{% if simulation_status %}{{ simulation_status }}{% endif %}

{{ FINAL_CONSENT }}

{% if orders %}
{{ ORDERS_HEADER }}
{% for o in orders %}- {{ o }}
{% endfor %}
{% endif %}

{% if onward_referrals %}
{{ REFERRALS_HEADER }}
{% for r in onward_referrals %}- {{ r }}
{% endfor %}
{% endif %}

{% if advice %}
{{ ADVICE_HEADER }}
{% for a in advice %}- {{ a }}
{% endfor %}
{% endif %}

{{ CLOSING }}
$LAYOUT$
WHERE template_code = 'RS_BREAST';

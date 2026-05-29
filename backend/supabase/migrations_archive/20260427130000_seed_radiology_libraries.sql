-- Seed radiology plan + toxicity libraries from references/dharan prompts/02-06.
-- Idempotent: ON CONFLICT (template_id, plan_code|toxicity_code) DO NOTHING.
-- Conditional triggers derived from id prefix:
--   GY_BR_*  -> BRACHYTHERAPY
--   BR_SCF_* -> SCF
--   BR_LH_*  -> LEFT_HEART
--
-- After this migration applies, run a one-off reassembly so the
-- libraries are substituted into templates.assembled_full_prompt:
--   cd backend && source venv/bin/activate && python -m scripts.reassemble_radiology_templates
--
-- Wrapped in DO block: skips entirely if no RS_* templates exist (e.g. on
-- environments where radiology templates haven't been seeded yet).

DO $seed_rad$
BEGIN

IF NOT EXISTS (
  SELECT 1 FROM templates WHERE template_code IN ('RS_RECTUM','RS_PROSTATE','RS_HN','RS_GYN','RS_BREAST')
) THEN
  RAISE NOTICE 'Radiology templates (RS_*) not present — skipping radiology library seed.';
  RETURN;
END IF;

-- ============================================================================
-- PLAN LIBRARY
-- ============================================================================

-- ---- RS_RECTUM ----
INSERT INTO radiology_plan_library
    (template_id, plan_code, plan_name, rt_intent, rt_indication, rt_dose_gy, rt_fractions, rt_dose_per_fraction_gy, rt_weeks, rt_technique, concurrent_systemic_therapy, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_PLAN_LCRT', 'Long-course chemoradiation (neoadjuvant)', 'Neoadjuvant', 'Locally advanced rectal cancer (cT3-4 or N+)', '50.4', '28', '1.8', '5.5', 'VMAT/IMRT', 'Concurrent capecitabine 825 mg/m2 BD on RT days', 1),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_PLAN_SCRT', 'Short-course RT (neoadjuvant)', 'Neoadjuvant', 'Locally advanced rectal cancer, candidate for short-course schedule', '25', '5', '5', '1', '3D-CRT/VMAT', '', 2),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_PLAN_TNT', 'Total Neoadjuvant Therapy', 'Neoadjuvant', 'Locally advanced rectal cancer with high-risk features, TNT approach', '50.4', '28', '1.8', '5.5', 'VMAT/IMRT', 'Concurrent capecitabine; sequential FOLFOX or CAPOX', 3),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_PLAN_ADJ', 'Adjuvant chemoradiation (post-op)', 'Adjuvant', 'Post-operative rectal cancer with high-risk features', '50.4', '28', '1.8', '5.5', 'VMAT/IMRT', 'Concurrent capecitabine 825 mg/m2 BD on RT days', 4),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_PLAN_PALL_30_10', 'Palliative pelvic RT (10 fraction)', 'Palliative', 'Symptomatic primary or metastatic disease', '30', '10', '3', '2', '3D-CRT', '', 5),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_PLAN_PALL_20_5', 'Palliative pelvic RT (5 fraction)', 'Palliative', 'Symptomatic disease, frail patient or short prognosis', '20', '5', '4', '1', '3D-CRT', '', 6)
ON CONFLICT (template_id, plan_code) DO NOTHING;

-- ---- RS_PROSTATE ----
INSERT INTO radiology_plan_library
    (template_id, plan_code, plan_name, rt_intent, rt_indication, rt_dose_gy, rt_fractions, rt_dose_per_fraction_gy, rt_weeks, rt_technique, concurrent_systemic_therapy, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_PLAN_CONV', 'Conventional fractionation, definitive', 'Curative', 'Localized prostate cancer, definitive RT', '78', '39', '2', '8', 'VMAT/IMRT with daily IGRT', 'ADT per risk category', 1),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_PLAN_MODHYPO_60_20', 'Moderate hypofractionation (CHHIP)', 'Curative', 'Localized prostate cancer, moderate hypofractionation', '60', '20', '3', '4', 'VMAT/IMRT with daily IGRT', 'ADT per risk category', 2),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_PLAN_SBRT', 'Ultra-hypofractionation / SBRT', 'Curative', 'Low or favorable-intermediate-risk prostate cancer, SBRT', '36.25', '5', '7.25', '2', 'SBRT (VMAT) with daily IGRT, fiducial markers', '', 3),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_PLAN_ADJUVANT', 'Adjuvant post-prostatectomy', 'Adjuvant', 'Post-prostatectomy with adverse pathology features', '66', '33', '2', '6.5', 'VMAT/IMRT with daily IGRT', '', 4),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_PLAN_SALVAGE', 'Salvage post-prostatectomy', 'Salvage', 'Biochemical recurrence after prostatectomy', '66', '33', '2', '6.5', 'VMAT/IMRT with daily IGRT', 'ADT may be added based on risk', 5),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_PLAN_PALL_30_10', 'Palliative prostate / metastatic site (10 fraction)', 'Palliative', 'Symptomatic primary or bone metastasis', '30', '10', '3', '2', '3D-CRT', '', 6),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_PLAN_PALL_8_1', 'Palliative single fraction (bone met)', 'Palliative', 'Painful bone metastasis', '8', '1', '8', '0.2', '3D-CRT', '', 7)
ON CONFLICT (template_id, plan_code) DO NOTHING;

-- ---- RS_HN ----
INSERT INTO radiology_plan_library
    (template_id, plan_code, plan_name, rt_intent, rt_indication, rt_dose_gy, rt_fractions, rt_dose_per_fraction_gy, rt_weeks, rt_technique, concurrent_systemic_therapy, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_PLAN_DEF_CRT', 'Definitive chemoradiation', 'Curative', 'Locally advanced HN cancer, definitive CRT', '70', '35', '2', '7', 'VMAT/IMRT with daily IGRT', 'Concurrent cisplatin 100 mg/m2 every 3 weeks (3 cycles)', 1),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_PLAN_DEF_RT', 'Definitive RT alone (early stage)', 'Curative', 'Early-stage HN cancer, RT alone', '66', '33', '2', '6.5', 'VMAT/IMRT with daily IGRT', '', 2),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_PLAN_POSTOP_HIGH', 'Post-op high-risk (with concurrent chemo)', 'Adjuvant', 'Post-op HN with positive margins or extranodal extension', '66', '33', '2', '6.5', 'VMAT/IMRT with daily IGRT', 'Concurrent cisplatin 100 mg/m2 every 3 weeks', 3),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_PLAN_POSTOP_INT', 'Post-op intermediate-risk', 'Adjuvant', 'Post-op HN with intermediate-risk pathology', '60', '30', '2', '6', 'VMAT/IMRT with daily IGRT', '', 4),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_PLAN_PALL_30_10', 'Palliative HN (10 fraction)', 'Palliative', 'Locally advanced or metastatic HN, symptom control', '30', '10', '3', '2', '3D-CRT/VMAT', '', 5),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_PLAN_PALL_QUADSHOT', 'Palliative QUAD shot', 'Palliative', 'Symptomatic HN cancer, frail patient', '14', '4', '3.5', '0.5', '3D-CRT/VMAT', '', 6)
ON CONFLICT (template_id, plan_code) DO NOTHING;

-- ---- RS_GYN ----
INSERT INTO radiology_plan_library
    (template_id, plan_code, plan_name, rt_intent, rt_indication, rt_dose_gy, rt_fractions, rt_dose_per_fraction_gy, rt_weeks, rt_technique, concurrent_systemic_therapy, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_PLAN_CERVIX_DEF_CRT', 'Cervix definitive chemoradiation + brachy', 'Curative', 'Locally advanced cervical cancer, definitive CRT', '45', '25', '1.8', '5', 'VMAT/IMRT with daily IGRT', 'Concurrent weekly cisplatin 40 mg/m2 (5–6 cycles)', 1),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_PLAN_CERVIX_50', 'Cervix definitive (50 Gy variant) + brachy', 'Curative', 'Locally advanced cervical cancer with parametrial/nodal disease', '50', '25', '2', '5', 'VMAT/IMRT with daily IGRT', 'Concurrent weekly cisplatin 40 mg/m2', 2),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_PLAN_CERVIX_POSTOP', 'Cervix post-op adjuvant', 'Adjuvant', 'Post-op cervical cancer with risk factors', '50.4', '28', '1.8', '5.5', 'VMAT/IMRT', 'Concurrent cisplatin if high-risk features', 3),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_PLAN_ENDOM_ADJ', 'Endometrial adjuvant EBRT + vault brachy', 'Adjuvant', 'Post-op endometrial cancer with intermediate/high-risk pathology', '45', '25', '1.8', '5', 'VMAT/IMRT', '', 4),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_PLAN_VAULT_BRACHY_ALONE', 'Vaginal vault brachytherapy alone', 'Adjuvant', 'Post-op endometrial cancer, vault brachy alone', '21', '3', '7', '1.5', 'HDR vaginal vault brachytherapy', '', 5),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_PLAN_PALL_30_10', 'Palliative pelvic RT (10 fraction)', 'Palliative', 'Symptomatic pelvic disease, bleeding control', '30', '10', '3', '2', '3D-CRT/VMAT', '', 6)
ON CONFLICT (template_id, plan_code) DO NOTHING;

-- ---- RS_BREAST ----
INSERT INTO radiology_plan_library
    (template_id, plan_code, plan_name, rt_intent, rt_indication, rt_dose_gy, rt_fractions, rt_dose_per_fraction_gy, rt_weeks, rt_technique, concurrent_systemic_therapy, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_WB_HYPO_40_15', 'Whole breast hypofractionated (UK START)', 'Adjuvant', 'Post-lumpectomy whole-breast RT, hypofractionation', '40', '15', '2.67', '3', 'VMAT/3D-CRT, tangents', '', 1),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_WB_HYPO_42_16', 'Whole breast hypofractionated (42.5 Gy)', 'Adjuvant', 'Post-lumpectomy whole-breast RT, hypofractionation', '42.5', '16', '2.66', '3.2', 'VMAT/3D-CRT, tangents', '', 2),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_WB_CONV_50_25', 'Whole breast conventional fractionation', 'Adjuvant', 'Post-lumpectomy whole-breast RT, conventional', '50', '25', '2', '5', 'VMAT/3D-CRT, tangents', '', 3),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_WB_FAST_FORWARD', 'FAST-Forward 5-fraction', 'Adjuvant', 'Post-lumpectomy whole-breast RT, ultra-hypofractionation', '26', '5', '5.2', '1', 'VMAT/3D-CRT, tangents', '', 4),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_PMRT_HYPO', 'Post-mastectomy hypofractionated', 'Adjuvant', 'Post-mastectomy chest wall ± nodal RT', '40', '15', '2.67', '3', 'VMAT/3D-CRT with bolus over chest wall', '', 5),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_PMRT_CONV', 'Post-mastectomy conventional', 'Adjuvant', 'Post-mastectomy chest wall ± nodal RT', '50', '25', '2', '5', 'VMAT/3D-CRT with bolus over chest wall', '', 6),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_APBI_40_15', 'Accelerated partial breast irradiation', 'Adjuvant', 'Low-risk post-lumpectomy, partial breast', '40', '15', '2.67', '3', 'VMAT/IMRT partial breast', '', 7),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_PALL_30_10', 'Palliative breast / chest wall (10 fraction)', 'Palliative', 'Symptomatic locally advanced or metastatic disease', '30', '10', '3', '2', '3D-CRT', '', 8),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_PLAN_PALL_8_1', 'Palliative single fraction (bone met)', 'Palliative', 'Painful bone metastasis', '8', '1', '8', '0.2', '3D-CRT', '', 9)
ON CONFLICT (template_id, plan_code) DO NOTHING;


-- ============================================================================
-- TOXICITY LIBRARY
-- ============================================================================

-- ---- RS_RECTUM (early) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_E01', 'early', 'Fatigue, weight loss, and discomfort or pain at the site of radiation.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_E02', 'early', 'Skin irritation, erythema, and desquamation in the perineal and gluteal region.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_E03', 'early', 'Anorexia, nausea, and occasional vomiting.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_E04', 'early', 'Abdominal distension, change in bowel habits, loose stools, and diarrhea.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_E05', 'early', 'Rectal or anal discharge, bleeding, and tenesmus.', NULL, 5),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_E06', 'early', 'Urinary frequency, urgency, nocturia, dysuria, and occasional hematuria.', NULL, 6),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_E07', 'early', 'Anemia, leukopenia, and thrombocytopenia, particularly when concurrent chemotherapy is given.', NULL, 7),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_E08', 'early', 'Risk of luminal obstruction, perforation, or bleeding.', NULL, 8)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_RECTUM (late) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L01', 'late', 'Skin atrophy, pigmentation, telangiectasia, and rarely ulceration.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L02', 'late', 'Subcutaneous tissue fibrosis, lymphedema, and rarely necrosis.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L03', 'late', 'Chronic changes in bowel movement, intermittent diarrhea, cramps, colic, and bloating.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L04', 'late', 'Rectal discharge or bleeding, weakness of the anal sphincter, with possible urgency or incontinence.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L05', 'late', 'Long-term urinary frequency and urgency, nocturia, dysuria, and hematuria.', NULL, 5),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L06', 'late', 'Impaired sexual function including vaginal dryness and stenosis or erectile dysfunction.', NULL, 6),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L07', 'late', 'Impaired fertility for patients of child-bearing age.', NULL, 7),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L08', 'late', 'Increased risk of pelvic bone insufficiency fracture and rarely nerve damage.', NULL, 8),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L09', 'late', 'Risk of luminal obstruction, perforation, or fistula formation.', NULL, 9),
((SELECT id FROM templates WHERE template_code='RS_RECTUM'), 'RC_L10', 'late', 'Small but real risk of radiation-induced secondary malignancy.', NULL, 10)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_PROSTATE (early) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_E01', 'early', 'Fatigue.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_E02', 'early', 'Urinary symptoms including frequency, urgency, weakened stream, dysuria, and rarely urinary retention requiring catheterization.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_E03', 'early', 'Bowel symptoms including frequency, urgency, looser stools, and diarrhea.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_E04', 'early', 'Mild perineal or peri-anal skin irritation.', NULL, 4)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_PROSTATE (late) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L01', 'late', 'Erectile dysfunction and other forms of sexual dysfunction.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L02', 'late', 'Long-term urinary symptoms including frequency, urgency, and nocturia.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L03', 'late', 'Long-term bowel symptoms including altered habit and urgency.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L04', 'late', 'Cystitis and proctitis, including hematuria and hematochezia.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L05', 'late', 'Urinary or fecal incontinence.', NULL, 5),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L06', 'late', 'Urethral stricture.', NULL, 6),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L07', 'late', 'Penile or testicular shrinkage and infertility.', NULL, 7),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L08', 'late', 'Approximately 1% or lower risk of a serious side effect that may require surgical intervention.', NULL, 8),
((SELECT id FROM templates WHERE template_code='RS_PROSTATE'), 'PR_L09', 'late', 'Small but real risk of radiation-induced secondary malignancy.', NULL, 9)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_HN (early) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_E01', 'early', 'Fatigue, weight loss, dehydration, and discomfort or pain at the site of radiation.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_E02', 'early', 'Skin irritation, itching, erythema, desquamation, edema, and rarely ulceration, necrosis, or bleeding.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_E03', 'early', 'Oral, pharyngeal, and laryngeal mucositis with erythema, irritation, pain, edema, discharge, and rarely ulceration, necrosis, or bleeding.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_E04', 'early', 'Mouth dryness, thick sticky saliva, altered or metallic taste, anorexia, nausea, and vomiting.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_E05', 'early', 'Odynophagia and dysphagia, possibly requiring narcotic analgesics, IV fluids, or feeding tube; risk of pharyngeal or oesophageal obstruction, ulceration, perforation, fistula, and bleeding.', NULL, 5),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_E06', 'early', 'Hoarseness, cough, dyspnoea, stridor, or haemoptysis, with rare need for tracheostomy or intubation.', NULL, 6),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_E07', 'early', 'Otitis, ear pain, discharge, tinnitus, and hearing diminution.', NULL, 7),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_E08', 'early', 'Increased tearing, dry eye, conjunctivitis, photophobia, corneal irritation, and impaired visual acuity or visual fields.', NULL, 8)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_HN (late) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L01', 'late', 'Skin atrophy, pigmentation, telangiectasia, and rarely ulceration, with possible localized hair loss corresponding to the radiation field.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L02', 'late', 'Subcutaneous tissue fibrosis, induration, contracture, lymphedema, and rarely necrosis.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L03', 'late', 'Persistent dry mouth and altered taste.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L04', 'late', 'Chronic oral, pharyngeal, and laryngeal mucosal atrophy, dryness, telangiectasia, and rarely ulceration, necrosis, or fistula.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L05', 'late', 'Aspiration and difficulty or pain in swallowing, possibly requiring feeding tube or dilation.', NULL, 5),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L06', 'late', 'Persistent hoarseness, arytenoid edema, chondritis, and rarely laryngeal necrosis.', NULL, 6),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L07', 'late', 'Bone changes (e.g., jaw, maxilla) including sclerosis, pain, osteoradionecrosis, and rarely fracture.', NULL, 7),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L08', 'late', 'Joint stiffness (e.g., jaw, shoulder), pain, and limitation of movement.', NULL, 8),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L09', 'late', 'Radiation-induced myelopathy with numbness, pain, or weakness in regions supplied by the affected spinal cord level.', NULL, 9),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L10', 'late', 'Radiation-induced plexopathy with numbness, pain, or weakness in the neck, shoulder, or arm.', NULL, 10),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L11', 'late', 'Dry eye, cataract, corneal ulceration, and impaired visual acuity or visual fields.', NULL, 11),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L12', 'late', 'Chronic ear pain, discharge, tinnitus, and hearing loss.', NULL, 12),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L13', 'late', 'Fibrosis of the upper portion of the lung.', NULL, 13),
((SELECT id FROM templates WHERE template_code='RS_HN'), 'HN_L14', 'late', 'Small but real risk of radiation-induced secondary malignancy.', NULL, 14)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_GYN (early) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_E01', 'early', 'Fatigue.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_E02', 'early', 'Dysuria, urinary frequency, urinary urgency, and cystitis.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_E03', 'early', 'Diarrhoea, proctitis, rectal bleeding, and faecal urgency.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_E04', 'early', 'Urinary or faecal incontinence.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_E05', 'early', 'Nausea and vomiting.', NULL, 5),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_E06', 'early', 'Skin reaction in the perineal and gluteal region.', NULL, 6),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_BR_E01', 'early', 'Brachytherapy is performed in the operating room under anaesthesia.', 'BRACHYTHERAPY', 7),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_BR_E02', 'early', 'Risk of infection at the applicator site during or after brachytherapy.', 'BRACHYTHERAPY', 8),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_BR_E03', 'early', 'Skin or vaginal mucosal irritation related to brachytherapy applicators.', 'BRACHYTHERAPY', 9),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_BR_E04', 'early', 'Risk of deep vein thrombosis or pulmonary embolism related to peri-procedural immobilization for brachytherapy.', 'BRACHYTHERAPY', 10),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_BR_E05', 'early', 'Bleeding upon brachytherapy applicator removal.', 'BRACHYTHERAPY', 11)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_GYN (late) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_L01', 'late', 'Risk of fistula formation, bowel obstruction, and stricture.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_L02', 'late', 'Vaginal dryness and vaginal stenosis.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_L03', 'late', 'Weakening of pelvic bones with risk of insufficiency fracture.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_L04', 'late', 'Sterility and premature menopause for premenopausal patients.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_L05', 'late', 'Long-term urinary symptoms including frequency, urgency, and rarely hematuria.', NULL, 5),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_L06', 'late', 'Long-term bowel symptoms including altered habit, urgency, and rarely hematochezia.', NULL, 6),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_L07', 'late', 'Skin atrophy, pigmentation, and telangiectasia in the irradiated region.', NULL, 7),
((SELECT id FROM templates WHERE template_code='RS_GYN'), 'GY_L08', 'late', 'Small but real risk of radiation-induced secondary malignancy.', NULL, 8)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_BREAST (early) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_E01', 'early', 'Fatigue, mild dehydration, and discomfort or pain at the site of radiation.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_E02', 'early', 'Skin irritation, itching, erythema, desquamation, edema, and rarely ulceration, necrosis, or bleeding.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_E03', 'early', 'Lymphedema or swelling of the arm or forearm on the side of radiotherapy.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_E04', 'early', 'Mild breast tenderness, heaviness, and intermittent shooting pains.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_SCF_E01', 'early', 'Odynophagia and dysphagia related to oesophageal dose, possibly requiring analgesics or dietary modification; rarely oesophageal obstruction, ulceration, or perforation.', 'SCF', 5)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

-- ---- RS_BREAST (late) ----
INSERT INTO radiology_toxicity_library
    (template_id, toxicity_code, phase, text, conditional_trigger, display_order)
VALUES
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_L01', 'late', 'Skin atrophy, pigmentation, telangiectasia, and rarely ulceration, with possible localized hair loss in the radiation field.', NULL, 1),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_L02', 'late', 'Subcutaneous tissue fibrosis, induration, contracture, lymphedema, and rarely necrosis.', NULL, 2),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_L03', 'late', 'Long-term breast firmness, retraction, and altered breast cosmesis.', NULL, 3),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_L04', 'late', 'Fibrosis of the portion of the lung immediately adjacent to the breast or chest wall radiotherapy field.', NULL, 4),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_L05', 'late', 'Small but real risk of radiation-induced secondary malignancy.', NULL, 5),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_SCF_L01', 'late', 'Radiation-induced brachial plexopathy with numbness, pain, or weakness in the neck, shoulder, or arm.', 'SCF', 6),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_SCF_L02', 'late', 'Rare risk of rib fracture in the irradiated region.', 'SCF', 7),
((SELECT id FROM templates WHERE template_code='RS_BREAST'), 'BR_LH_L01', 'late', 'Very rare risk of major coronary events related to incidental cardiac dose; mitigation strategies such as deep inspiration breath-hold are used to minimize this.', 'LEFT_HEART', 8)
ON CONFLICT (template_id, toxicity_code) DO NOTHING;

END $seed_rad$;

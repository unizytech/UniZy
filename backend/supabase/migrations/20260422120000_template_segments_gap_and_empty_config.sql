-- Admin-controlled per-template, per-segment configuration for:
--   1) Which fields are tracked by the extraction-gaps API
--      (GET /api/v1/ehr/extraction-gaps/{extraction_id})
--   2) Which segments are included in the empty-extraction payload
--      (GET /api/v1/ehr/template-schema)
--
-- Both columns are nullable so day-1 behavior is preserved for the external
-- webapp consuming these public EHR APIs: a NULL row means "legacy default".

ALTER TABLE template_segments
ADD COLUMN IF NOT EXISTS gap_analysis_fields_json JSONB NULL;

ALTER TABLE template_segments
ADD COLUMN IF NOT EXISTS include_in_empty_payload BOOLEAN NULL;

COMMENT ON COLUMN template_segments.gap_analysis_fields_json IS
'Dot-path list of fields tracked by extraction-gaps. NULL = default (all leaves of recognized shape). [] = segment excluded from gap analysis. ["spo2","pulse"] = only those leaves tracked. Dot-paths: "dm.status", "pnd.present", etc.';

COMMENT ON COLUMN template_segments.include_in_empty_payload IS
'Admin opt-in to trim the empty-extraction payload. NULL = legacy (segment included). FALSE = segment omitted from both the segments list and empty_extraction object. TRUE = explicitly included.';

-- Seed block: preserve byte-for-byte responses for the 4 segments that had
-- hardcoded field lists (_VITALS_FIELDS / _NUTRITIONAL_FIELDS / _ALLERGY_FIELDS
-- / _COMORBIDITY_KEYS in backend/routers/ehr_integration.py).

-- VITALS: ["temperature", "pulse", "respiratory_rate", "blood_pressure", "spo2"]
UPDATE template_segments ts
SET gap_analysis_fields_json = '["temperature","pulse","respiratory_rate","blood_pressure","spo2"]'::jsonb
FROM segment_definitions sd
WHERE ts.segment_id = sd.id
  AND sd.segment_code = 'VITALS'
  AND ts.gap_analysis_fields_json IS NULL;

-- NUTRITIONAL_SCREENING: ["height", "weight", "bmi", "bmi_flag"]
UPDATE template_segments ts
SET gap_analysis_fields_json = '["height","weight","bmi","bmi_flag"]'::jsonb
FROM segment_definitions sd
WHERE ts.segment_id = sd.id
  AND sd.segment_code = 'NUTRITIONAL_SCREENING'
  AND ts.gap_analysis_fields_json IS NULL;

-- ALLERGY: ["has_allergy", "details"]
UPDATE template_segments ts
SET gap_analysis_fields_json = '["has_allergy","details"]'::jsonb
FROM segment_definitions sd
WHERE ts.segment_id = sd.id
  AND sd.segment_code = 'ALLERGY'
  AND ts.gap_analysis_fields_json IS NULL;

-- COMORBIDITIES: the 12 legacy keys. _COMORBIDITY_WITH_SINCE = {dm, ht, dlp,
-- history_of_copd} track both .status and .since; the rest track only .status.
UPDATE template_segments ts
SET gap_analysis_fields_json = '[
  "dm.status","dm.since",
  "ht.status","ht.since",
  "dlp.status","dlp.since",
  "history_of_copd.status","history_of_copd.since",
  "smoking.status",
  "previous_mi.status",
  "renal_failure.status",
  "alcohol_intake.status",
  "history_of_cva.status",
  "previous_stent.status",
  "tobacco_chewing.status",
  "peripheral_vascular_disease.status"
]'::jsonb
FROM segment_definitions sd
WHERE ts.segment_id = sd.id
  AND sd.segment_code = 'COMORBIDITIES'
  AND ts.gap_analysis_fields_json IS NULL;

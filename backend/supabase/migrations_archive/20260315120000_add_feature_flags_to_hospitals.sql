-- Add feature_flags JSONB column to hospitals table
-- Stores per-hospital feature toggles for frontend gating

ALTER TABLE hospitals
ADD COLUMN IF NOT EXISTS feature_flags jsonb NOT NULL DEFAULT '{
  "care_plan": true,
  "merge": true,
  "interventions": true,
  "upload": true,
  "ocr": false,
  "edit_prescription": true,
  "edit_investigation": true,
  "edit_record": true,
  "patient_qa": true,
  "doctor_qa": true,
  "template_configuration": true,
  "patient_registration": true,
  "billing": false,
  "nudge_plan": false,
  "iris": false,
  "triage_support": false
}'::jsonb;

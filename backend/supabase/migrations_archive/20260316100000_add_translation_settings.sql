-- Add translation language settings to doctors and hospitals
-- Add translation_model to processing_modes (follows emotion_model, triage_model pattern)

-- Doctor-level translation language (overrides hospital default)
ALTER TABLE doctors
ADD COLUMN IF NOT EXISTS translation_language VARCHAR(20) DEFAULT NULL;

COMMENT ON COLUMN doctors.translation_language IS 'Target Indic language for post-extraction translation (e.g., tamil, hindi, telugu). NULL = no translation.';

-- Hospital-level default translation language
ALTER TABLE hospitals
ADD COLUMN IF NOT EXISTS default_translation_language VARCHAR(20) DEFAULT NULL;

COMMENT ON COLUMN hospitals.default_translation_language IS 'Default translation language for all doctors in this hospital. Doctor setting overrides this.';

-- Add translation feature flag to hospitals (merge into existing feature_flags JSONB)
UPDATE hospitals
SET feature_flags = COALESCE(feature_flags, '{}'::jsonb) || '{"translation": false}'::jsonb
WHERE NOT (COALESCE(feature_flags, '{}'::jsonb) ? 'translation');

-- Add translation_model to processing_modes (same pattern as emotion_model, triage_model)
ALTER TABLE processing_modes
ADD COLUMN IF NOT EXISTS translation_model VARCHAR(100) DEFAULT 'gemini-2.5-flash';

COMMENT ON COLUMN processing_modes.translation_model IS 'Model used for post-extraction Indic language translation';

-- Set translation_model per processing mode
UPDATE processing_modes SET translation_model = 'gemini-2.5-flash' WHERE mode_code = 'fast';
UPDATE processing_modes SET translation_model = 'gemini-2.5-flash' WHERE mode_code = 'default';
UPDATE processing_modes SET translation_model = 'gemini-2.5-pro' WHERE mode_code = 'thorough';
UPDATE processing_modes SET translation_model = 'gemini-2.5-flash' WHERE mode_code = 'ultra';
UPDATE processing_modes SET translation_model = 'gemini-2.5-flash' WHERE mode_code = 'ultra_fast';

-- Add 'translation' to use_for array in models_master for relevant Gemini models
UPDATE models_master
SET use_for = array_append(use_for, 'translation')
WHERE model_id IN ('gemini-2.5-flash', 'gemini-2.5-pro')
  AND NOT ('translation' = ANY(COALESCE(use_for, ARRAY[]::text[])));

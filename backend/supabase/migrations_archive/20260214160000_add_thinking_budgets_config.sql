-- Add thinking_budgets JSONB column to models_master
-- Stores per-call-type thinking budget configuration per model
-- Example: {"transcription": 0, "extraction": 1024, "emotion": 0, "triage": 2048, "consultation_insights": 1024}
ALTER TABLE models_master ADD COLUMN IF NOT EXISTS thinking_budgets jsonb;

-- Set default thinking budgets for Gemini 2.5 Flash (the primary model)
UPDATE models_master SET thinking_budgets = '{
    "transcription": 0,
    "extraction": 1024,
    "emotion": 0,
    "triage": 2048,
    "consultation_insights": 1024,
    "merge": 1024
}'::jsonb
WHERE model_id = 'gemini-2.5-flash';

-- Gemini 2.5 Flash native audio (same budgets)
UPDATE models_master SET thinking_budgets = '{
    "transcription": 0,
    "extraction": 1024,
    "emotion": 0,
    "triage": 2048,
    "consultation_insights": 1024,
    "merge": 1024
}'::jsonb
WHERE model_id = 'gemini-2.5-flash-native-audio-preview';

-- Gemini 2.5 Pro (higher budgets since it benefits more from thinking)
UPDATE models_master SET thinking_budgets = '{
    "transcription": 0,
    "extraction": 2048,
    "emotion": 0,
    "triage": 4096,
    "consultation_insights": 2048,
    "merge": 2048
}'::jsonb
WHERE model_id = 'gemini-2.5-pro';

-- Gemini 3 Pro
UPDATE models_master SET thinking_budgets = '{
    "transcription": 0,
    "extraction": 2048,
    "emotion": 0,
    "triage": 4096,
    "consultation_insights": 2048,
    "merge": 2048
}'::jsonb
WHERE model_id IN ('gemini-3-pro', 'gemini-3-pro-preview');

COMMENT ON COLUMN models_master.thinking_budgets IS 'Per-call-type thinking budget config. Keys: transcription, extraction, emotion, triage, consultation_insights, merge. Value 0 = disabled, null key = model default.';

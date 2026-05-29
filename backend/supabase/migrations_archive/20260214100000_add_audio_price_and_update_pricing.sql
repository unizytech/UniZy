-- Add audio_price_per_minute column to models_master
ALTER TABLE models_master
ADD COLUMN IF NOT EXISTS audio_price_per_minute NUMERIC DEFAULT NULL;

-- Seed audio pricing for models that support transcription
UPDATE models_master SET audio_price_per_minute = 0.001 WHERE model_id = 'gemini-2.5-flash';
UPDATE models_master SET audio_price_per_minute = 0.001 WHERE model_id = 'gemini-2.0-flash';
UPDATE models_master SET audio_price_per_minute = 0.001 WHERE model_id = 'gemini-2.0-flash-lite';
UPDATE models_master SET audio_price_per_minute = 0.00625 WHERE model_id = 'gemini-2.5-pro';
UPDATE models_master SET audio_price_per_minute = 0.00625 WHERE model_id = 'gemini-3-pro';
UPDATE models_master SET audio_price_per_minute = 0.00625 WHERE model_id = 'gemini-3-pro-preview';

-- Update pricing to current Feb 2026 rates
-- Gemini 2.5 Flash
UPDATE models_master SET
  input_price_per_million = 0.30,
  output_price_per_million = 2.50,
  cached_input_price_per_million = 0.03
WHERE model_id = 'gemini-2.5-flash';

-- Claude Haiku 4.5
UPDATE models_master SET
  input_price_per_million = 1.00,
  output_price_per_million = 5.00,
  cached_input_price_per_million = 0.10
WHERE model_id = 'claude-haiku-4-5-20251001';

-- Claude Opus 4.5
UPDATE models_master SET
  input_price_per_million = 5.00,
  output_price_per_million = 25.00,
  cached_input_price_per_million = 0.50
WHERE model_id = 'claude-opus-4-5-20251101';

-- GPT 4.1
UPDATE models_master SET
  input_price_per_million = 2.00,
  output_price_per_million = 8.00,
  cached_input_price_per_million = 0.50
WHERE model_id = 'gpt-4.1-2025-04-14';

-- Update updated_at for all changed rows
UPDATE models_master SET updated_at = now()
WHERE model_id IN (
  'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-lite',
  'gemini-2.5-pro', 'gemini-3-pro', 'gemini-3-pro-preview',
  'claude-haiku-4-5-20251001', 'claude-opus-4-5-20251101',
  'gpt-4.1-2025-04-14'
);

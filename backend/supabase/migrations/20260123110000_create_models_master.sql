-- Create models_master table for database-driven model management
CREATE TABLE models_master (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'gemini',
  tier TEXT NOT NULL DEFAULT 'standard',
  use_for TEXT[] NOT NULL DEFAULT '{}',
  input_price_per_million NUMERIC(10,4),
  output_price_per_million NUMERIC(10,4),
  cached_input_price_per_million NUMERIC(10,4),
  is_active BOOLEAN NOT NULL DEFAULT true,
  display_order INTEGER NOT NULL DEFAULT 100,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed data
INSERT INTO models_master (model_id, display_name, provider, tier, use_for, input_price_per_million, output_price_per_million, cached_input_price_per_million, display_order) VALUES
-- Gemini models (all use cases)
('gemini-3-pro', 'Gemini 3 Pro (Vertex AI)', 'gemini', 'premium', '{transcription,extraction,merge,triage,compare,emotion,insights}', 2.00, 12.00, 0.20, 10),
('gemini-3-pro-preview', 'Gemini 3 Pro Preview (Gemini API)', 'gemini', 'premium', '{transcription,extraction,merge,triage,compare,emotion,insights}', 2.00, 12.00, 0.20, 11),
('gemini-2.5-flash', 'Gemini 2.5 Flash (Recommended)', 'gemini', 'standard', '{transcription,extraction,merge,triage,compare,emotion,insights}', 0.15, 0.60, 0.0375, 20),
('gemini-2.5-pro', 'Gemini 2.5 Pro', 'gemini', 'premium', '{transcription,extraction,merge,triage,compare,emotion,insights}', 1.25, 10.00, 0.3125, 21),
('gemini-2.5-flash-lite', 'Gemini 2.5 Flash Lite', 'gemini', 'lite', '{transcription,extraction,merge,triage,compare,emotion,insights}', 0.075, 0.30, 0.01875, 22),
('gemini-2.0-flash', 'Gemini 2.0 Flash', 'gemini', 'standard', '{transcription,extraction,merge,triage,compare,emotion,insights}', 0.10, 0.40, 0.025, 30),
('gemini-2.0-flash-lite', 'Gemini 2.0 Flash Lite', 'gemini', 'lite', '{transcription,extraction,merge,triage,compare,emotion,insights}', 0.05, 0.20, 0.0125, 31),
-- Gemini Live models (transcription_live only)
('gemini-2.5-flash-native-audio-preview', 'Gemini 2.5 Flash Native Audio (Preview)', 'gemini', 'live', '{transcription_live}', 0.15, 0.60, 0.0375, 40),
('gemini-2.0-flash-live-001', 'Gemini 2.0 Flash Live', 'gemini', 'live', '{transcription_live}', 0.10, 0.40, 0.025, 41),
-- Claude models (extraction + merge only)
('claude-haiku-4-5-20251001', 'Claude Haiku 4.5', 'anthropic', 'standard', '{extraction,merge}', 0.80, 4.00, 0.08, 50),
('claude-sonnet-4-5-20250929', 'Claude Sonnet 4.5', 'anthropic', 'premium', '{extraction,merge}', 3.00, 15.00, 0.30, 51),
('claude-opus-4-5-20251101', 'Claude Opus 4.5', 'anthropic', 'premium', '{extraction,merge}', 15.00, 75.00, 1.50, 52),
-- OpenAI models (extraction + merge only)
('gpt-4.1-2025-04-14', 'GPT 4.1', 'openai', 'standard', '{extraction,merge}', 2.00, 8.00, 1.00, 60),
('gpt-5-mini-2025-08-07', 'GPT 5 Mini', 'openai', 'standard', '{extraction,merge}', 0.40, 1.60, 0.20, 61),
('gpt-5.2-2025-12-11', 'GPT 5.2', 'openai', 'premium', '{extraction,merge}', 5.00, 20.00, 2.50, 62);

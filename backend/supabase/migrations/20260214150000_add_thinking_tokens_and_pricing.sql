-- Add thinking token tracking to llm_usage_log
ALTER TABLE llm_usage_log ADD COLUMN IF NOT EXISTS thoughts_token_count integer;

-- Add thinking price to models_master
ALTER TABLE models_master ADD COLUMN IF NOT EXISTS thinking_price_per_million numeric(10,4);

-- Update thinking prices for models that support thinking/reasoning
-- Gemini 2.5 Flash: output=$0.60/M, thinking=$3.50/M
UPDATE models_master SET
    output_price_per_million = 0.60,
    thinking_price_per_million = 3.50
WHERE model_id = 'gemini-2.5-flash';

-- Gemini 2.5 Flash native audio: same thinking pricing
UPDATE models_master SET
    thinking_price_per_million = 3.50
WHERE model_id = 'gemini-2.5-flash-native-audio-preview';

-- Gemini 2.5 Pro: thinking=$10.00/M (same as output for pro)
UPDATE models_master SET
    thinking_price_per_million = 10.00
WHERE model_id = 'gemini-2.5-pro';

-- Gemini 3 Pro: thinking=$12.00/M (same as output)
UPDATE models_master SET
    thinking_price_per_million = 12.00
WHERE model_id LIKE 'gemini-3-pro%';

-- Add comment for clarity
COMMENT ON COLUMN llm_usage_log.thoughts_token_count IS 'Gemini thinking/reasoning tokens (separate from candidates_token_count)';
COMMENT ON COLUMN models_master.thinking_price_per_million IS 'Price per million thinking/reasoning tokens (Gemini 2.5+ models)';

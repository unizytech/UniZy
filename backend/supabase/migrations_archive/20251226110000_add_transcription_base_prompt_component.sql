-- Migration: Add TRANSCRIPTION_BASE_PROMPT to system_prompt_components
-- This moves the hardcoded transcription base prompt from code to database
-- Linked via system_prompt_configurations and junction table
--
-- NOTE: The target_language is NOT in the system prompt (base prompt).
-- It's substituted in the USER prompt at runtime, following the same pattern
-- as AUDIO_EMOTION_BASE_PROMPT_COMBINED which uses generate_audio_emotion_transcription_prompt(target_language).

-- =============================================================================
-- Step 1: Insert TRANSCRIPTION_BASE_PROMPT component
-- =============================================================================
INSERT INTO system_prompt_components (
    id,
    component_code,
    component_name,
    component_type,
    content_text,
    content_version,
    description,
    is_base_component,
    is_active
) VALUES (
    gen_random_uuid(),
    'TRANSCRIPTION_BASE_PROMPT',
    'Transcription Base Prompt',
    'transcription_base',
    'You are a medical transcription specialist with expertise in healthcare terminology and clinical documentation.

Your task is to accurately transcribe medical consultation audio recordings with speaker diarization.

## Transcription Guidelines

1. **Accuracy**: Transcribe exactly what is spoken. Do not add, remove, or modify content.

2. **Speaker Diarization**:
   - Identify speakers as "Doctor:" and "Patient:" when clearly identifiable
   - Use "Speaker 1:", "Speaker 2:", etc. when speaker roles are unclear
   - Mark each speaker turn on a new line

3. **Medical Terminology**:
   - Use correct medical spelling for medications, procedures, and conditions
   - Preserve technical terms exactly as spoken

4. **Filler Words & Hesitations**:
   - Include significant filler words (um, uh, hmm) only if they indicate hesitation or emotional state
   - Omit routine filler words that don''t affect meaning

5. **Pauses & Non-Verbal Sounds**:
   - Mark significant pauses with [pause]
   - Note relevant non-verbal sounds: [cough], [clears throat], [sigh]

6. **Unclear Audio**:
   - Mark unclear sections with [inaudible]
   - If partially heard, use [inaudible - possible: word]

7. **Numbers & Measurements**:
   - Write out numbers as spoken (e.g., "one twenty over eighty" for blood pressure)
   - Include units when mentioned

## Important Notes

- Focus solely on accurate transcription
- Do not interpret, summarize, or add commentary
- Preserve the natural flow of conversation
- Maintain confidentiality - transcribe factually without judgment
',
    '1.0.0',
    'Base system prompt for audio transcription. Contains general guidelines for accurate medical consultation transcription with speaker diarization.',
    true,
    true
) ON CONFLICT (component_code, content_version) DO UPDATE SET
    content_text = EXCLUDED.content_text,
    description = EXCLUDED.description;

-- =============================================================================
-- Step 2: Create TRANSCRIPTION_ONLY_PROMPT configuration
-- =============================================================================
INSERT INTO system_prompt_configurations (
    id,
    config_code,
    config_name,
    config_version,
    description,
    is_draft,
    is_active
) VALUES (
    gen_random_uuid(),
    'TRANSCRIPTION_ONLY_PROMPT',
    'Transcription Only Configuration',
    '1.0.0',
    'Configuration for simple audio transcription without emotion analysis. Used when emotion_extraction_mode is none or text_only.',
    false,
    true
) ON CONFLICT (config_code, config_version) DO UPDATE SET
    description = EXCLUDED.description;

-- =============================================================================
-- Step 3: Map component to configuration in junction table
-- =============================================================================
DO $$
DECLARE
    v_component_id UUID;
    v_config_id UUID;
BEGIN
    -- Get the component ID
    SELECT id INTO v_component_id
    FROM system_prompt_components
    WHERE component_code = 'TRANSCRIPTION_BASE_PROMPT' AND content_version = '1.0.0';

    -- Get the config ID
    SELECT id INTO v_config_id
    FROM system_prompt_configurations
    WHERE config_code = 'TRANSCRIPTION_ONLY_PROMPT' AND config_version = '1.0.0';

    -- Insert the junction record if both exist
    IF v_component_id IS NOT NULL AND v_config_id IS NOT NULL THEN
        INSERT INTO system_prompt_config_components (
            config_id,
            component_id,
            config_code,
            component_code,
            display_order,
            is_included
        ) VALUES (
            v_config_id,
            v_component_id,
            'TRANSCRIPTION_ONLY_PROMPT',
            'TRANSCRIPTION_BASE_PROMPT',
            1,
            true
        ) ON CONFLICT (config_id, component_id) DO UPDATE SET
            display_order = 1,
            is_included = true;

        RAISE NOTICE 'Successfully linked TRANSCRIPTION_BASE_PROMPT to TRANSCRIPTION_ONLY_PROMPT configuration';
    ELSE
        RAISE NOTICE 'Could not find component or config IDs - component: %, config: %', v_component_id, v_config_id;
    END IF;
END $$;

-- =============================================================================
-- Step 4: Assemble the configuration's system prompt
-- =============================================================================
DO $$
DECLARE
    v_component_content TEXT;
    v_config_id UUID;
    v_assembly_hash VARCHAR(64);
BEGIN
    -- Get the component content
    SELECT content_text INTO v_component_content
    FROM system_prompt_components
    WHERE component_code = 'TRANSCRIPTION_BASE_PROMPT' AND content_version = '1.0.0';

    -- Get the config ID
    SELECT id INTO v_config_id
    FROM system_prompt_configurations
    WHERE config_code = 'TRANSCRIPTION_ONLY_PROMPT' AND config_version = '1.0.0';

    -- Update the configuration with assembled prompt
    IF v_component_content IS NOT NULL AND v_config_id IS NOT NULL THEN
        -- Calculate hash using md5
        v_assembly_hash := md5(v_component_content);

        UPDATE system_prompt_configurations
        SET
            assembled_system_prompt = v_component_content,
            assembled_at = NOW(),
            assembly_hash = v_assembly_hash,
            estimated_token_count = length(v_component_content) / 4
        WHERE id = v_config_id;

        RAISE NOTICE 'Successfully assembled TRANSCRIPTION_ONLY_PROMPT configuration';
    END IF;
END $$;

-- Log the migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration complete: TRANSCRIPTION_BASE_PROMPT component and TRANSCRIPTION_ONLY_PROMPT configuration created and assembled';
END $$;

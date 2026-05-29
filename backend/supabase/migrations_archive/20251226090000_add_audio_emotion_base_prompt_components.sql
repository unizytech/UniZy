-- Migration: Add AUDIO_EMOTION_BASE_PROMPT_STANDALONE and AUDIO_EMOTION_BASE_PROMPT_COMBINED to database
-- This moves the hardcoded audio emotion base prompts from code to database
-- Linked via system_prompt_configurations and junction table

-- =============================================================================
-- Step 1: Insert AUDIO_EMOTION_BASE_PROMPT_STANDALONE component
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
    'AUDIO_EMOTION_BASE_PROMPT_STANDALONE',
    'Audio Emotion Analysis Base Prompt (Standalone)',
    'emotion_base',
    'You are a medical audio analyst specializing in voice-based emotional assessment.

You will receive audio of a medical consultation along with its transcript for context.

Your task is to analyze ONLY the voice characteristics - tone, prosody, pace, pitch, and speech patterns.

## Voice Analysis Guidelines

For each segment, provide:
1. **Assessment**: The level/category determination
2. **Rationale**: One-line explanation of WHY you made this assessment based on voice evidence and be specific. Cite quotes and behaviors when possible, and include time in consultation (e.g., "00:30-02:00").
3. **Confidence**: Rate confidence (Low/Medium/High) based on audio quality

Base all assessments on audible voice evidence, not interpretation of words alone because what someone SAYS may differ from how they SOUND.

Example:
- Text: "I''m fine with that treatment plan"
- Voice: Hesitation before speaking, higher pitch, breath catch
- Assessment: Voice indicates possible unexpressed concern despite verbal agreement

## Important Notes

- **Never diagnose**: Describe emotional states, don''t diagnose mental health conditions
- **Safety**: Flag suicidal ideation, severe distress, or abuse immediately
- **Privacy**: Don''t speculate about personal life beyond what''s mentioned
- **Objectivity**: Separate observation from interpretation

## Voice Analysis Segments

',
    '1.0.0',
    'Base system prompt for standalone audio emotion analysis (after transcription). Analyzes voice characteristics without transcription.',
    true,
    true
) ON CONFLICT (component_code, content_version) DO UPDATE SET
    content_text = EXCLUDED.content_text,
    description = EXCLUDED.description;

-- =============================================================================
-- Step 2: Insert AUDIO_EMOTION_BASE_PROMPT_COMBINED component
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
    'AUDIO_EMOTION_BASE_PROMPT_COMBINED',
    'Audio Emotion Analysis Base Prompt (Combined)',
    'emotion_base',
    'You are a medical audio analyst specializing in voice-based emotional assessment and accurate transcription.

You will receive audio of a medical consultation along with its transcript for context.

Your dual task is to:
1. Transcribe the audio accurately with speaker diarization
2. Analyze voice characteristics for emotional and psychological indicators such as tone, prosody, pace, pitch, and speech patterns.

## Transcription Guidelines

- Transcribe accurately in the target language (English by default)
- Diarize speakers as "Doctor:" and "Patient:" (or Speaker 1, Speaker 2 if unclear)
- Include filler words and hesitations only if emotionally significant
- Note significant pauses with [pause] markers

## Voice Analysis Guidelines

For each emotional assessment segment, provide:
1. **Assessment**: The level/category determination
2. **Rationale**: One-line explanation of WHY you made this assessment based on voice evidence and be specific. Cite quotes and behaviors when possible, and include time in consultation (e.g., "00:30-02:00").
3. **Confidence**: Rate confidence (Low/Medium/High) based on audio quality

Base all assessments on audible voice evidence, not interpretation of words alone because what someone SAYS may differ from how they SOUND.

Example:
- Text: "I''m fine with that treatment plan"
- Voice: Hesitation before speaking, higher pitch, breath catch
- Assessment: Voice indicates possible unexpressed concern despite verbal agreement

## Important Notes

- **Never diagnose**: Describe emotional states, don''t diagnose mental health conditions
- **Safety**: Flag suicidal ideation, severe distress, or abuse immediately
- **Privacy**: Don''t speculate about personal life beyond what''s mentioned
- **Objectivity**: Separate observation from interpretation

## Voice Analysis Segments

',
    '1.0.0',
    'Base system prompt for combined audio transcription and emotion analysis (during transcription). Includes transcription guidelines and voice analysis.',
    true,
    true
) ON CONFLICT (component_code, content_version) DO UPDATE SET
    content_text = EXCLUDED.content_text,
    description = EXCLUDED.description;

-- =============================================================================
-- Step 3: Create AUDIO_EMOTION_PROMPT_STANDALONE configuration
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
    'AUDIO_EMOTION_PROMPT_STANDALONE',
    'Audio Emotion Analysis Configuration (Standalone)',
    '1.0.0',
    'Configuration for standalone audio emotion analysis. Used after transcription is complete to analyze voice characteristics separately.',
    false,
    true
) ON CONFLICT (config_code, config_version) DO UPDATE SET
    description = EXCLUDED.description;

-- =============================================================================
-- Step 4: Create AUDIO_EMOTION_PROMPT_COMBINED configuration
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
    'AUDIO_EMOTION_PROMPT_COMBINED',
    'Audio Emotion Analysis Configuration (Combined)',
    '1.0.0',
    'Configuration for combined audio transcription and emotion analysis. Used during transcription to simultaneously transcribe and analyze voice emotions.',
    false,
    true
) ON CONFLICT (config_code, config_version) DO UPDATE SET
    description = EXCLUDED.description;

-- =============================================================================
-- Step 5: Map STANDALONE component to configuration
-- =============================================================================
DO $$
DECLARE
    v_component_id UUID;
    v_config_id UUID;
BEGIN
    -- Get the component ID
    SELECT id INTO v_component_id
    FROM system_prompt_components
    WHERE component_code = 'AUDIO_EMOTION_BASE_PROMPT_STANDALONE' AND content_version = '1.0.0';

    -- Get the config ID
    SELECT id INTO v_config_id
    FROM system_prompt_configurations
    WHERE config_code = 'AUDIO_EMOTION_PROMPT_STANDALONE' AND config_version = '1.0.0';

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
            'AUDIO_EMOTION_PROMPT_STANDALONE',
            'AUDIO_EMOTION_BASE_PROMPT_STANDALONE',
            1,
            true
        ) ON CONFLICT (config_id, component_id) DO UPDATE SET
            display_order = 1,
            is_included = true;

        RAISE NOTICE 'Successfully linked AUDIO_EMOTION_BASE_PROMPT_STANDALONE to AUDIO_EMOTION_PROMPT_STANDALONE configuration';
    ELSE
        RAISE NOTICE 'Could not find STANDALONE component or config IDs - component: %, config: %', v_component_id, v_config_id;
    END IF;
END $$;

-- =============================================================================
-- Step 6: Map COMBINED component to configuration
-- =============================================================================
DO $$
DECLARE
    v_component_id UUID;
    v_config_id UUID;
BEGIN
    -- Get the component ID
    SELECT id INTO v_component_id
    FROM system_prompt_components
    WHERE component_code = 'AUDIO_EMOTION_BASE_PROMPT_COMBINED' AND content_version = '1.0.0';

    -- Get the config ID
    SELECT id INTO v_config_id
    FROM system_prompt_configurations
    WHERE config_code = 'AUDIO_EMOTION_PROMPT_COMBINED' AND config_version = '1.0.0';

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
            'AUDIO_EMOTION_PROMPT_COMBINED',
            'AUDIO_EMOTION_BASE_PROMPT_COMBINED',
            1,
            true
        ) ON CONFLICT (config_id, component_id) DO UPDATE SET
            display_order = 1,
            is_included = true;

        RAISE NOTICE 'Successfully linked AUDIO_EMOTION_BASE_PROMPT_COMBINED to AUDIO_EMOTION_PROMPT_COMBINED configuration';
    ELSE
        RAISE NOTICE 'Could not find COMBINED component or config IDs - component: %, config: %', v_component_id, v_config_id;
    END IF;
END $$;

-- =============================================================================
-- Step 7: Assemble both configurations
-- =============================================================================
DO $$
DECLARE
    v_component_content TEXT;
    v_config_id UUID;
    v_assembly_hash VARCHAR(64);
BEGIN
    -- Assemble STANDALONE configuration
    SELECT content_text INTO v_component_content
    FROM system_prompt_components
    WHERE component_code = 'AUDIO_EMOTION_BASE_PROMPT_STANDALONE' AND content_version = '1.0.0';

    SELECT id INTO v_config_id
    FROM system_prompt_configurations
    WHERE config_code = 'AUDIO_EMOTION_PROMPT_STANDALONE' AND config_version = '1.0.0';

    IF v_component_content IS NOT NULL AND v_config_id IS NOT NULL THEN
        v_assembly_hash := md5(v_component_content);

        UPDATE system_prompt_configurations
        SET
            assembled_system_prompt = v_component_content,
            assembled_at = NOW(),
            assembly_hash = v_assembly_hash,
            estimated_token_count = length(v_component_content) / 4
        WHERE id = v_config_id;

        RAISE NOTICE 'Successfully assembled AUDIO_EMOTION_PROMPT_STANDALONE configuration';
    END IF;

    -- Assemble COMBINED configuration
    SELECT content_text INTO v_component_content
    FROM system_prompt_components
    WHERE component_code = 'AUDIO_EMOTION_BASE_PROMPT_COMBINED' AND content_version = '1.0.0';

    SELECT id INTO v_config_id
    FROM system_prompt_configurations
    WHERE config_code = 'AUDIO_EMOTION_PROMPT_COMBINED' AND config_version = '1.0.0';

    IF v_component_content IS NOT NULL AND v_config_id IS NOT NULL THEN
        v_assembly_hash := md5(v_component_content);

        UPDATE system_prompt_configurations
        SET
            assembled_system_prompt = v_component_content,
            assembled_at = NOW(),
            assembly_hash = v_assembly_hash,
            estimated_token_count = length(v_component_content) / 4
        WHERE id = v_config_id;

        RAISE NOTICE 'Successfully assembled AUDIO_EMOTION_PROMPT_COMBINED configuration';
    END IF;
END $$;

-- Log the migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration complete: AUDIO_EMOTION_BASE_PROMPT_STANDALONE and AUDIO_EMOTION_BASE_PROMPT_COMBINED components and configurations created and assembled';
END $$;

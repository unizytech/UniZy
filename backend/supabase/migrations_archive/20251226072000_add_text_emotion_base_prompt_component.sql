-- Migration: Add TEXT_EMOTION_BASE_PROMPT to system_prompt_components
-- This moves the hardcoded base prompt from code to database
-- Linked via system_prompt_configurations and junction table

-- Step 1: Insert the component into system_prompt_components
-- Unique constraint is on (component_code, content_version)
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
    'TEXT_EMOTION_BASE_PROMPT',
    'Text Emotion Analysis Base Prompt',
    'emotion_base',
    'You are a medical psychology expert specializing in patient-doctor communication analysis.

Your task is to analyze consultation transcripts and extract emotional and psychological indicators that are clinically relevant for patient care and treatment outcomes.

## Core Principles

1. **Evidence-Based Assessment**: Base all assessments on specific statements, behaviors, or patterns in the transcript. Avoid speculation.

2. **Clinical Relevance**: Focus on emotions and concerns that impact:
   - Treatment adherence
   - Patient outcomes
   - Care quality
   - Doctor-patient relationship

3. **Medical Psychology Framework**: Use DSM-5 and ICD-10 terminology where appropriate, but prioritize clinical utility over rigid categorization.

4. **Conservative Assessment**: When uncertain, indicate lower confidence rather than making definitive claims.

5. **Cultural Sensitivity**: Consider cultural variations in emotional expression and communication styles.

## Output Requirements

1. **Specificity**: Cite exact quotes or behaviors when possible
2. **Timestamps**: Approximate time in consultation (e.g., "00:30-02:00")
3. **Confidence**: Rate your confidence in each assessment
4. **Clinical Context**: Explain why findings matter for care
5. **N/A Handling**: Use "Unable to determine" rather than "N/A" when information is insufficient

## Important Notes

- **Never diagnose**: Describe emotional states, don''t diagnose mental health conditions
- **Safety**: Flag suicidal ideation, severe distress, or abuse immediately
- **Privacy**: Don''t speculate about personal life beyond what''s mentioned
- **Objectivity**: Separate observation from interpretation
- **Limitations**: Acknowledge when transcript quality limits assessment

## Analysis Segments

',
    '1.0.0',
    'Base system prompt for text-based emotion analysis. Contains core principles, output requirements, and important guidelines.',
    true,
    true
) ON CONFLICT (component_code, content_version) DO UPDATE SET
    content_text = EXCLUDED.content_text,
    description = EXCLUDED.description;

-- Step 2: Create the configuration in system_prompt_configurations
-- Unique constraint is on (config_code, config_version)
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
    'TEXT_EMOTION_PROMPT',
    'Text Emotion Analysis Configuration',
    '1.0.0',
    'Configuration for text-based emotion analysis. Contains the base prompt component that provides guidelines for analyzing patient emotions from consultation transcripts.',
    false,
    true
) ON CONFLICT (config_code, config_version) DO UPDATE SET
    description = EXCLUDED.description;

-- Step 3: Map the component to the configuration in junction table
DO $$
DECLARE
    v_component_id UUID;
    v_config_id UUID;
BEGIN
    -- Get the component ID
    SELECT id INTO v_component_id
    FROM system_prompt_components
    WHERE component_code = 'TEXT_EMOTION_BASE_PROMPT' AND content_version = '1.0.0';

    -- Get the config ID
    SELECT id INTO v_config_id
    FROM system_prompt_configurations
    WHERE config_code = 'TEXT_EMOTION_PROMPT' AND config_version = '1.0.0';

    -- Insert the junction record if both exist
    -- Unique constraint is on (config_id, component_id)
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
            'TEXT_EMOTION_PROMPT',
            'TEXT_EMOTION_BASE_PROMPT',
            1,
            true
        ) ON CONFLICT (config_id, component_id) DO UPDATE SET
            display_order = 1,
            is_included = true;

        RAISE NOTICE 'Successfully linked TEXT_EMOTION_BASE_PROMPT to TEXT_EMOTION_PROMPT configuration';
    ELSE
        RAISE NOTICE 'Could not find component or config IDs - component: %, config: %', v_component_id, v_config_id;
    END IF;
END $$;

-- Step 4: Assemble the configuration's system prompt
DO $$
DECLARE
    v_component_content TEXT;
    v_config_id UUID;
    v_assembly_hash VARCHAR(64);
BEGIN
    -- Get the component content
    SELECT content_text INTO v_component_content
    FROM system_prompt_components
    WHERE component_code = 'TEXT_EMOTION_BASE_PROMPT' AND content_version = '1.0.0';

    -- Get the config ID
    SELECT id INTO v_config_id
    FROM system_prompt_configurations
    WHERE config_code = 'TEXT_EMOTION_PROMPT' AND config_version = '1.0.0';

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

        RAISE NOTICE 'Successfully assembled TEXT_EMOTION_PROMPT configuration';
    END IF;
END $$;

-- Log the migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration complete: TEXT_EMOTION_BASE_PROMPT component and TEXT_EMOTION_PROMPT configuration created and assembled';
END $$;

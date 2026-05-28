-- Migration: Update emotion segment schemas to support combined (congruence) mode
-- This adds fields from COMBINED_* segments to the existing segment definitions
-- so that combined analysis results can be stored using the same segment codes.

-- ============================================================================
-- 1. ANXIETY_POST_CONSULTATION
-- Add combined mode fields: pre_consultation, post_consultation objects with
-- level, combined_score, source, text_level, audio_level, mismatch, rationale
-- Plus trajectory object
-- ============================================================================

UPDATE segment_definitions
SET schema_definition_json = jsonb_build_object(
    'type', 'object',
    'required', jsonb_build_array('level', 'confidence'),
    'properties', jsonb_build_object(
        -- Original fields (text-only mode)
        'level', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('None', 'Mild', 'Moderate', 'Severe'),
            'description', 'Anxiety severity at consultation end'
        ),
        'indicators', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object('type', 'string'),
            'description', 'Specific behaviors or statements indicating anxiety'
        ),
        'confidence', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('Low', 'Medium', 'High'),
            'description', 'Confidence in this assessment'
        ),
        'change_from_pre', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('Improved', 'Unchanged', 'Worsened', 'Unable to determine'),
            'description', 'Change in anxiety from pre to post consultation'
        ),
        'notes', jsonb_build_object(
            'type', 'string',
            'description', 'Additional clinical observations'
        ),
        'timestamp_end', jsonb_build_object(
            'type', 'string',
            'description', 'Approximate timestamp when assessment ends'
        ),
        -- Combined mode fields
        'pre_consultation', jsonb_build_object(
            'type', 'object',
            'description', 'Pre-consultation anxiety (combined mode)',
            'properties', jsonb_build_object(
                'level', jsonb_build_object('type', 'string', 'enum', jsonb_build_array('None', 'Mild', 'Moderate', 'Severe')),
                'combined_score', jsonb_build_object('type', 'number'),
                'source', jsonb_build_object('type', 'string', 'enum', jsonb_build_array('text_higher', 'audio_higher', 'both_agree')),
                'text_level', jsonb_build_object('type', 'string'),
                'audio_level', jsonb_build_object('type', 'string'),
                'mismatch', jsonb_build_object('type', 'boolean'),
                'rationale', jsonb_build_object('type', 'string')
            )
        ),
        'post_consultation', jsonb_build_object(
            'type', 'object',
            'description', 'Post-consultation anxiety (combined mode)',
            'properties', jsonb_build_object(
                'level', jsonb_build_object('type', 'string', 'enum', jsonb_build_array('None', 'Mild', 'Moderate', 'Severe')),
                'combined_score', jsonb_build_object('type', 'number'),
                'source', jsonb_build_object('type', 'string', 'enum', jsonb_build_array('text_higher', 'audio_higher', 'both_agree')),
                'text_level', jsonb_build_object('type', 'string'),
                'audio_level', jsonb_build_object('type', 'string'),
                'mismatch', jsonb_build_object('type', 'boolean'),
                'rationale', jsonb_build_object('type', 'string')
            )
        ),
        'trajectory', jsonb_build_object(
            'type', 'object',
            'description', 'Anxiety trajectory (combined mode)',
            'properties', jsonb_build_object(
                'trajectory', jsonb_build_object('type', 'string', 'enum', jsonb_build_array('Improved', 'Stable', 'Worsened', 'Unable to determine')),
                'text_change', jsonb_build_object('type', 'string'),
                'audio_trajectory', jsonb_build_object('type', 'string'),
                'mismatch', jsonb_build_object('type', 'boolean')
            )
        ),
        -- Combined mode metadata
        'source', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('text_only', 'audio_only', 'combined'),
            'description', 'Analysis source mode'
        ),
        'mismatch', jsonb_build_object(
            'type', 'boolean',
            'description', 'Whether text and audio analysis disagreed'
        ),
        'rationale', jsonb_build_object(
            'type', 'string',
            'description', 'Combined rationale from text and audio analysis'
        )
    )
),
updated_at = NOW()
WHERE segment_code = 'ANXIETY_POST_CONSULTATION'
AND segment_type = 'system';

-- ============================================================================
-- 2. FINANCIAL_CONCERNS
-- Add combined mode fields with Mild/Moderate/Severe severity enum
-- ============================================================================

UPDATE segment_definitions
SET schema_definition_json = jsonb_build_object(
    'type', 'object',
    'required', jsonb_build_array('concerns_present', 'severity'),
    'properties', jsonb_build_object(
        -- Original fields (text-only mode)
        'concerns_present', jsonb_build_object(
            'type', 'boolean',
            'description', 'Were any financial concerns detected?'
        ),
        'severity', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('None', 'Mild', 'Moderate', 'Severe'),
            'description', 'Severity of financial concerns'
        ),
        'specific_concerns', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object(
                'type', 'object',
                'required', jsonb_build_array('concern_type', 'evidence'),
                'properties', jsonb_build_object(
                    'concern_type', jsonb_build_object(
                        'type', 'string',
                        'enum', jsonb_build_array('Treatment cost', 'Medication cost', 'Test/procedure cost', 'Insurance coverage', 'Alternative options', 'Payment plans', 'Other')
                    ),
                    'evidence', jsonb_build_object('type', 'string'),
                    'impact_on_compliance', jsonb_build_object(
                        'type', 'string',
                        'enum', jsonb_build_array('High risk', 'Moderate risk', 'Low risk')
                    )
                )
            ),
            'description', 'List of specific financial concerns'
        ),
        'alternative_treatment_requested', jsonb_build_object(
            'type', 'boolean',
            'description', 'Did patient request cheaper alternatives?'
        ),
        'notes', jsonb_build_object(
            'type', 'string',
            'description', 'Additional context'
        ),
        -- Combined mode fields
        'combined_score', jsonb_build_object(
            'type', 'number',
            'description', 'Numeric score for severity (combined mode)'
        ),
        'source', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('text_only', 'audio_only', 'combined', 'text_higher', 'audio_higher', 'both_agree'),
            'description', 'Analysis source mode'
        ),
        'text_severity', jsonb_build_object(
            'type', 'string',
            'description', 'Text analysis severity level'
        ),
        'audio_severity', jsonb_build_object(
            'type', 'string',
            'description', 'Audio analysis severity level'
        ),
        'mismatch', jsonb_build_object(
            'type', 'boolean',
            'description', 'Whether text and audio analysis disagreed'
        ),
        'rationale', jsonb_build_object(
            'type', 'string',
            'description', 'Combined rationale from text and audio analysis'
        ),
        'confidence', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('Low', 'Medium', 'High'),
            'description', 'Confidence in this assessment'
        )
    )
),
updated_at = NOW()
WHERE segment_code = 'FINANCIAL_CONCERNS'
AND segment_type = 'system';

-- ============================================================================
-- 3. TREATMENT_COMPLIANCE_LIKELIHOOD
-- Add combined mode fields
-- ============================================================================

UPDATE segment_definitions
SET schema_definition_json = jsonb_build_object(
    'type', 'object',
    'required', jsonb_build_array('likelihood', 'positive_factors', 'negative_factors', 'confidence'),
    'properties', jsonb_build_object(
        -- Original fields (text-only mode)
        'likelihood', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('Very Low (0-19%)', 'Low (20-49%)', 'Moderate (50-79%)', 'High (80-100%)', 'Very Low', 'Low', 'Moderate', 'High'),
            'description', 'Overall likelihood of treatment compliance'
        ),
        'positive_factors', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object('type', 'string'),
            'description', 'Factors supporting compliance'
        ),
        'negative_factors', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object('type', 'string'),
            'description', 'Barriers to compliance'
        ),
        'confidence', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('Low', 'Medium', 'High'),
            'description', 'Confidence in this assessment'
        ),
        'key_barriers', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object(
                'type', 'object',
                'properties', jsonb_build_object(
                    'barrier_type', jsonb_build_object(
                        'type', 'string',
                        'enum', jsonb_build_array('Financial', 'Logistical', 'Understanding', 'Motivation', 'Fear/Anxiety', 'Social support', 'Other')
                    ),
                    'severity', jsonb_build_object(
                        'type', 'string',
                        'enum', jsonb_build_array('Minor', 'Moderate', 'Major')
                    ),
                    'evidence', jsonb_build_object('type', 'string')
                )
            ),
            'description', 'Primary barriers to compliance'
        ),
        'recommendations', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object('type', 'string'),
            'description', 'Suggestions to improve compliance'
        ),
        'notes', jsonb_build_object(
            'type', 'string',
            'description', 'Additional observations'
        ),
        -- Combined mode fields
        'combined_score', jsonb_build_object(
            'type', 'number',
            'description', 'Numeric score for likelihood (combined mode)'
        ),
        'source', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('text_only', 'audio_only', 'combined', 'text_higher', 'audio_higher', 'both_agree'),
            'description', 'Analysis source mode'
        ),
        'text_likelihood', jsonb_build_object(
            'type', 'string',
            'description', 'Text analysis likelihood level'
        ),
        'audio_likelihood', jsonb_build_object(
            'type', 'string',
            'description', 'Audio analysis likelihood level'
        ),
        'mismatch', jsonb_build_object(
            'type', 'boolean',
            'description', 'Whether text and audio analysis disagreed'
        ),
        'rationale', jsonb_build_object(
            'type', 'string',
            'description', 'Combined rationale from text and audio analysis'
        )
    )
),
updated_at = NOW()
WHERE segment_code = 'TREATMENT_COMPLIANCE_LIKELIHOOD'
AND segment_type = 'system';

-- ============================================================================
-- 4. OTHER_EMOTIONS_DETECTED
-- Add combined mode fields
-- ============================================================================

UPDATE segment_definitions
SET schema_definition_json = jsonb_build_object(
    'type', 'object',
    'required', jsonb_build_array('emotions_detected'),
    'properties', jsonb_build_object(
        -- Original fields (text-only mode) - emotions_detected can be array of objects OR strings
        'emotions_detected', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object(
                'oneOf', jsonb_build_array(
                    jsonb_build_object('type', 'string'),
                    jsonb_build_object(
                        'type', 'object',
                        'properties', jsonb_build_object(
                            'emotion', jsonb_build_object('type', 'string'),
                            'severity', jsonb_build_object('type', 'string', 'enum', jsonb_build_array('Mild', 'Moderate', 'Severe')),
                            'evidence', jsonb_build_object('type', 'array', 'items', jsonb_build_object('type', 'string')),
                            'clinical_significance', jsonb_build_object('type', 'string', 'enum', jsonb_build_array('High', 'Medium', 'Low'))
                        )
                    )
                )
            ),
            'description', 'List of emotions detected - either strings (combined mode) or objects with details (text-only mode)'
        ),
        'dominant_emotion', jsonb_build_object(
            'type', 'string',
            'description', 'Most prominent emotion throughout consultation'
        ),
        'notes', jsonb_build_object(
            'type', 'string',
            'description', 'Additional observations'
        ),
        -- Combined mode fields
        'text_emotions', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object('type', 'string'),
            'description', 'Emotions detected from text analysis'
        ),
        'audio_dominant', jsonb_build_object(
            'type', 'string',
            'description', 'Dominant emotion from audio analysis'
        ),
        'source', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('text_only', 'audio_only', 'combined', 'text', 'audio', 'both'),
            'description', 'Analysis source mode'
        ),
        'mismatch', jsonb_build_object(
            'type', 'boolean',
            'description', 'Whether text and audio analysis disagreed'
        ),
        'rationale', jsonb_build_object(
            'type', 'string',
            'description', 'Combined rationale from text and audio analysis'
        ),
        'confidence', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('Low', 'Medium', 'High'),
            'description', 'Confidence in this assessment'
        )
    )
),
updated_at = NOW()
WHERE segment_code = 'OTHER_EMOTIONS_DETECTED'
AND segment_type = 'system';

-- ============================================================================
-- 5. DOCTOR_COMMUNICATION_STYLE
-- Add combined mode fields
-- ============================================================================

UPDATE segment_definitions
SET schema_definition_json = jsonb_build_object(
    'type', 'object',
    'required', jsonb_build_array('primary_style', 'confidence'),
    'properties', jsonb_build_object(
        -- Original fields (text-only mode)
        'primary_style', jsonb_build_object(
            'type', 'string',
            'description', 'Primary communication style'
        ),
        'confidence', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('Low', 'Medium', 'High'),
            'description', 'Confidence in this assessment'
        ),
        'empathy_indicators', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object('type', 'string'),
            'description', 'Indicators of empathy shown'
        ),
        'patient_anxiety_impact', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('Reduced', 'No effect', 'Increased'),
            'description', 'Impact on patient anxiety'
        ),
        'clarity_rating', jsonb_build_object(
            'type', 'string',
            'description', 'Rating of communication clarity'
        ),
        'communication_strengths', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object('type', 'string'),
            'description', 'Communication strengths observed'
        ),
        'areas_for_improvement', jsonb_build_object(
            'type', 'array',
            'items', jsonb_build_object('type', 'string'),
            'description', 'Areas where communication could improve'
        ),
        'notes', jsonb_build_object(
            'type', 'string',
            'description', 'Additional observations'
        ),
        -- Combined mode fields
        'text_style', jsonb_build_object(
            'type', 'string',
            'description', 'Communication style from text analysis'
        ),
        'audio_style', jsonb_build_object(
            'type', 'string',
            'description', 'Communication style from audio analysis'
        ),
        'voice_warmth', jsonb_build_object(
            'type', 'string',
            'description', 'Voice warmth level from audio analysis'
        ),
        'tone_consistency', jsonb_build_object(
            'type', 'string',
            'description', 'Tone consistency from audio analysis'
        ),
        'source', jsonb_build_object(
            'type', 'string',
            'enum', jsonb_build_array('text_only', 'audio_only', 'combined', 'text', 'both'),
            'description', 'Analysis source mode'
        ),
        'mismatch', jsonb_build_object(
            'type', 'boolean',
            'description', 'Whether text and audio analysis disagreed'
        ),
        'rationale', jsonb_build_object(
            'type', 'string',
            'description', 'Combined rationale from text and audio analysis'
        )
    )
),
updated_at = NOW()
WHERE segment_code = 'DOCTOR_COMMUNICATION_STYLE'
AND segment_type = 'system';

-- ============================================================================
-- 6. DROP ANXIETY_PRE_CONSULTATION segment
-- Pre-consultation anxiety is now embedded within ANXIETY_POST_CONSULTATION schema
-- as pre_consultation object in combined mode, and text-only uses TEXT_EMOTION_* prefix
-- ============================================================================

DELETE FROM segment_definitions
WHERE segment_code = 'ANXIETY_PRE_CONSULTATION'
AND segment_type = 'system';

-- ============================================================================
-- Verify updates
-- ============================================================================

DO $$
DECLARE
    updated_count INTEGER;
    deleted_count INTEGER;
BEGIN
    -- Check updated segments
    SELECT COUNT(*) INTO updated_count
    FROM segment_definitions
    WHERE segment_code IN (
        'ANXIETY_POST_CONSULTATION',
        'FINANCIAL_CONCERNS',
        'TREATMENT_COMPLIANCE_LIKELIHOOD',
        'OTHER_EMOTIONS_DETECTED',
        'DOCTOR_COMMUNICATION_STYLE'
    )
    AND segment_type = 'system'
    AND schema_definition_json ? 'mismatch';  -- Check for combined mode field

    RAISE NOTICE 'Updated % segment definitions with combined mode fields', updated_count;

    IF updated_count != 5 THEN
        RAISE WARNING 'Expected 5 segments to be updated, but only % were updated', updated_count;
    END IF;

    -- Check deleted segment
    SELECT COUNT(*) INTO deleted_count
    FROM segment_definitions
    WHERE segment_code = 'ANXIETY_PRE_CONSULTATION'
    AND segment_type = 'system';

    IF deleted_count = 0 THEN
        RAISE NOTICE 'Successfully dropped ANXIETY_PRE_CONSULTATION segment';
    ELSE
        RAISE WARNING 'ANXIETY_PRE_CONSULTATION segment still exists';
    END IF;
END $$;

-- Remove access_level filters from validate_segment_configuration RPC
-- access_level is no longer used for gating; is_active=TRUE is the only filter needed

CREATE OR REPLACE FUNCTION public.validate_segment_configuration(p_doctor_id uuid)
 RETURNS TABLE(is_valid boolean, error_message text)
 LANGUAGE plpgsql
AS $function$
DECLARE
    activated_template_count INTEGER;
    template_required_count INTEGER;
    template_core_required_count INTEGER;
BEGIN
    -- Check if doctor has any active templates
    SELECT COUNT(*) INTO activated_template_count
    FROM doctor_templates
    WHERE doctor_id = p_doctor_id
      AND is_active = TRUE;

    -- If no active templates, validation passes (they'll use global templates)
    IF activated_template_count = 0 THEN
        RETURN QUERY SELECT TRUE, NULL::TEXT;
        RETURN;
    END IF;

    -- Count required segments that are IN the doctor's active templates
    -- (excluding segments marked as 'excluded' in template_segments)
    SELECT COUNT(DISTINCT sd.id) INTO template_required_count
    FROM segment_definitions sd
    INNER JOIN template_segments ts ON ts.segment_id = sd.id
    INNER JOIN templates t ON t.id = ts.template_id
    INNER JOIN doctor_templates dt ON dt.template_id = t.id
    WHERE sd.is_required = TRUE
      AND sd.is_active = TRUE
      AND t.is_active = TRUE
      AND dt.doctor_id = p_doctor_id
      AND dt.is_active = TRUE
      AND LOWER(ts.category) != 'excluded';  -- Ignore excluded segments

    -- Count required segments that are in CORE category
    SELECT COUNT(DISTINCT sd.id) INTO template_core_required_count
    FROM segment_definitions sd
    INNER JOIN template_segments ts ON ts.segment_id = sd.id
    INNER JOIN templates t ON t.id = ts.template_id
    INNER JOIN doctor_templates dt ON dt.template_id = t.id
    WHERE sd.is_required = TRUE
      AND sd.is_active = TRUE
      AND t.is_active = TRUE
      AND dt.doctor_id = p_doctor_id
      AND dt.is_active = TRUE
      AND LOWER(ts.category) = 'core';  -- Case-insensitive check

    -- If no required segments in template at all, that's fine (template might use different segments)
    IF template_required_count = 0 THEN
        RETURN QUERY SELECT TRUE, NULL::TEXT;
        RETURN;
    END IF;

    -- Check that all required segments in the template are in CORE category
    IF template_core_required_count < template_required_count THEN
        RETURN QUERY SELECT FALSE,
            format(
                'Required segments must be in CORE category for clinical safety. Found %s/%s required segments in CORE.',
                template_core_required_count,
                template_required_count
            )::TEXT;
    ELSE
        RETURN QUERY SELECT TRUE, NULL::TEXT;
    END IF;
END;
$function$;

-- Clean up existing reasons to remove point references
-- Makes reasons more human-readable without scoring details

-- =============================================================================
-- 1. Clean up clinical_severity_assessments.reasons
-- =============================================================================

-- Update reasons array to remove point references
UPDATE clinical_severity_assessments
SET reasons = (
    SELECT array_agg(
        CASE
            -- Remove "(Xpts)" pattern
            WHEN reason ~ '\([0-9]+pts\)$' THEN regexp_replace(reason, '\s*\([0-9]+pts\)$', '')
            -- Remove "+Xpts" pattern
            WHEN reason ~ '\+[0-9]+pts' THEN regexp_replace(reason, '\s*\+[0-9]+pts', '')
            -- Replace "Chronic Condition: +1pts" style
            WHEN reason ~ '^Chronic Condition:' THEN 'Chronic condition requiring ongoing management'
            -- Replace surgical with points
            WHEN reason ~ 'Surgical intervention \(\+3pts\)' THEN 'Surgical intervention required'
            ELSE reason
        END
    )
    FROM unnest(reasons) AS reason
)
WHERE reasons IS NOT NULL AND array_length(reasons, 1) > 0;

-- Also update contributing_factors to match
UPDATE clinical_severity_assessments
SET contributing_factors = (
    SELECT array_agg(
        CASE
            WHEN factor ~ '\([0-9]+pts\)$' THEN regexp_replace(factor, '\s*\([0-9]+pts\)$', '')
            WHEN factor ~ '\+[0-9]+pts' THEN regexp_replace(factor, '\s*\+[0-9]+pts', '')
            WHEN factor ~ '^Chronic Condition:' THEN 'Chronic condition requiring ongoing management'
            WHEN factor ~ 'Surgical intervention \(\+3pts\)' THEN 'Surgical intervention required'
            ELSE factor
        END
    )
    FROM unnest(contributing_factors) AS factor
)
WHERE contributing_factors IS NOT NULL AND array_length(contributing_factors, 1) > 0;

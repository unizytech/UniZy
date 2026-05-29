-- Migration: Add exec_sql function for Q&A Engine dynamic queries
-- This function allows executing SELECT queries dynamically for vector search
-- SECURITY: Restricted to SELECT only, blocks modification keywords

CREATE OR REPLACE FUNCTION public.exec_sql(sql_query TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSONB;
    cleaned_query TEXT;
BEGIN
    -- Remove leading/trailing whitespace including newlines
    cleaned_query := REGEXP_REPLACE(sql_query, '^[\s\n\r\t]+', '', 'g');
    cleaned_query := UPPER(cleaned_query);

    -- Validate query is SELECT or WITH (CTE) only
    IF NOT (cleaned_query LIKE 'SELECT%' OR cleaned_query LIKE 'WITH%') THEN
        RAISE EXCEPTION 'Only SELECT queries are allowed';
    END IF;

    -- Check for dangerous keywords
    IF sql_query ~* '\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b' THEN
        RAISE EXCEPTION 'Modification queries are not allowed';
    END IF;

    -- Execute and return as JSON
    EXECUTE 'SELECT COALESCE(jsonb_agg(row_to_json(t)), ''[]''::jsonb) FROM (' || sql_query || ') t'
    INTO result;

    RETURN result;
END;
$$;

-- Grant execute to authenticated users and service role
GRANT EXECUTE ON FUNCTION public.exec_sql(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.exec_sql(TEXT) TO service_role;

COMMENT ON FUNCTION public.exec_sql(TEXT) IS 'Execute SELECT queries dynamically for Q&A Engine vector search. Only SELECT allowed.';

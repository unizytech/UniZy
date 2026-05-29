-- Baseline Migration (consolidated schema)
-- Version: 20251216000000
--
-- This file is a FULL schema snapshot of the production (main) database,
-- generated via `supabase db dump` from project yvpyqnkxxgyzaapozafg.
--
-- Why this exists:
--   The previous baseline was an empty placeholder (`SELECT 1;`) created after a
--   migration-tracking reset, on the assumption that existing databases were
--   already schema-synced. That assumption breaks for Supabase preview branches:
--   a new branch builds a fresh, EMPTY database and replays migrations from
--   scratch. With an empty baseline, the first real migration after it
--   (20251216064130_drop_unused_segment_columns) failed with
--   `relation "segment_definitions" does not exist`, aborting the entire branch
--   build and leaving the branch with zero tables.
--
--   This baseline now contains the actual consolidated schema so any fresh
--   branch builds correctly. All migrations that previously preceded this point
--   have been squashed into this snapshot; obsolete post-baseline migrations
--   have been moved to ../migrations_archive/. New migrations go AFTER this file.
--
-- main and dev are schema-synchronized as of this snapshot.




SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE EXTENSION IF NOT EXISTS "pg_cron" WITH SCHEMA "pg_catalog";






CREATE EXTENSION IF NOT EXISTS "pg_net" WITH SCHEMA "extensions";






COMMENT ON SCHEMA "public" IS 'Schema updated 2025-11-24:
- Fixed validate_segment_configuration RPC function to use template_segments table
- Removed reference to dropped doctor_segment_configurations table
- Function now validates across activated templates (doctor_templates junction)';



CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."activate_config_for_consultation_type_rpc"("p_consultation_type_code" character varying, "p_config_id" "uuid") RETURNS boolean
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_consultation_type_id UUID;
BEGIN
    -- Get consultation_type_id
    SELECT id INTO v_consultation_type_id
    FROM consultation_types
    WHERE type_code = p_consultation_type_code;

    IF v_consultation_type_id IS NULL THEN
        RAISE EXCEPTION 'Consultation type not found: %', p_consultation_type_code;
    END IF;

    -- Deactivate all existing active configs for this consultation type
    UPDATE consultation_type_system_prompts
    SET is_active = false, updated_at = NOW()
    WHERE consultation_type_id = v_consultation_type_id
      AND is_active = true;

    -- Activate the specified config
    UPDATE consultation_type_system_prompts
    SET is_active = true, updated_at = NOW()
    WHERE consultation_type_id = v_consultation_type_id
      AND system_prompt_config_id = p_config_id;

    RETURN true;
END;
$$;


ALTER FUNCTION "public"."activate_config_for_consultation_type_rpc"("p_consultation_type_code" character varying, "p_config_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."assemble_combined_emotion_prompt"("p_template_id" "uuid") RETURNS TABLE("prompt" "text", "schema_json" "jsonb")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_base_prompt TEXT;
    v_segment_prompts TEXT := '';
    v_schema JSONB := '{"type": "object", "required": [], "properties": {}}'::jsonb;
    v_seg RECORD;
BEGIN
    -- Get base prompt from system_prompt_components
    SELECT content INTO v_base_prompt
    FROM system_prompt_components
    WHERE component_code = 'COMBINED_EMOTION_BASE_PROMPT'
    AND is_active = true;

    IF v_base_prompt IS NULL THEN
        RETURN;
    END IF;

    -- Get all combined emotion segments
    FOR v_seg IN
        SELECT segment_code, prompt_section_text, schema_definition_json
        FROM segment_definitions
        WHERE segment_code LIKE 'COMBINED_%'
        AND is_active = true
        ORDER BY segment_code
    LOOP
        -- Append segment prompt
        v_segment_prompts := v_segment_prompts || E'\n\n' || v_seg.prompt_section_text;

        -- Add to schema properties
        v_schema := jsonb_set(
            v_schema,
            ARRAY['properties', v_seg.segment_code],
            v_seg.schema_definition_json
        );

        -- Add to required array
        v_schema := jsonb_set(
            v_schema,
            '{required}',
            (v_schema->'required') || to_jsonb(v_seg.segment_code)
        );
    END LOOP;

    -- Combine base prompt with segment prompts
    prompt := v_base_prompt || E'\n\n## Segment-Specific Instructions\n' || v_segment_prompts;
    schema_json := v_schema;

    RETURN NEXT;
END;
$$;


ALTER FUNCTION "public"."assemble_combined_emotion_prompt"("p_template_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."assemble_system_prompt_rpc"("p_config_id" "uuid") RETURNS "text"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    assembled_prompt TEXT := '';
    component_record RECORD;
BEGIN
    -- Get all included components ordered by display_order
    FOR component_record IN
        SELECT spc.content_text
        FROM system_prompt_config_components spcc
        JOIN system_prompt_components spc ON spcc.component_id = spc.id
        WHERE spcc.config_id = p_config_id
          AND spcc.is_included = true
        ORDER BY spcc.display_order ASC
    LOOP
        IF assembled_prompt != '' THEN
            assembled_prompt := assembled_prompt || E'\n\n';
        END IF;
        assembled_prompt := assembled_prompt || component_record.content_text;
    END LOOP;

    RETURN assembled_prompt;
END;
$$;


ALTER FUNCTION "public"."assemble_system_prompt_rpc"("p_config_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."can_doctor_access_template"("p_doctor_id" "uuid", "p_template_id" "uuid") RETURNS boolean
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    template_owner UUID;
    has_access BOOLEAN;
BEGIN
    -- Get template owner
    SELECT doctor_id INTO template_owner
    FROM templates
    WHERE id = p_template_id;

    -- Common templates (doctor_id=NULL) are accessible to all
    IF template_owner IS NULL THEN
        RETURN TRUE;
    END IF;

    -- Owner can always access
    IF template_owner = p_doctor_id THEN
        RETURN TRUE;
    END IF;

    -- Check doctor_templates junction table
    SELECT EXISTS (
        SELECT 1
        FROM doctor_templates
        WHERE doctor_id = p_doctor_id
        AND template_id = p_template_id
    ) INTO has_access;

    RETURN has_access;
END;
$$;


ALTER FUNCTION "public"."can_doctor_access_template"("p_doctor_id" "uuid", "p_template_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."can_doctor_access_template"("p_doctor_id" "uuid", "p_template_id" "uuid") IS 'Check if a doctor can access a template.
Returns true if:
1. Template is common (doctor_id=NULL), OR
2. Doctor is template owner (template.doctor_id=doctor_id), OR
3. Doctor has explicit access via doctor_templates table';



CREATE OR REPLACE FUNCTION "public"."check_rate_limit"("p_client_id" "uuid") RETURNS boolean
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_rate_limit INT;
    v_request_count INT;
BEGIN
    SELECT rate_limit_per_hour INTO v_rate_limit
    FROM api_clients WHERE id = p_client_id;
    
    IF v_rate_limit IS NULL THEN RETURN FALSE; END IF;
    
    SELECT get_client_request_count_last_hour(p_client_id) INTO v_request_count;
    RETURN v_request_count < v_rate_limit;
END;
$$;


ALTER FUNCTION "public"."check_rate_limit"("p_client_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."cleanup_chunks_after_processing"("p_session_id" "uuid", "p_full_audio_data" "text", "p_full_audio_mime_type" "text", "p_full_audio_size_bytes" bigint, "p_processed_audio_data" "text" DEFAULT NULL::"text") RETURNS "void"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    DELETE FROM audio_chunks WHERE session_id = p_session_id;

    UPDATE recording_sessions
    SET full_audio_data = p_full_audio_data,
        full_audio_mime_type = p_full_audio_mime_type,
        full_audio_size_bytes = p_full_audio_size_bytes,
        processed_audio_data = p_processed_audio_data,
        has_processed_audio = (p_processed_audio_data IS NOT NULL)
    WHERE id = p_session_id;
END;
$$;


ALTER FUNCTION "public"."cleanup_chunks_after_processing"("p_session_id" "uuid", "p_full_audio_data" "text", "p_full_audio_mime_type" "text", "p_full_audio_size_bytes" bigint, "p_processed_audio_data" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."cleanup_old_realtime_responses"() RETURNS integer
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE deleted_count INTEGER;
BEGIN
    DELETE FROM realtime_extraction_responses WHERE created_at < NOW() - INTERVAL '24 hours';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;


ALTER FUNCTION "public"."cleanup_old_realtime_responses"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."cleanup_old_sessions"("days_old" integer DEFAULT 30) RETURNS integer
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM recording_sessions
    WHERE created_at < NOW() - (days_old || ' days')::INTERVAL
      AND status IN ('COMPLETED', 'ERROR', 'CANCELLED')
      AND chunks_deleted = TRUE;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;


ALTER FUNCTION "public"."cleanup_old_sessions"("days_old" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."compute_all_hospital_patterns"() RETURNS TABLE("hospital_id" "uuid", "specialty" "text", "doctor_count" integer, "success" boolean)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    r RECORD;
    v_result hospital_specialty_patterns%ROWTYPE;
BEGIN
    -- Iterate through all unique hospital/specialty combinations
    FOR r IN (
        SELECT DISTINCT d.hospital_id, d.specialization
        FROM doctors d
        WHERE d.hospital_id IS NOT NULL
        AND d.specialization IS NOT NULL
    ) LOOP
        BEGIN
            v_result := compute_hospital_specialty_patterns(r.hospital_id, r.specialization);

            hospital_id := r.hospital_id;
            specialty := r.specialization;
            doctor_count := COALESCE(v_result.doctor_count, 0);
            success := (v_result IS NOT NULL);
            RETURN NEXT;

        EXCEPTION WHEN OTHERS THEN
            hospital_id := r.hospital_id;
            specialty := r.specialization;
            doctor_count := 0;
            success := FALSE;
            RETURN NEXT;
        END;
    END LOOP;

    RETURN;
END;
$$;


ALTER FUNCTION "public"."compute_all_hospital_patterns"() OWNER TO "postgres";


COMMENT ON FUNCTION "public"."compute_all_hospital_patterns"() IS 'Background job to recompute all hospital specialty patterns. Run daily.';


SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."doctor_practice_styles" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "specialty" "text",
    "practice_intensity" "text",
    "avg_investigations_per_extraction" numeric(5,2),
    "avg_suggestions_accepted_per_extraction" numeric(5,2),
    "preferred_investigation_types" "jsonb" DEFAULT '{}'::"jsonb",
    "preferred_diagnosis_categories" "jsonb" DEFAULT '{}'::"jsonb",
    "first_line_by_presentation" "jsonb" DEFAULT '{}'::"jsonb",
    "common_rejection_reasons" "jsonb" DEFAULT '[]'::"jsonb",
    "total_extractions_analyzed" integer DEFAULT 0,
    "total_suggestions_generated" integer DEFAULT 0,
    "total_feedback_entries" integer DEFAULT 0,
    "acceptance_rate" numeric(5,2),
    "confidence_level" "text" DEFAULT 'low'::"text",
    "last_computed_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "doctor_practice_styles_confidence_level_check" CHECK (("confidence_level" = ANY (ARRAY['low'::"text", 'medium'::"text", 'high'::"text"]))),
    CONSTRAINT "doctor_practice_styles_practice_intensity_check" CHECK (("practice_intensity" = ANY (ARRAY['conservative'::"text", 'moderate'::"text", 'aggressive'::"text"])))
);


ALTER TABLE "public"."doctor_practice_styles" OWNER TO "postgres";


COMMENT ON TABLE "public"."doctor_practice_styles" IS 'Aggregated practice characteristics learned from doctor feedback on triage suggestions';



COMMENT ON COLUMN "public"."doctor_practice_styles"."practice_intensity" IS 'Overall practice style: conservative (fewer investigations), moderate, or aggressive (more investigations)';



COMMENT ON COLUMN "public"."doctor_practice_styles"."preferred_investigation_types" IS 'JSON map of investigation types to acceptance counts';



COMMENT ON COLUMN "public"."doctor_practice_styles"."first_line_by_presentation" IS 'JSON map of presentations to commonly accepted first-line investigations';



COMMENT ON COLUMN "public"."doctor_practice_styles"."confidence_level" IS 'low (<20 feedback), medium (20-100 feedback), high (>100 feedback)';



CREATE OR REPLACE FUNCTION "public"."compute_doctor_practice_style"("p_doctor_id" "uuid") RETURNS "public"."doctor_practice_styles"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $_$
DECLARE
    v_result doctor_practice_styles%ROWTYPE;
    v_total_feedback INT;
    v_accepted_count INT;
    v_rejected_count INT;
    v_total_extractions INT;
    v_avg_inv_per_ext NUMERIC(5,2);
    v_avg_accepted_per_ext NUMERIC(5,2);
    v_acceptance_rate NUMERIC(5,2);
    v_specialty TEXT;
    v_confidence TEXT;
    v_practice_intensity TEXT;
    v_preferred_investigations JSONB;
    v_rejection_reasons JSONB;
    v_first_line JSONB;
BEGIN
    -- Get doctor's specialty
    SELECT d.specialization INTO v_specialty
    FROM doctors d
    WHERE d.id = p_doctor_id;

    -- Get total feedback entries
    SELECT COUNT(*) INTO v_total_feedback
    FROM triage_feedback tf
    WHERE tf.doctor_id = p_doctor_id;

    -- Get accepted and rejected counts
    SELECT
        COUNT(*) FILTER (WHERE feedback_type = 'accepted') as accepted,
        COUNT(*) FILTER (WHERE feedback_type = 'rejected') as rejected
    INTO v_accepted_count, v_rejected_count
    FROM triage_feedback tf
    WHERE tf.doctor_id = p_doctor_id;

    -- Get total unique extractions analyzed
    SELECT COUNT(DISTINCT tsl.extraction_id) INTO v_total_extractions
    FROM triage_suggestion_log tsl
    WHERE tsl.doctor_id = p_doctor_id;

    -- Calculate average investigations per extraction
    SELECT COALESCE(AVG(inv_count), 0) INTO v_avg_inv_per_ext
    FROM (
        SELECT tsl.extraction_id, COUNT(*) as inv_count
        FROM triage_suggestion_log tsl
        WHERE tsl.doctor_id = p_doctor_id
        AND tsl.suggestion_type = 'investigation'
        GROUP BY tsl.extraction_id
    ) subq;

    -- Calculate average accepted suggestions per extraction
    SELECT COALESCE(AVG(accepted_count), 0) INTO v_avg_accepted_per_ext
    FROM (
        SELECT tsl.extraction_id, COUNT(*) as accepted_count
        FROM triage_suggestion_log tsl
        JOIN triage_feedback tf ON tf.suggestion_id = tsl.id
        WHERE tsl.doctor_id = p_doctor_id
        AND tf.feedback_type = 'accepted'
        GROUP BY tsl.extraction_id
    ) subq;

    -- Calculate acceptance rate
    IF v_total_feedback > 0 THEN
        v_acceptance_rate := ROUND((v_accepted_count::NUMERIC / v_total_feedback::NUMERIC) * 100, 2);
    ELSE
        v_acceptance_rate := NULL;
    END IF;

    -- Determine confidence level
    IF v_total_feedback >= 100 THEN
        v_confidence := 'high';
    ELSIF v_total_feedback >= 20 THEN
        v_confidence := 'medium';
    ELSE
        v_confidence := 'low';
    END IF;

    -- Determine practice intensity based on investigation ordering
    IF v_avg_inv_per_ext >= 5 THEN
        v_practice_intensity := 'aggressive';
    ELSIF v_avg_inv_per_ext >= 2 THEN
        v_practice_intensity := 'moderate';
    ELSE
        v_practice_intensity := 'conservative';
    END IF;

    -- Get preferred investigation types (accepted investigations)
    SELECT COALESCE(jsonb_object_agg(inv_type, inv_count), '{}') INTO v_preferred_investigations
    FROM (
        SELECT
            LOWER(SUBSTRING(tsl.suggestion_text FROM 'Consider ordering: (.+)$')) as inv_type,
            COUNT(*) as inv_count
        FROM triage_suggestion_log tsl
        JOIN triage_feedback tf ON tf.suggestion_id = tsl.id
        WHERE tsl.doctor_id = p_doctor_id
        AND tf.feedback_type = 'accepted'
        AND tsl.suggestion_type = 'investigation'
        GROUP BY LOWER(SUBSTRING(tsl.suggestion_text FROM 'Consider ordering: (.+)$'))
        HAVING COUNT(*) >= 2
        ORDER BY inv_count DESC
        LIMIT 20
    ) subq
    WHERE inv_type IS NOT NULL;

    -- Get common rejection reasons
    SELECT COALESCE(jsonb_agg(rejection_data), '[]') INTO v_rejection_reasons
    FROM (
        SELECT jsonb_build_object(
            'pattern', LOWER(SUBSTRING(tsl.suggestion_text, 1, 50)),
            'reason', tf.rejection_reason,
            'count', COUNT(*)
        ) as rejection_data
        FROM triage_suggestion_log tsl
        JOIN triage_feedback tf ON tf.suggestion_id = tsl.id
        WHERE tsl.doctor_id = p_doctor_id
        AND tf.feedback_type = 'rejected'
        AND tf.rejection_reason IS NOT NULL
        GROUP BY LOWER(SUBSTRING(tsl.suggestion_text, 1, 50)), tf.rejection_reason
        HAVING COUNT(*) >= 2
        ORDER BY COUNT(*) DESC
        LIMIT 10
    ) subq;

    -- Build first-line by presentation (placeholder - needs more data)
    v_first_line := '{}';

    -- Upsert into doctor_practice_styles
    INSERT INTO doctor_practice_styles (
        doctor_id,
        specialty,
        practice_intensity,
        avg_investigations_per_extraction,
        avg_suggestions_accepted_per_extraction,
        preferred_investigation_types,
        common_rejection_reasons,
        first_line_by_presentation,
        total_extractions_analyzed,
        total_suggestions_generated,
        total_feedback_entries,
        acceptance_rate,
        confidence_level,
        last_computed_at,
        updated_at
    ) VALUES (
        p_doctor_id,
        v_specialty,
        v_practice_intensity,
        v_avg_inv_per_ext,
        v_avg_accepted_per_ext,
        v_preferred_investigations,
        v_rejection_reasons,
        v_first_line,
        v_total_extractions,
        (SELECT COUNT(*) FROM triage_suggestion_log WHERE doctor_id = p_doctor_id),
        v_total_feedback,
        v_acceptance_rate,
        v_confidence,
        NOW(),
        NOW()
    )
    ON CONFLICT (doctor_id) DO UPDATE SET
        specialty = EXCLUDED.specialty,
        practice_intensity = EXCLUDED.practice_intensity,
        avg_investigations_per_extraction = EXCLUDED.avg_investigations_per_extraction,
        avg_suggestions_accepted_per_extraction = EXCLUDED.avg_suggestions_accepted_per_extraction,
        preferred_investigation_types = EXCLUDED.preferred_investigation_types,
        common_rejection_reasons = EXCLUDED.common_rejection_reasons,
        first_line_by_presentation = EXCLUDED.first_line_by_presentation,
        total_extractions_analyzed = EXCLUDED.total_extractions_analyzed,
        total_suggestions_generated = EXCLUDED.total_suggestions_generated,
        total_feedback_entries = EXCLUDED.total_feedback_entries,
        acceptance_rate = EXCLUDED.acceptance_rate,
        confidence_level = EXCLUDED.confidence_level,
        last_computed_at = EXCLUDED.last_computed_at,
        updated_at = EXCLUDED.updated_at
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$_$;


ALTER FUNCTION "public"."compute_doctor_practice_style"("p_doctor_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."compute_doctor_practice_style"("p_doctor_id" "uuid") IS 'Computes and caches aggregated practice style metrics from triage feedback data';



CREATE TABLE IF NOT EXISTS "public"."hospital_specialty_patterns" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "specialty" "text" NOT NULL,
    "doctor_count" integer DEFAULT 0,
    "total_extractions" integer DEFAULT 0,
    "total_suggestions" integer DEFAULT 0,
    "total_feedback" integer DEFAULT 0,
    "common_investigations" "jsonb" DEFAULT '{}'::"jsonb",
    "common_diagnoses" "jsonb" DEFAULT '{}'::"jsonb",
    "avg_suggestions_per_extraction" numeric(5,2),
    "avg_acceptance_rate" numeric(5,2),
    "investigation_frequency_p25" "jsonb" DEFAULT '{}'::"jsonb",
    "investigation_frequency_p75" "jsonb" DEFAULT '{}'::"jsonb",
    "intensity_distribution" "jsonb" DEFAULT '{}'::"jsonb",
    "last_computed_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."hospital_specialty_patterns" OWNER TO "postgres";


COMMENT ON TABLE "public"."hospital_specialty_patterns" IS 'Aggregated triage patterns by hospital and specialty for peer intelligence';



COMMENT ON COLUMN "public"."hospital_specialty_patterns"."common_investigations" IS 'Investigation name -> frequency (0.0-1.0) showing how often each is ordered';



COMMENT ON COLUMN "public"."hospital_specialty_patterns"."investigation_frequency_p25" IS '25th percentile frequencies for outlier detection (below = conservative)';



COMMENT ON COLUMN "public"."hospital_specialty_patterns"."investigation_frequency_p75" IS '75th percentile frequencies for outlier detection (above = aggressive)';



CREATE OR REPLACE FUNCTION "public"."compute_hospital_specialty_patterns"("p_hospital_id" "uuid", "p_specialty" "text") RETURNS "public"."hospital_specialty_patterns"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $_$
DECLARE
    v_result hospital_specialty_patterns%ROWTYPE;
    v_doctor_count INT;
    v_total_extractions INT;
    v_total_suggestions INT;
    v_total_feedback INT;
    v_common_investigations JSONB;
    v_avg_suggestions NUMERIC(5,2);
    v_avg_acceptance NUMERIC(5,2);
    v_intensity_dist JSONB;
BEGIN
    -- Count doctors with this specialty in hospital
    SELECT COUNT(DISTINCT d.id) INTO v_doctor_count
    FROM doctors d
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- If no doctors, return NULL
    IF v_doctor_count = 0 THEN
        RETURN NULL;
    END IF;

    -- Count total extractions for this specialty
    SELECT COUNT(DISTINCT me.id) INTO v_total_extractions
    FROM medical_extractions me
    JOIN doctors d ON me.doctor_id = d.id
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- Count total suggestions
    SELECT COUNT(*) INTO v_total_suggestions
    FROM triage_suggestion_log tsl
    JOIN doctors d ON tsl.doctor_id = d.id
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- Count total feedback
    SELECT COUNT(*) INTO v_total_feedback
    FROM triage_feedback tf
    JOIN doctors d ON tf.doctor_id = d.id
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- Calculate average suggestions per extraction
    IF v_total_extractions > 0 THEN
        v_avg_suggestions := v_total_suggestions::NUMERIC / v_total_extractions::NUMERIC;
    ELSE
        v_avg_suggestions := 0;
    END IF;

    -- Calculate average acceptance rate
    SELECT COALESCE(
        ROUND(
            (COUNT(*) FILTER (WHERE tf.feedback_type = 'accepted')::NUMERIC /
            NULLIF(COUNT(*), 0)::NUMERIC) * 100, 2
        ), 0
    ) INTO v_avg_acceptance
    FROM triage_feedback tf
    JOIN doctors d ON tf.doctor_id = d.id
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- Get common investigations (aggregated acceptance rates)
    SELECT COALESCE(jsonb_object_agg(inv_type, acceptance_rate), '{}') INTO v_common_investigations
    FROM (
        SELECT
            LOWER(SUBSTRING(tsl.suggestion_text FROM 'Consider ordering: (.+)$')) as inv_type,
            ROUND(
                COUNT(*) FILTER (WHERE tf.feedback_type = 'accepted')::NUMERIC /
                NULLIF(COUNT(*), 0)::NUMERIC, 2
            ) as acceptance_rate
        FROM triage_suggestion_log tsl
        JOIN doctors d ON tsl.doctor_id = d.id
        LEFT JOIN triage_feedback tf ON tf.suggestion_id = tsl.id
        WHERE d.hospital_id = p_hospital_id
        AND d.specialization = p_specialty
        AND tsl.suggestion_type = 'investigation'
        GROUP BY LOWER(SUBSTRING(tsl.suggestion_text FROM 'Consider ordering: (.+)$'))
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC
        LIMIT 20
    ) subq
    WHERE inv_type IS NOT NULL;

    -- Get practice intensity distribution
    SELECT COALESCE(jsonb_object_agg(practice_intensity, doctor_count), '{}') INTO v_intensity_dist
    FROM (
        SELECT practice_intensity, COUNT(*) as doctor_count
        FROM doctor_practice_styles dps
        JOIN doctors d ON dps.doctor_id = d.id
        WHERE d.hospital_id = p_hospital_id
        AND d.specialization = p_specialty
        GROUP BY practice_intensity
    ) subq;

    -- Upsert into hospital_specialty_patterns
    INSERT INTO hospital_specialty_patterns (
        hospital_id,
        specialty,
        doctor_count,
        total_extractions,
        total_suggestions,
        total_feedback,
        common_investigations,
        avg_suggestions_per_extraction,
        avg_acceptance_rate,
        intensity_distribution,
        last_computed_at,
        updated_at
    ) VALUES (
        p_hospital_id,
        p_specialty,
        v_doctor_count,
        v_total_extractions,
        v_total_suggestions,
        v_total_feedback,
        v_common_investigations,
        v_avg_suggestions,
        v_avg_acceptance,
        v_intensity_dist,
        NOW(),
        NOW()
    )
    ON CONFLICT (hospital_id, specialty) DO UPDATE SET
        doctor_count = EXCLUDED.doctor_count,
        total_extractions = EXCLUDED.total_extractions,
        total_suggestions = EXCLUDED.total_suggestions,
        total_feedback = EXCLUDED.total_feedback,
        common_investigations = EXCLUDED.common_investigations,
        avg_suggestions_per_extraction = EXCLUDED.avg_suggestions_per_extraction,
        avg_acceptance_rate = EXCLUDED.avg_acceptance_rate,
        intensity_distribution = EXCLUDED.intensity_distribution,
        last_computed_at = EXCLUDED.last_computed_at,
        updated_at = EXCLUDED.updated_at
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$_$;


ALTER FUNCTION "public"."compute_hospital_specialty_patterns"("p_hospital_id" "uuid", "p_specialty" "text") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."compute_hospital_specialty_patterns"("p_hospital_id" "uuid", "p_specialty" "text") IS 'Computes aggregated triage patterns for a hospital/specialty combination';



CREATE OR REPLACE FUNCTION "public"."copy_hospital_investigation_to_doctor_rpc"("p_hospital_investigation_id" "uuid", "p_doctor_id" "uuid") RETURNS "uuid"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_new_id UUID;
BEGIN
    INSERT INTO doctor_investigations (
        doctor_id,
        investigation_name,
        common_names,
        investigation_type,
        category,
        normal_range,
        loinc_code,
        cpt_code,
        normalized_name,
        search_tokens
    )
    SELECT
        p_doctor_id,
        hi.investigation_name,
        hi.common_names,
        hi.investigation_type,
        hi.category,
        hi.normal_range,
        hi.loinc_code,
        hi.cpt_code,
        hi.normalized_name,
        hi.search_tokens
    FROM hospital_investigation_lists hi
    WHERE hi.id = p_hospital_investigation_id
    ON CONFLICT (doctor_id, normalized_name) DO NOTHING
    RETURNING id INTO v_new_id;

    RETURN v_new_id;
END;
$$;


ALTER FUNCTION "public"."copy_hospital_investigation_to_doctor_rpc"("p_hospital_investigation_id" "uuid", "p_doctor_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."copy_hospital_medicine_to_doctor_rpc"("p_hospital_medicine_id" "uuid", "p_doctor_id" "uuid") RETURNS "uuid"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_new_id UUID;
BEGIN
    INSERT INTO doctor_medicines (
        doctor_id,
        medicine_name,
        common_names,
        category,
        typical_dosage,
        form,
        snomed_code,
        formulary_name,
        medicine_type,
        normalized_name,
        search_tokens
    )
    SELECT
        p_doctor_id,
        hm.medicine_name,
        hm.common_names,
        hm.category,
        hm.typical_dosage,
        hm.form,
        hm.snomed_code,
        hm.formulary_name,
        hm.medicine_type,
        hm.normalized_name,
        hm.search_tokens
    FROM hospital_medicine_lists hm
    WHERE hm.id = p_hospital_medicine_id
    ON CONFLICT (doctor_id, normalized_name) DO NOTHING
    RETURNING id INTO v_new_id;

    RETURN v_new_id;
END;
$$;


ALTER FUNCTION "public"."copy_hospital_medicine_to_doctor_rpc"("p_hospital_medicine_id" "uuid", "p_doctor_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."copy_hospital_medicine_to_doctor_rpc"("p_hospital_medicine_id" "uuid", "p_doctor_id" "uuid") IS 'Copy a hospital medicine to doctors personal list';



CREATE OR REPLACE FUNCTION "public"."exec_sql"("sql_query" "text") RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'extensions', 'pg_temp'
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


ALTER FUNCTION "public"."exec_sql"("sql_query" "text") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."exec_sql"("sql_query" "text") IS 'Execute SELECT queries dynamically for Q&A Engine vector search. Only SELECT allowed.';



CREATE OR REPLACE FUNCTION "public"."get_accuracy_metrics"("p_hospital_id" "uuid" DEFAULT NULL::"uuid", "p_doctor_id" "uuid" DEFAULT NULL::"uuid", "p_date_from" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_date_to" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_group_by" "text" DEFAULT 'total'::"text") RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    result JSONB;
BEGIN
    IF p_group_by = 'total' THEN
        SELECT jsonb_build_object(
            'count', COUNT(*),
            'avg_wer', ROUND(COALESCE(AVG(eam.overall_wer), 0)::numeric, 4),
            'median_wer', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eam.overall_wer), 0)::numeric, 4),
            'p95_wer', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY eam.overall_wer), 0)::numeric, 4),
            'avg_entity_error_rate', ROUND(COALESCE(AVG(eam.entity_error_rate), 0)::numeric, 4),
            'avg_segments_unchanged', ROUND(COALESCE(AVG(eam.segments_unchanged), 0)::numeric, 1),
            'avg_segments_modified', ROUND(COALESCE(AVG(eam.segments_modified), 0)::numeric, 1),
            'avg_doctor_additions', ROUND(COALESCE(AVG(eam.doctor_additions_count), 0)::numeric, 1)
        ) INTO result
        FROM extraction_accuracy_metrics eam
        JOIN doctors d ON d.id = eam.doctor_id
        WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
          AND (p_doctor_id IS NULL OR eam.doctor_id = p_doctor_id)
          AND (p_date_from IS NULL OR eam.computed_at >= p_date_from)
          AND (p_date_to IS NULL OR eam.computed_at < p_date_to + interval '1 day');

    ELSIF p_group_by = 'doctor' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY doctor_name), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'doctor_id', d.id,
                'doctor_name', d.full_name,
                'count', COUNT(*),
                'avg_wer', ROUND(COALESCE(AVG(eam.overall_wer), 0)::numeric, 4),
                'avg_entity_error_rate', ROUND(COALESCE(AVG(eam.entity_error_rate), 0)::numeric, 4),
                'avg_segments_modified', ROUND(COALESCE(AVG(eam.segments_modified), 0)::numeric, 1)
            ) AS row_data, d.full_name AS doctor_name
            FROM extraction_accuracy_metrics eam
            JOIN doctors d ON d.id = eam.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR eam.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR eam.computed_at >= p_date_from)
              AND (p_date_to IS NULL OR eam.computed_at < p_date_to + interval '1 day')
            GROUP BY d.id, d.full_name
        ) sub;

    ELSIF p_group_by = 'weekly' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY week_start), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'week_start', date_trunc('week', eam.computed_at)::date,
                'count', COUNT(*),
                'avg_wer', ROUND(COALESCE(AVG(eam.overall_wer), 0)::numeric, 4),
                'avg_entity_error_rate', ROUND(COALESCE(AVG(eam.entity_error_rate), 0)::numeric, 4)
            ) AS row_data, date_trunc('week', eam.computed_at)::date AS week_start
            FROM extraction_accuracy_metrics eam
            JOIN doctors d ON d.id = eam.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR eam.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR eam.computed_at >= p_date_from)
              AND (p_date_to IS NULL OR eam.computed_at < p_date_to + interval '1 day')
            GROUP BY date_trunc('week', eam.computed_at)::date
        ) sub;

    ELSIF p_group_by = 'monthly' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY month_start), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'month_start', date_trunc('month', eam.computed_at)::date,
                'count', COUNT(*),
                'avg_wer', ROUND(COALESCE(AVG(eam.overall_wer), 0)::numeric, 4),
                'avg_entity_error_rate', ROUND(COALESCE(AVG(eam.entity_error_rate), 0)::numeric, 4)
            ) AS row_data, date_trunc('month', eam.computed_at)::date AS month_start
            FROM extraction_accuracy_metrics eam
            JOIN doctors d ON d.id = eam.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR eam.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR eam.computed_at >= p_date_from)
              AND (p_date_to IS NULL OR eam.computed_at < p_date_to + interval '1 day')
            GROUP BY date_trunc('month', eam.computed_at)::date
        ) sub;
    END IF;

    RETURN COALESCE(result, '{}'::jsonb);
END;
$$;


ALTER FUNCTION "public"."get_accuracy_metrics"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_group_by" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_active_system_prompt_rpc"("p_consultation_type_code" character varying) RETURNS "text"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_assembled_prompt TEXT;
BEGIN
    -- Get the assembled prompt from the active configuration
    SELECT spc.assembled_system_prompt INTO v_assembled_prompt
    FROM consultation_type_system_prompts ctsp
    JOIN system_prompt_configurations spc ON ctsp.system_prompt_config_id = spc.id
    WHERE ctsp.consultation_type_code = p_consultation_type_code
      AND ctsp.is_active = true
      AND spc.is_draft = false
    LIMIT 1;

    RETURN v_assembled_prompt;
END;
$$;


ALTER FUNCTION "public"."get_active_system_prompt_rpc"("p_consultation_type_code" character varying) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_active_template_for_doctor"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid") RETURNS TABLE("template_id" "uuid", "template_code" "text", "template_name" "text", "is_owned" boolean, "is_common" boolean)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.id,
        t.template_code,
        t.template_name,
        (t.doctor_id = p_doctor_id) AS is_owned,
        (t.doctor_id IS NULL) AS is_common
    FROM templates t
    LEFT JOIN doctor_templates dt
        ON dt.template_id = t.id
        AND dt.doctor_id = p_doctor_id
    WHERE t.consultation_type_id = p_consultation_type_id
        AND t.is_active = true
        AND (
            t.doctor_id = p_doctor_id OR  -- Owned by doctor
            t.doctor_id IS NULL OR        -- Common template
            dt.id IS NOT NULL             -- Shared with doctor
        )
        AND (
            dt.is_active = true OR        -- Activated via junction table
            (t.doctor_id = p_doctor_id AND NOT EXISTS (  -- Owner's default if no activation
                SELECT 1 FROM doctor_templates
                WHERE doctor_id = p_doctor_id
                AND is_active = true
            ))
        )
    LIMIT 1;
END;
$$;


ALTER FUNCTION "public"."get_active_template_for_doctor"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_active_template_for_doctor"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid") IS 'Get the currently active template for a doctor and consultation type.
Priority:
1. Explicitly activated template (doctor_templates.is_active=true)
2. Doctor-owned template (if no activation set)
3. Common template (doctor_id=NULL)';



CREATE OR REPLACE FUNCTION "public"."get_ai_acceptance_metrics"("p_hospital_id" "uuid" DEFAULT NULL::"uuid", "p_doctor_id" "uuid" DEFAULT NULL::"uuid", "p_date_from" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_date_to" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_group_by" "text" DEFAULT 'total'::"text") RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    result JSONB;
BEGIN
    IF p_group_by = 'total' THEN
        SELECT jsonb_build_object(
            'total_extractions', COUNT(*),
            'unchanged_count', COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL),
            'edited_count', COUNT(*) FILTER (WHERE me.edit_count > 0),
            'acceptance_rate_pct', ROUND(
                COALESCE(
                    COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL)::NUMERIC
                    / NULLIF(COUNT(*), 0) * 100,
                0), 2
            ),
            'avg_edit_count', ROUND(COALESCE(AVG(me.edit_count)::numeric, 0), 2)
        ) INTO result
        FROM medical_extractions me
        JOIN doctors d ON d.id = me.doctor_id
        WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
          AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
          AND (p_date_from IS NULL OR me.created_at >= p_date_from)
          AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day');

    ELSIF p_group_by = 'daily' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY day), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'date', me.created_at::date,
                'total', COUNT(*),
                'unchanged', COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL),
                'edited', COUNT(*) FILTER (WHERE me.edit_count > 0),
                'acceptance_rate_pct', ROUND(
                    COALESCE(
                        COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL)::NUMERIC
                        / NULLIF(COUNT(*), 0) * 100,
                    0), 2
                )
            ) AS row_data, me.created_at::date AS day
            FROM medical_extractions me
            JOIN doctors d ON d.id = me.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR me.created_at >= p_date_from)
              AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
            GROUP BY me.created_at::date
        ) sub;

    ELSIF p_group_by = 'doctor' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY doctor_name), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'doctor_id', d.id,
                'doctor_name', d.full_name,
                'total', COUNT(*),
                'unchanged', COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL),
                'edited', COUNT(*) FILTER (WHERE me.edit_count > 0),
                'acceptance_rate_pct', ROUND(
                    COALESCE(
                        COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL)::NUMERIC
                        / NULLIF(COUNT(*), 0) * 100,
                    0), 2
                ),
                'avg_edit_count', ROUND(COALESCE(AVG(me.edit_count)::numeric, 0), 2)
            ) AS row_data, d.full_name AS doctor_name
            FROM medical_extractions me
            JOIN doctors d ON d.id = me.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR me.created_at >= p_date_from)
              AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
            GROUP BY d.id, d.full_name
        ) sub;

    ELSIF p_group_by = 'doctor_daily' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY doctor_name, day), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'doctor_id', d.id,
                'doctor_name', d.full_name,
                'date', me.created_at::date,
                'total', COUNT(*),
                'unchanged', COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL),
                'edited', COUNT(*) FILTER (WHERE me.edit_count > 0),
                'acceptance_rate_pct', ROUND(
                    COALESCE(
                        COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL)::NUMERIC
                        / NULLIF(COUNT(*), 0) * 100,
                    0), 2
                )
            ) AS row_data, d.full_name AS doctor_name, me.created_at::date AS day
            FROM medical_extractions me
            JOIN doctors d ON d.id = me.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR me.created_at >= p_date_from)
              AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
            GROUP BY d.id, d.full_name, me.created_at::date
        ) sub;
    END IF;

    RETURN COALESCE(result, '{}'::jsonb);
END;
$$;


ALTER FUNCTION "public"."get_ai_acceptance_metrics"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_group_by" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_avg_pipeline_timing"("p_hospital_id" "uuid" DEFAULT NULL::"uuid", "p_doctor_id" "uuid" DEFAULT NULL::"uuid", "p_date_from" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_date_to" timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'count', COUNT(*),
        'stitching', jsonb_build_object(
            'avg', ROUND(COALESCE(AVG(me.stitching_time_seconds), 0)::numeric, 2),
            'p50', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY me.stitching_time_seconds), 0)::numeric, 2),
            'p95', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY me.stitching_time_seconds), 0)::numeric, 2),
            'p99', ROUND(COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY me.stitching_time_seconds), 0)::numeric, 2)
        ),
        'transcription', jsonb_build_object(
            'avg', ROUND(COALESCE(AVG(me.transcription_time_seconds), 0)::numeric, 2),
            'p50', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY me.transcription_time_seconds), 0)::numeric, 2),
            'p95', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY me.transcription_time_seconds), 0)::numeric, 2),
            'p99', ROUND(COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY me.transcription_time_seconds), 0)::numeric, 2)
        ),
        'extraction', jsonb_build_object(
            'avg', ROUND(COALESCE(AVG(me.extraction_time_seconds), 0)::numeric, 2),
            'p50', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY me.extraction_time_seconds), 0)::numeric, 2),
            'p95', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY me.extraction_time_seconds), 0)::numeric, 2),
            'p99', ROUND(COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY me.extraction_time_seconds), 0)::numeric, 2)
        ),
        'total', jsonb_build_object(
            'avg', ROUND(COALESCE(AVG(me.total_processing_time_seconds), 0)::numeric, 2),
            'p50', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY me.total_processing_time_seconds), 0)::numeric, 2),
            'p95', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY me.total_processing_time_seconds), 0)::numeric, 2),
            'p99', ROUND(COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY me.total_processing_time_seconds), 0)::numeric, 2)
        )
    ) INTO result
    FROM medical_extractions me
    JOIN doctors d ON d.id = me.doctor_id
    WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
      AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
      AND (p_date_from IS NULL OR me.created_at >= p_date_from)
      AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
      AND me.total_processing_time_seconds IS NOT NULL;

    RETURN COALESCE(result, '{}'::jsonb);
END;
$$;


ALTER FUNCTION "public"."get_avg_pipeline_timing"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_client_request_count_last_hour"("p_client_id" "uuid") RETURNS integer
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    request_count INT;
BEGIN
    SELECT COUNT(*)
    INTO request_count
    FROM api_client_usage
    WHERE client_id = p_client_id
      AND created_at > now() - interval '1 hour';
    RETURN request_count;
END;
$$;


ALTER FUNCTION "public"."get_client_request_count_last_hour"("p_client_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_comorbidity_pathway"("p_condition_code" "text", "p_comorbidity" "text") RETURNS TABLE("condition_name" "text", "comorbidity" "text", "content_json" "jsonb", "content_text" "text", "drug_classes" "text"[], "contraindications" "text"[])
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.name,
        ch.comorbidity,
        ch.content_json,
        ch.content_text,
        ch.drug_classes,
        ch.contraindications
    FROM clinical_chunks ch
    JOIN clinical_conditions cc ON ch.condition_id = cc.id
    WHERE cc.is_active = TRUE
    AND cc.condition_id = p_condition_code
    AND ch.chunk_type = 'comorbidity_pathway'
    AND ch.comorbidity = p_comorbidity;
END;
$$;


ALTER FUNCTION "public"."get_comorbidity_pathway"("p_condition_code" "text", "p_comorbidity" "text") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_comorbidity_pathway"("p_condition_code" "text", "p_comorbidity" "text") IS 'Get specific comorbidity pathway for a condition (e.g., HTN + diabetes)';



CREATE OR REPLACE FUNCTION "public"."get_condition_chunks"("p_condition_id" "uuid" DEFAULT NULL::"uuid", "p_condition_code" "text" DEFAULT NULL::"text", "p_chunk_types" "text"[] DEFAULT NULL::"text"[]) RETURNS TABLE("chunk_id" "uuid", "chunk_type" "text", "chunk_index" integer, "content_json" "jsonb", "content_text" "text", "urgency_default" "text", "care_levels" "text"[], "comorbidity" "text", "numeric_thresholds" "jsonb")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        ch.id,
        ch.chunk_type,
        ch.chunk_index,
        ch.content_json,
        ch.content_text,
        ch.urgency_default,
        ch.care_levels,
        ch.comorbidity,
        ch.numeric_thresholds
    FROM clinical_chunks ch
    JOIN clinical_conditions cc ON ch.condition_id = cc.id
    WHERE cc.is_active = TRUE
    AND (p_condition_id IS NULL OR cc.id = p_condition_id)
    AND (p_condition_code IS NULL OR cc.condition_id = p_condition_code)
    AND (p_chunk_types IS NULL OR ch.chunk_type = ANY(p_chunk_types))
    ORDER BY ch.chunk_type, ch.chunk_index;
END;
$$;


ALTER FUNCTION "public"."get_condition_chunks"("p_condition_id" "uuid", "p_condition_code" "text", "p_chunk_types" "text"[]) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_condition_chunks"("p_condition_id" "uuid", "p_condition_code" "text", "p_chunk_types" "text"[]) IS 'Get all chunks for a specific condition, optionally filtered by chunk type';



CREATE OR REPLACE FUNCTION "public"."get_dashboard_summary"("p_hospital_id" "uuid" DEFAULT NULL::"uuid", "p_doctor_id" "uuid" DEFAULT NULL::"uuid", "p_start_date" "date" DEFAULT NULL::"date", "p_end_date" "date" DEFAULT NULL::"date", "p_min_priority_score" integer DEFAULT 50) RETURNS json
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_doctor_ids UUID[];
    v_result JSON;
BEGIN
    -- Get doctor IDs for hospital filter (done once, reused)
    IF p_hospital_id IS NOT NULL THEN
        SELECT ARRAY_AGG(id) INTO v_doctor_ids
        FROM doctors
        WHERE hospital_id = p_hospital_id AND is_active = TRUE;

        -- If no doctors found, return empty result
        IF v_doctor_ids IS NULL OR array_length(v_doctor_ids, 1) IS NULL THEN
            RETURN json_build_object(
                'total_patients', 0,
                'patients_with_interventions', 0,
                'revenue_potential', 0,
                'by_category', '[]'::json,
                'by_department', '[]'::json,
                'by_doctor', '[]'::json
            );
        END IF;
    END IF;

    -- If specific doctor_id provided, use that
    IF p_doctor_id IS NOT NULL THEN
        v_doctor_ids := ARRAY[p_doctor_id];
    END IF;

    -- Single aggregated query
    WITH filtered_interventions AS (
        -- Base filtered data
        SELECT
            pi.id,
            pi.intervention_code,
            pi.intervention_category,
            pi.priority_score,
            pi.take_up_likelihood,
            pi.revenue_estimate,
            pi.created_at,
            me.patient_id,
            me.doctor_id,
            d.full_name as doctor_name,
            d.specialization
        FROM patient_interventions pi
        INNER JOIN medical_extractions me ON pi.extraction_id = me.id
        INNER JOIN doctors d ON me.doctor_id = d.id
        WHERE pi.priority_score >= p_min_priority_score
          AND pi.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND pi.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
    ),
    -- Category aggregation
    category_stats AS (
        SELECT
            intervention_category as category,
            COUNT(DISTINCT patient_id) as patient_count,
            COUNT(*) as intervention_count,
            COALESCE(SUM(revenue_estimate), 0) as revenue_potential,
            -- Aggregate risk score: 100 - weighted avg take_up_likelihood
            CASE
                WHEN SUM(priority_score) > 0 THEN
                    100 - (SUM(COALESCE(take_up_likelihood, 50) * priority_score) / SUM(priority_score))
                ELSE 50
            END as aggregate_risk_score
        FROM filtered_interventions
        GROUP BY intervention_category
    ),
    -- Department (specialization) aggregation
    dept_stats AS (
        SELECT
            COALESCE(specialization, 'General') as dept_name,
            intervention_category,
            COUNT(DISTINCT patient_id) as patient_count
        FROM filtered_interventions
        GROUP BY COALESCE(specialization, 'General'), intervention_category
    ),
    dept_summary AS (
        SELECT
            dept_name,
            json_object_agg(intervention_category, patient_count) as by_category,
            SUM(patient_count) as total_at_risk
        FROM dept_stats
        GROUP BY dept_name
    ),
    -- Doctor aggregation
    doctor_stats AS (
        SELECT
            doctor_id,
            doctor_name,
            specialization,
            intervention_category,
            COUNT(DISTINCT patient_id) as patient_count
        FROM filtered_interventions
        GROUP BY doctor_id, doctor_name, specialization, intervention_category
    ),
    doctor_summary AS (
        SELECT
            doctor_id::text as id,
            doctor_name as name,
            specialization,
            json_object_agg(intervention_category, patient_count) as by_category,
            SUM(patient_count) as total_at_risk
        FROM doctor_stats
        GROUP BY doctor_id, doctor_name, specialization
    ),
    -- Overall totals
    totals AS (
        SELECT
            COUNT(DISTINCT patient_id) as patients_with_interventions,
            COALESCE(SUM(revenue_estimate), 0) as revenue_potential
        FROM filtered_interventions
    ),
    -- Total patients (from medical_extractions in the period)
    total_patients AS (
        SELECT COUNT(DISTINCT patient_id) as total
        FROM medical_extractions me
        WHERE me.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND me.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
    )
    SELECT json_build_object(
        'total_patients', (SELECT total FROM total_patients),
        'patients_with_interventions', (SELECT patients_with_interventions FROM totals),
        'revenue_potential', (SELECT revenue_potential FROM totals),
        'by_category', COALESCE((
            SELECT json_agg(json_build_object(
                'category', category,
                'patient_count', patient_count,
                'intervention_count', intervention_count,
                'revenue_potential', revenue_potential,
                'aggregate_risk_score', ROUND(aggregate_risk_score::numeric, 1),
                'risk_band', CASE
                    WHEN aggregate_risk_score >= 60 THEN 'HIGH'
                    WHEN aggregate_risk_score >= 40 THEN 'MEDIUM'
                    ELSE 'LOW'
                END
            ) ORDER BY patient_count DESC)
            FROM category_stats
        ), '[]'::json),
        'by_department', COALESCE((
            SELECT json_agg(json_build_object(
                'id', dept_name,
                'name', dept_name,
                'by_category', by_category,
                'total_at_risk', total_at_risk
            ) ORDER BY total_at_risk DESC)
            FROM dept_summary
        ), '[]'::json),
        'by_doctor', COALESCE((
            SELECT json_agg(json_build_object(
                'id', id,
                'name', name,
                'specialization', specialization,
                'by_category', by_category,
                'total_at_risk', total_at_risk
            ) ORDER BY total_at_risk DESC)
            FROM doctor_summary
        ), '[]'::json)
    ) INTO v_result;

    RETURN v_result;
END;
$$;


ALTER FUNCTION "public"."get_dashboard_summary"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_start_date" "date", "p_end_date" "date", "p_min_priority_score" integer) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_dashboard_summary"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_start_date" "date", "p_end_date" "date", "p_min_priority_score" integer) IS 'Optimized dashboard summary aggregation - single query replaces multiple API calls';



CREATE OR REPLACE FUNCTION "public"."get_dashboard_summary_v2"("p_hospital_id" "uuid" DEFAULT NULL::"uuid", "p_doctor_id" "uuid" DEFAULT NULL::"uuid", "p_start_date" "date" DEFAULT NULL::"date", "p_end_date" "date" DEFAULT NULL::"date", "p_min_priority_score" integer DEFAULT 50) RETURNS json
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_doctor_ids UUID[];
    v_result JSON;
BEGIN
    -- Get doctor IDs for hospital filter (done once, reused)
    IF p_hospital_id IS NOT NULL THEN
        SELECT ARRAY_AGG(id) INTO v_doctor_ids
        FROM doctors
        WHERE hospital_id = p_hospital_id AND is_active = TRUE;

        -- If no doctors found, return empty result
        IF v_doctor_ids IS NULL OR array_length(v_doctor_ids, 1) IS NULL THEN
            RETURN json_build_object(
                'total_patients', 0,
                'patients_with_interventions', 0,
                'revenue_potential', 0,
                'by_category', '[]'::json,
                'by_department', '[]'::json,
                'by_doctor', '[]'::json,
                'by_patient', '[]'::json
            );
        END IF;
    END IF;

    -- If specific doctor_id provided, use that
    IF p_doctor_id IS NOT NULL THEN
        v_doctor_ids := ARRAY[p_doctor_id];
    END IF;

    -- Single aggregated query
    WITH filtered_interventions AS (
        -- Base filtered data with category remapping: 7 DB categories → 6 dashboard categories
        -- Key change from v2: FOLLOWUP_DUE stays as FOLLOWUP_DUE (not remapped to TREATMENT_COMPLIANCE)
        SELECT
            pi.id,
            pi.intervention_code,
            pi.intervention_category AS db_category,
            CASE pi.intervention_category
                WHEN 'FOLLOWUP_DUE' THEN 'FOLLOWUP_DUE'
                WHEN 'RETENTION_RISK' THEN 'DROP_OFF_RISK'
                WHEN 'RX_REFILL' THEN 'HEALTH_SERVICES'
                WHEN 'DIAGNOSTICS_DUE' THEN 'HEALTH_SERVICES'
                WHEN 'ALLIED_HEALTH' THEN 'HEALTH_SERVICES'
                WHEN 'OP_TO_IP' THEN 'SURGERY_CANDIDATE'
                WHEN 'QUALITY_RISK' THEN 'QUALITY_RISK'
                ELSE 'QUALITY_RISK'
            END AS dashboard_category,
            pi.priority_score,
            pi.take_up_likelihood,
            pi.revenue_estimate,
            pi.created_at,
            me.patient_id,
            me.doctor_id,
            d.full_name as doctor_name,
            d.specialization
        FROM patient_interventions pi
        INNER JOIN medical_extractions me ON pi.extraction_id = me.id
        INNER JOIN doctors d ON me.doctor_id = d.id
        WHERE pi.priority_score >= p_min_priority_score
          AND pi.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND pi.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
    ),
    -- Score-based metrics from patient_dropoff_risk (for TREATMENT_COMPLIANCE and DROP_OFF_RISK)
    dropoff_scores AS (
        SELECT
            AVG(
                CASE pdr.compliance_likelihood
                    WHEN 'Very Low' THEN 10
                    WHEN 'Low' THEN 35
                    WHEN 'Moderate' THEN 65
                    WHEN 'High' THEN 90
                    ELSE 50
                END
            ) AS avg_compliance_score,
            AVG(pdr.dropoff_probability) AS avg_dropoff_probability,
            COUNT(DISTINCT pdr.patient_id) FILTER (WHERE pdr.compliance_likelihood IN ('Very Low', 'Low')) AS low_compliance_count,
            COUNT(DISTINCT pdr.patient_id) FILTER (WHERE pdr.dropoff_probability >= 40) AS high_dropoff_count
        FROM patient_dropoff_risk pdr
        INNER JOIN medical_extractions me ON pdr.extraction_id = me.id
        WHERE pdr.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND pdr.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
    ),
    -- Category aggregation using intervention-based dashboard categories (5 of 6 - excludes TREATMENT_COMPLIANCE)
    category_stats AS (
        SELECT
            dashboard_category as category,
            COUNT(DISTINCT patient_id) as patient_count,
            COUNT(*) as intervention_count,
            COALESCE(SUM(revenue_estimate), 0) as revenue_potential,
            -- Aggregate risk score: 100 - weighted avg take_up_likelihood
            CASE
                WHEN SUM(priority_score) > 0 THEN
                    100 - (SUM(COALESCE(take_up_likelihood, 50) * priority_score) / SUM(priority_score))
                ELSE 50
            END as aggregate_risk_score
        FROM filtered_interventions
        GROUP BY dashboard_category
    ),
    -- Enrich category stats with score-based metrics + add TREATMENT_COMPLIANCE as score-only row
    enriched_categories AS (
        -- Intervention-based categories (FOLLOWUP_DUE, DROP_OFF_RISK, HEALTH_SERVICES, SURGERY_CANDIDATE, QUALITY_RISK)
        SELECT
            cs.category,
            cs.patient_count::bigint,
            cs.intervention_count::bigint,
            cs.revenue_potential::numeric,
            cs.aggregate_risk_score::double precision,
            CASE
                WHEN cs.aggregate_risk_score >= 60 THEN 'HIGH'
                WHEN cs.aggregate_risk_score >= 40 THEN 'MEDIUM'
                ELSE 'LOW'
            END AS risk_band,
            NULL::double precision AS avg_compliance_score,
            CASE WHEN cs.category = 'DROP_OFF_RISK' THEN (SELECT avg_dropoff_probability FROM dropoff_scores) ELSE NULL END::double precision AS avg_dropoff_probability
        FROM category_stats cs

        UNION ALL

        -- TREATMENT_COMPLIANCE: score-only from patient_dropoff_risk (no interventions)
        SELECT
            'TREATMENT_COMPLIANCE'::text AS category,
            COALESCE((SELECT low_compliance_count FROM dropoff_scores), 0)::bigint AS patient_count,
            0::bigint AS intervention_count,
            0::numeric AS revenue_potential,
            CASE
                WHEN (SELECT avg_compliance_score FROM dropoff_scores) IS NOT NULL
                    THEN 100.0 - (SELECT avg_compliance_score FROM dropoff_scores)
                ELSE 50.0
            END::double precision AS aggregate_risk_score,
            CASE
                WHEN (SELECT avg_compliance_score FROM dropoff_scores) IS NOT NULL THEN
                    CASE
                        WHEN 100.0 - (SELECT avg_compliance_score FROM dropoff_scores) >= 60 THEN 'HIGH'
                        WHEN 100.0 - (SELECT avg_compliance_score FROM dropoff_scores) >= 40 THEN 'MEDIUM'
                        ELSE 'LOW'
                    END
                ELSE 'MEDIUM'
            END AS risk_band,
            (SELECT avg_compliance_score FROM dropoff_scores)::double precision AS avg_compliance_score,
            NULL::double precision AS avg_dropoff_probability
    ),
    -- Department (specialization) aggregation with 6 categories
    dept_stats AS (
        SELECT
            COALESCE(specialization, 'General') as dept_name,
            dashboard_category,
            COUNT(DISTINCT patient_id) as patient_count
        FROM filtered_interventions
        GROUP BY COALESCE(specialization, 'General'), dashboard_category
    ),
    dept_summary AS (
        SELECT
            dept_name,
            json_object_agg(dashboard_category, patient_count) as by_category,
            SUM(patient_count) as total_at_risk
        FROM dept_stats
        GROUP BY dept_name
    ),
    -- Doctor aggregation with 6 categories
    doctor_stats AS (
        SELECT
            doctor_id,
            doctor_name,
            specialization,
            dashboard_category,
            COUNT(DISTINCT patient_id) as patient_count
        FROM filtered_interventions
        GROUP BY doctor_id, doctor_name, specialization, dashboard_category
    ),
    doctor_summary AS (
        SELECT
            doctor_id::text as id,
            doctor_name as name,
            specialization,
            json_object_agg(dashboard_category, patient_count) as by_category,
            SUM(patient_count) as total_at_risk
        FROM doctor_stats
        GROUP BY doctor_id, doctor_name, specialization
    ),
    -- Overall totals
    totals AS (
        SELECT
            COUNT(DISTINCT patient_id) as patients_with_interventions,
            COALESCE(SUM(revenue_estimate), 0) as revenue_potential
        FROM filtered_interventions
    ),
    -- Total patients (from medical_extractions in the period)
    total_patients AS (
        SELECT COUNT(DISTINCT patient_id) as total
        FROM medical_extractions me
        WHERE me.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND me.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
    ),
    -- Per-patient metrics (by_patient array)
    patient_dropoff AS (
        -- Get latest dropoff risk per patient in the period
        SELECT DISTINCT ON (pdr.patient_id)
            pdr.patient_id,
            pdr.compliance_likelihood,
            pdr.dropoff_probability
        FROM patient_dropoff_risk pdr
        INNER JOIN medical_extractions me ON pdr.extraction_id = me.id
        WHERE pdr.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND pdr.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
        ORDER BY pdr.patient_id, pdr.created_at DESC
    ),
    patient_intervention_flags AS (
        SELECT
            fi.patient_id,
            BOOL_OR(fi.db_category = 'OP_TO_IP') AS is_surgery_candidate,
            COUNT(*) FILTER (WHERE fi.db_category IN ('RX_REFILL', 'DIAGNOSTICS_DUE', 'ALLIED_HEALTH')) AS health_service_count,
            BOOL_OR(fi.db_category = 'FOLLOWUP_DUE') AS has_followup_due,
            COUNT(*) FILTER (WHERE fi.db_category = 'FOLLOWUP_DUE') AS followup_count
        FROM filtered_interventions fi
        GROUP BY fi.patient_id
    ),
    patient_metrics AS (
        SELECT
            COALESCE(pd.patient_id, pif.patient_id) AS patient_id,
            p.full_name AS patient_name,
            p.patient_id AS mrn,
            pd.compliance_likelihood,
            pd.dropoff_probability,
            COALESCE(pif.is_surgery_candidate, FALSE) AS is_surgery_candidate,
            COALESCE(pif.health_service_count, 0) AS health_service_count,
            CASE
                WHEN COALESCE(pif.health_service_count, 0) >= 2 THEN 'High'
                WHEN COALESCE(pif.health_service_count, 0) = 1 THEN 'Medium'
                ELSE 'Low'
            END AS health_service_level,
            COALESCE(pif.has_followup_due, FALSE) AS has_followup_due,
            COALESCE(pif.followup_count, 0) AS followup_count
        FROM patient_dropoff pd
        FULL OUTER JOIN patient_intervention_flags pif ON pd.patient_id = pif.patient_id
        LEFT JOIN patients p ON COALESCE(pd.patient_id, pif.patient_id) = p.id
        WHERE pd.patient_id IS NOT NULL OR pif.patient_id IS NOT NULL
    )
    SELECT json_build_object(
        'total_patients', (SELECT total FROM total_patients),
        'patients_with_interventions', (SELECT patients_with_interventions FROM totals),
        'revenue_potential', (SELECT revenue_potential FROM totals),
        'by_category', COALESCE((
            SELECT json_agg(json_build_object(
                'category', category,
                'patient_count', patient_count,
                'intervention_count', intervention_count,
                'revenue_potential', revenue_potential,
                'aggregate_risk_score', ROUND(aggregate_risk_score::numeric, 1),
                'risk_band', risk_band,
                'avg_compliance_score', ROUND(avg_compliance_score::numeric, 1),
                'avg_dropoff_probability', ROUND(avg_dropoff_probability::numeric, 1)
            ) ORDER BY patient_count DESC)
            FROM enriched_categories
        ), '[]'::json),
        'by_department', COALESCE((
            SELECT json_agg(json_build_object(
                'id', dept_name,
                'name', dept_name,
                'by_category', by_category,
                'total_at_risk', total_at_risk
            ) ORDER BY total_at_risk DESC)
            FROM dept_summary
        ), '[]'::json),
        'by_doctor', COALESCE((
            SELECT json_agg(json_build_object(
                'id', id,
                'name', name,
                'specialization', specialization,
                'by_category', by_category,
                'total_at_risk', total_at_risk
            ) ORDER BY total_at_risk DESC)
            FROM doctor_summary
        ), '[]'::json),
        'by_patient', COALESCE((
            SELECT json_agg(json_build_object(
                'patient_id', patient_id,
                'patient_name', COALESCE(patient_name, 'Unknown'),
                'mrn', mrn,
                'compliance_likelihood', compliance_likelihood,
                'dropoff_probability', dropoff_probability,
                'is_surgery_candidate', is_surgery_candidate,
                'health_service_count', health_service_count,
                'health_service_level', health_service_level,
                'has_followup_due', has_followup_due,
                'followup_count', followup_count
            ) ORDER BY dropoff_probability DESC NULLS LAST)
            FROM patient_metrics
        ), '[]'::json)
    ) INTO v_result;

    RETURN v_result;
END;
$$;


ALTER FUNCTION "public"."get_dashboard_summary_v2"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_start_date" "date", "p_end_date" "date", "p_min_priority_score" integer) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_dashboard_summary_v2"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_start_date" "date", "p_end_date" "date", "p_min_priority_score" integer) IS 'Dashboard summary v3 - 6 dashboard categories: TREATMENT_COMPLIANCE (score-only), FOLLOWUP_DUE (intervention-based), and 4 others';



CREATE OR REPLACE FUNCTION "public"."get_doctor_ehr_config"("p_doctor_id" "uuid", "p_template_code" character varying DEFAULT NULL::character varying) RETURNS TABLE("ehr_code" character varying, "hospital_id" "uuid", "api_url" "text", "api_key" "text", "url_suffix" character varying)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        et.ehr_code,
        d.hospital_id,
        COALESCE(he.api_url, et.default_api_url) as api_url,  -- Hospital overrides default
        he.api_key,
        te.url_suffix  -- Template + EHR specific suffix (e.g., neo_daily + neopead)
    FROM doctors d
    JOIN ehr_types et ON et.id = d.ehr_type_id
    JOIN hospital_ehr he ON he.hospital_id = d.hospital_id AND he.ehr_type_id = d.ehr_type_id
    LEFT JOIN templates t ON UPPER(t.template_code) = UPPER(p_template_code)
    LEFT JOIN template_ehr te ON te.template_id = t.id AND te.ehr_type_id = d.ehr_type_id
    WHERE d.id = p_doctor_id
      AND he.is_enabled = true
      AND COALESCE(he.api_url, et.default_api_url) IS NOT NULL;
END;
$$;


ALTER FUNCTION "public"."get_doctor_ehr_config"("p_doctor_id" "uuid", "p_template_code" character varying) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_doctor_ehr_config"("p_doctor_id" "uuid", "p_template_code" character varying) IS 'Single query for EHR routing. Returns NULL if doctor has no EHR or config is incomplete.';



CREATE OR REPLACE FUNCTION "public"."get_doctor_feedback_patterns"("p_doctor_id" "uuid") RETURNS TABLE("suggestion_text" "text", "suggestion_type" "text", "source_layer" "text", "total_shown" integer, "accepted_count" integer, "rejected_count" integer, "modified_count" integer, "rejection_reasons" "text"[], "modified_versions" "text"[], "acceptance_rate" numeric, "last_feedback_at" timestamp with time zone)
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        tsl.suggestion_text,
        tsl.suggestion_type,
        tsl.source_layer,
        COUNT(DISTINCT tsl.id)::INT as total_shown,
        COUNT(tf.id) FILTER (WHERE tf.feedback_type = 'accepted')::INT as accepted_count,
        COUNT(tf.id) FILTER (WHERE tf.feedback_type = 'rejected')::INT as rejected_count,
        COUNT(tf.id) FILTER (WHERE tf.feedback_type = 'modified')::INT as modified_count,
        ARRAY_AGG(DISTINCT tf.rejection_reason) FILTER (WHERE tf.rejection_reason IS NOT NULL) as rejection_reasons,
        ARRAY_AGG(DISTINCT tf.modified_text) FILTER (WHERE tf.modified_text IS NOT NULL) as modified_versions,
        CASE
            WHEN COUNT(tf.id) > 0
            THEN ROUND(
                COUNT(tf.id) FILTER (WHERE tf.feedback_type = 'accepted')::NUMERIC /
                COUNT(tf.id)::NUMERIC * 100, 1
            )
            ELSE NULL
        END as acceptance_rate,
        MAX(tf.feedback_at) as last_feedback_at
    FROM triage_suggestion_log tsl
    LEFT JOIN triage_feedback tf ON tsl.id = tf.suggestion_id
    WHERE tsl.doctor_id = p_doctor_id
    GROUP BY tsl.suggestion_text, tsl.suggestion_type, tsl.source_layer
    HAVING COUNT(tf.id) > 0  -- Only return suggestions that have feedback
    ORDER BY COUNT(tf.id) DESC;  -- Most feedback first
END;
$$;


ALTER FUNCTION "public"."get_doctor_feedback_patterns"("p_doctor_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_doctor_feedback_patterns"("p_doctor_id" "uuid") IS 'Aggregates all feedback for a doctor to learn suggestion preferences';



CREATE OR REPLACE FUNCTION "public"."get_doctor_practice_style"("p_doctor_id" "uuid", "p_max_age_hours" integer DEFAULT 24) RETURNS "public"."doctor_practice_styles"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_result doctor_practice_styles%ROWTYPE;
    v_last_computed TIMESTAMPTZ;
BEGIN
    -- Check for existing cached style
    SELECT * INTO v_result
    FROM doctor_practice_styles
    WHERE doctor_id = p_doctor_id;

    -- If no cache or cache is stale, recompute
    IF v_result IS NULL OR
       v_result.last_computed_at < NOW() - (p_max_age_hours || ' hours')::INTERVAL THEN
        v_result := compute_doctor_practice_style(p_doctor_id);
    END IF;

    RETURN v_result;
END;
$$;


ALTER FUNCTION "public"."get_doctor_practice_style"("p_doctor_id" "uuid", "p_max_age_hours" integer) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_doctor_practice_style"("p_doctor_id" "uuid", "p_max_age_hours" integer) IS 'Returns cached practice style or computes fresh if stale';



CREATE OR REPLACE FUNCTION "public"."get_doctor_preference_patterns"("p_doctor_id" "uuid") RETURNS TABLE("suggestion_pattern" "text", "suggestion_type" "text", "acceptance_count" integer, "avg_priority_rank" numeric)
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        LOWER(LEFT(tsl.suggestion_text, 100)) as suggestion_pattern,
        tsl.suggestion_type,
        COUNT(*)::INT as acceptance_count,
        ROUND(AVG(tsl.priority_rank), 1) as avg_priority_rank
    FROM triage_feedback tf
    JOIN triage_suggestion_log tsl ON tf.suggestion_id = tsl.id
    WHERE tsl.doctor_id = p_doctor_id
      AND tf.feedback_type = 'accepted'
    GROUP BY LOWER(LEFT(tsl.suggestion_text, 100)), tsl.suggestion_type
    HAVING COUNT(*) >= 3  -- Only patterns accepted 3+ times
    ORDER BY COUNT(*) DESC;
END;
$$;


ALTER FUNCTION "public"."get_doctor_preference_patterns"("p_doctor_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_doctor_preference_patterns"("p_doctor_id" "uuid") IS 'Returns suggestions accepted 3+ times by a doctor for boosting';



CREATE OR REPLACE FUNCTION "public"."get_doctor_rejection_patterns"("p_doctor_id" "uuid") RETURNS TABLE("suggestion_pattern" "text", "suggestion_type" "text", "rejection_count" integer, "common_reasons" "text"[])
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        -- Normalize suggestion text for pattern matching (first 100 chars, lowercase)
        LOWER(LEFT(tsl.suggestion_text, 100)) as suggestion_pattern,
        tsl.suggestion_type,
        COUNT(*)::INT as rejection_count,
        ARRAY_AGG(DISTINCT tf.rejection_reason) FILTER (WHERE tf.rejection_reason IS NOT NULL) as common_reasons
    FROM triage_feedback tf
    JOIN triage_suggestion_log tsl ON tf.suggestion_id = tsl.id
    WHERE tsl.doctor_id = p_doctor_id
      AND tf.feedback_type = 'rejected'
    GROUP BY LOWER(LEFT(tsl.suggestion_text, 100)), tsl.suggestion_type
    HAVING COUNT(*) >= 2  -- Only patterns rejected 2+ times
    ORDER BY COUNT(*) DESC;
END;
$$;


ALTER FUNCTION "public"."get_doctor_rejection_patterns"("p_doctor_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_doctor_rejection_patterns"("p_doctor_id" "uuid") IS 'Returns suggestions rejected 2+ times by a doctor for filtering';



CREATE OR REPLACE FUNCTION "public"."get_doctor_segment_configuration"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid", "p_template_id" "uuid" DEFAULT NULL::"uuid", "p_mode" character varying DEFAULT 'full'::character varying) RETURNS TABLE("segment_code" character varying, "segment_name" character varying, "prompt_section_text" "text", "schema_definition_json" "jsonb", "category" character varying, "display_order" integer, "brevity_level" character varying, "terminology_style" character varying, "is_required" boolean)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (sd.segment_code)
        sd.segment_code::VARCHAR,
        sd.segment_name::VARCHAR,

        -- Prompt section: segment-default only (no doctor-specific customization)
        sd.prompt_section_text,

        -- Schema: segment-default only (no doctor-specific customization)
        sd.schema_definition_json,

        -- Category: template → consultation type → segment-default
        COALESCE(
            ts.category,
            cts.default_category,
            sd.default_category
        )::VARCHAR AS category,

        -- Display order: template → consultation type → segment-default
        COALESCE(
            ts.display_order,
            cts.default_display_order,
            sd.display_order
        ) AS display_order,

        -- Brevity level: template → consultation type → segment-default
        COALESCE(
            ts.brevity_level,
            cts.default_brevity_level,
            sd.default_brevity_level
        )::VARCHAR AS brevity_level,

        -- Terminology style: template → consultation type → segment-default
        COALESCE(
            ts.terminology_style,
            cts.default_terminology_style,
            sd.default_terminology_style
        )::VARCHAR AS terminology_style,

        -- Is required: always from segment definition
        sd.is_required AS is_required

    FROM segment_definitions sd

    -- Join via consultation_type_segments junction table
    LEFT JOIN consultation_type_segments cts
        ON cts.segment_id = sd.id
        AND cts.consultation_type_id = p_consultation_type_id

    -- Join template segment configuration (using template_segments)
    LEFT JOIN template_segments ts
        ON ts.segment_id = sd.id
        AND ts.template_id = p_template_id
        AND p_template_id IS NOT NULL

    WHERE sd.is_active = TRUE
        AND (
            -- Segment is assigned to this consultation type via junction table
            cts.segment_id IS NOT NULL
            OR
            -- OR segment is in doctor's template (template-specific segments)
            ts.segment_id IS NOT NULL
        )
        AND (
            -- Mode filter: include segments based on mode
            p_mode = 'full' OR
            (p_mode = 'core' AND COALESCE(
                ts.category,
                cts.default_category,
                sd.default_category
            ) = 'core') OR
            (p_mode = 'additional' AND COALESCE(
                ts.category,
                cts.default_category,
                sd.default_category
            ) = 'additional')
        )
        -- ALWAYS exclude 'excluded' segments
        AND COALESCE(
            ts.category,
            cts.default_category,
            sd.default_category
        ) != 'excluded'

    ORDER BY sd.segment_code, COALESCE(
        ts.display_order,
        cts.default_display_order,
        sd.display_order
    );
END;
$$;


ALTER FUNCTION "public"."get_doctor_segment_configuration"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid", "p_template_id" "uuid", "p_mode" character varying) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_enabled_triage_layers"("p_doctor_id" "uuid" DEFAULT NULL::"uuid") RETURNS TABLE("layer_code" "text", "layer_name" "text", "is_enabled" boolean, "weight" numeric, "config" "jsonb")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        tlc.layer_code::TEXT,
        tlc.layer_name::TEXT,
        -- Check global enable first, then doctor preference if exists
        CASE
            WHEN tlc.layer_code = 'base_mvp' THEN TRUE  -- Base layer always enabled
            WHEN dlp.id IS NOT NULL THEN
                CASE tlc.layer_code
                    WHEN 'doctor_practice' THEN COALESCE(dlp.enable_doctor_practice_layer, TRUE)
                    WHEN 'hospital_intelligence' THEN COALESCE(dlp.enable_hospital_intelligence_layer, TRUE)
                    WHEN 'rag_guidelines' THEN COALESCE(dlp.enable_rag_guidelines_layer, TRUE)
                    ELSE tlc.is_enabled
                END
            ELSE tlc.is_enabled
        END as is_enabled,
        -- Get weight from doctor preferences if available, otherwise global config
        CASE
            WHEN dlp.id IS NOT NULL THEN
                CASE tlc.layer_code
                    WHEN 'base_mvp' THEN COALESCE(dlp.weight_base_mvp, tlc.weight)
                    WHEN 'doctor_practice' THEN COALESCE(dlp.weight_doctor_practice, tlc.weight)
                    WHEN 'hospital_intelligence' THEN COALESCE(dlp.weight_hospital_intelligence, tlc.weight)
                    WHEN 'rag_guidelines' THEN COALESCE(dlp.weight_rag_guidelines, tlc.weight)
                    ELSE tlc.weight
                END
            ELSE tlc.weight
        END as weight,
        tlc.config
    FROM triage_layer_config tlc
    LEFT JOIN doctor_layer_preferences dlp ON dlp.doctor_id = p_doctor_id
    ORDER BY tlc.display_order;
END;
$$;


ALTER FUNCTION "public"."get_enabled_triage_layers"("p_doctor_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_enabled_triage_layers"("p_doctor_id" "uuid") IS 'Returns all triage layers with enable status and weights, respecting doctor preferences';



CREATE OR REPLACE FUNCTION "public"."get_hospital_default_ehr_type_id"("p_hospital_id" "uuid") RETURNS "uuid"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_ehr_type_id UUID;
BEGIN
    SELECT ehr_type_id INTO v_ehr_type_id
    FROM hospital_ehr
    WHERE hospital_id = p_hospital_id
      AND is_default = true
      AND is_enabled = true
    LIMIT 1;

    RETURN v_ehr_type_id;
END;
$$;


ALTER FUNCTION "public"."get_hospital_default_ehr_type_id"("p_hospital_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_hospital_default_ehr_type_id"("p_hospital_id" "uuid") IS 'Returns the default EHR type ID for a hospital (for auto-assigning to new doctors).';



CREATE OR REPLACE FUNCTION "public"."get_intervention_stats_by_doctor"("p_doctor_id" "uuid", "p_date_from" timestamp with time zone DEFAULT ("now"() - '30 days'::interval), "p_date_to" timestamp with time zone DEFAULT "now"()) RETURNS TABLE("intervention_code" "text", "intervention_name" "text", "intervention_category" "text", "total_count" bigint, "top_3_count" bigint, "effectiveness_rate" numeric)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        ia.intervention_code,
        ia.intervention_name,
        ia.intervention_category,
        COUNT(*)::BIGINT AS total_count,
        COUNT(*) FILTER (WHERE ia.is_top_recommendation)::BIGINT AS top_3_count,
        CASE
            WHEN COUNT(*) FILTER (WHERE ia.outcome IS NOT NULL) > 0
            THEN ROUND((COUNT(*) FILTER (WHERE ia.outcome = 'effective')::DECIMAL / COUNT(*) FILTER (WHERE ia.outcome IS NOT NULL)) * 100, 1)
            ELSE NULL
        END AS effectiveness_rate
    FROM intervention_analytics ia
    WHERE ia.doctor_id = p_doctor_id
      AND ia.recommended_at BETWEEN p_date_from AND p_date_to
    GROUP BY ia.intervention_code, ia.intervention_name, ia.intervention_category
    ORDER BY total_count DESC;
END;
$$;


ALTER FUNCTION "public"."get_intervention_stats_by_doctor"("p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_investigation_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) RETURNS TABLE("matched_investigation_name" character varying, "correct_investigation_name" character varying, "feedback_status" character varying, "match_confidence" numeric)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        iml.matched_investigation_name,
        iml.correct_investigation_name,
        iml.feedback_status,
        iml.match_confidence
    FROM investigation_match_log iml
    WHERE iml.doctor_id = p_doctor_id
      AND LOWER(iml.original_investigation_name) = LOWER(p_original_name)
      AND iml.feedback_status IS NOT NULL
    ORDER BY iml.created_at DESC
    LIMIT 1;
END;
$$;


ALTER FUNCTION "public"."get_investigation_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_medicine_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) RETURNS TABLE("matched_medicine_name" character varying, "correct_medicine_name" character varying, "feedback_status" character varying, "match_confidence" numeric)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        mml.matched_medicine_name,
        mml.correct_medicine_name,
        mml.feedback_status,
        mml.match_confidence
    FROM medicine_match_log mml
    WHERE mml.doctor_id = p_doctor_id
      AND LOWER(mml.original_medicine_name) = LOWER(p_original_name)
      AND mml.feedback_status IS NOT NULL
    ORDER BY mml.created_at DESC
    LIMIT 1;
END;
$$;


ALTER FUNCTION "public"."get_medicine_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_medicine_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) IS 'Check if doctor has previous feedback for a medicine name';



CREATE OR REPLACE FUNCTION "public"."get_merge_lineage"("p_merged_extraction_id" "uuid") RETURNS TABLE("source_extraction_id" "uuid", "consultation_type_code" character varying, "created_at" timestamp with time zone, "doctor_name" character varying, "merge_order" integer, "merge_strategy" character varying)
    LANGUAGE "plpgsql" STABLE
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        me.id AS source_extraction_id,
        ct.type_code AS consultation_type_code,
        me.created_at,
        d.name AS doctor_name,
        er.merge_order,
        er.merge_strategy
    FROM extraction_relationships er
    INNER JOIN medical_extractions me ON er.source_extraction_id = me.id
    INNER JOIN consultation_types ct ON me.consultation_type_id = ct.id
    LEFT JOIN doctors d ON me.doctor_id = d.id
    WHERE er.merged_extraction_id = p_merged_extraction_id
    ORDER BY er.merge_order ASC;
END;
$$;


ALTER FUNCTION "public"."get_merge_lineage"("p_merged_extraction_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_merge_lineage"("p_merged_extraction_id" "uuid") IS 'Returns all source extractions for a merged extraction, ordered chronologically';



CREATE OR REPLACE FUNCTION "public"."get_notes_per_doctor_per_day"("p_hospital_id" "uuid" DEFAULT NULL::"uuid", "p_doctor_id" "uuid" DEFAULT NULL::"uuid", "p_date_from" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_date_to" timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(row_data ORDER BY doctor_name, day), '[]'::jsonb) INTO result
    FROM (
        SELECT jsonb_build_object(
            'doctor_id', d.id,
            'doctor_name', d.full_name,
            'date', me.created_at::date,
            'note_count', COUNT(*)
        ) AS row_data, d.full_name AS doctor_name, me.created_at::date AS day
        FROM medical_extractions me
        JOIN doctors d ON d.id = me.doctor_id
        WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
          AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
          AND (p_date_from IS NULL OR me.created_at >= p_date_from)
          AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
        GROUP BY d.id, d.full_name, me.created_at::date
    ) sub;

    RETURN result;
END;
$$;


ALTER FUNCTION "public"."get_notes_per_doctor_per_day"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_patient_extraction_timeline"("p_patient_identifier" character varying) RETURNS TABLE("extraction_id" "uuid", "consultation_type_code" character varying, "consultation_type_name" character varying, "created_at" timestamp with time zone, "doctor_name" character varying, "is_merged" boolean, "source_count" integer, "segment_count" integer)
    LANGUAGE "plpgsql" STABLE
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        me.id AS extraction_id,
        ct.type_code AS consultation_type_code,
        ct.type_name AS consultation_type_name,
        me.created_at,
        d.full_name AS doctor_name,
        COALESCE(me.is_merged, FALSE) AS is_merged,
        COALESCE((me.merge_metadata->>'source_count')::INTEGER, 0) AS source_count,
        me.segment_count
    FROM medical_extractions me
    INNER JOIN consultation_types ct ON me.consultation_type_id = ct.id
    LEFT JOIN doctors d ON me.doctor_id = d.id
    LEFT JOIN recording_sessions rs ON me.session_id = rs.id
    LEFT JOIN patients p ON me.patient_id = p.id
    WHERE
        -- Match by recording_sessions.patient_identifier (primary - for regular extractions)
        rs.patient_identifier = p_patient_identifier
        -- OR match by patients.patient_id string field (fallback)
        OR p.patient_id = p_patient_identifier
        -- OR match merged extractions by patient_id UUID linking to patients table
        -- This catches merged extractions that have patient_id but no session_id
        OR me.patient_id IN (
            SELECT id FROM patients WHERE patient_id = p_patient_identifier
        )
    ORDER BY me.created_at DESC;
END;
$$;


ALTER FUNCTION "public"."get_patient_extraction_timeline"("p_patient_identifier" character varying) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_patient_extraction_timeline"("p_patient_identifier" character varying) IS 'Returns all extractions for a patient by external patient_identifier (e.g., PAT-001).
Matches via:
1. recording_sessions.patient_identifier (primary - regular extractions from recordings)
2. patients.patient_id string field (fallback)
3. medical_extractions.patient_id → patients.id lookup (for merged extractions without session_id)';



CREATE OR REPLACE FUNCTION "public"."get_patient_triage_context"("p_patient_id" "uuid") RETURNS "jsonb"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'allergies', (
            -- Get allergies from ALLERGIES and CAUTION segments
            SELECT COALESCE(jsonb_agg(DISTINCT es.segment_value_text), '[]'::jsonb)
            FROM extraction_segments es
            JOIN medical_extractions me ON es.extraction_id = me.id
            JOIN recording_sessions rs ON me.session_id = rs.id
            WHERE rs.patient_id = p_patient_id
              AND es.segment_code IN ('ALLERGIES', 'CAUTION')
              AND es.segment_value_text IS NOT NULL
              AND es.segment_value_text != ''
              AND LOWER(es.segment_value_text) NOT IN ('n/a', 'na', 'none', 'nil', 'no known allergies', 'nkda')
        ),
        'chronic_conditions', (
            -- Get chronic conditions from HISTORY segments (past_medical_history field)
            SELECT COALESCE(
                jsonb_agg(DISTINCT elem),
                '[]'::jsonb
            )
            FROM extraction_segments es
            JOIN medical_extractions me ON es.extraction_id = me.id
            JOIN recording_sessions rs ON me.session_id = rs.id
            CROSS JOIN LATERAL jsonb_array_elements_text(
                CASE
                    WHEN jsonb_typeof(es.segment_value->'past_medical_history') = 'array'
                    THEN es.segment_value->'past_medical_history'
                    ELSE '[]'::jsonb
                END
            ) AS elem
            WHERE rs.patient_id = p_patient_id
              AND es.segment_code = 'HISTORY'
              AND es.segment_value IS NOT NULL
              AND LOWER(elem) NOT IN ('n/a', 'na', 'none', 'nil')
        ),
        'intervention_outcomes', (
            -- Get prior intervention outcomes from patient_interventions table
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'code', pi.intervention_code,
                'name', idef.intervention_name,
                'status', pi.status,
                'outcome', pi.outcome,
                'category', idef.category
            ) ORDER BY pi.created_at DESC), '[]'::jsonb)
            FROM patient_interventions pi
            JOIN medical_extractions me ON pi.extraction_id = me.id
            JOIN recording_sessions rs ON me.session_id = rs.id
            LEFT JOIN intervention_definitions idef ON pi.intervention_id = idef.id
            WHERE rs.patient_id = p_patient_id
              AND pi.outcome IS NOT NULL
        ),
        'anxiety_pattern', (
            -- Get anxiety trend from ANXIETY_POST_CONSULTATION segments
            SELECT jsonb_build_object(
                'recent_level', (
                    SELECT es.segment_value_text
                    FROM extraction_segments es
                    JOIN medical_extractions me ON es.extraction_id = me.id
                    JOIN recording_sessions rs ON me.session_id = rs.id
                    WHERE rs.patient_id = p_patient_id
                      AND es.segment_code = 'ANXIETY_POST_CONSULTATION'
                      AND es.segment_value_text IS NOT NULL
                    ORDER BY me.created_at DESC
                    LIMIT 1
                ),
                'consultation_count', (
                    SELECT COUNT(*)
                    FROM extraction_segments es
                    JOIN medical_extractions me ON es.extraction_id = me.id
                    JOIN recording_sessions rs ON me.session_id = rs.id
                    WHERE rs.patient_id = p_patient_id
                      AND es.segment_code = 'ANXIETY_POST_CONSULTATION'
                ),
                'trend', (
                    SELECT CASE
                        WHEN COUNT(*) < 2 THEN 'unknown'
                        WHEN SUM(CASE
                            WHEN LOWER(es.segment_value_text) LIKE '%severe%' OR LOWER(es.segment_value_text) LIKE '%high%' THEN 3
                            WHEN LOWER(es.segment_value_text) LIKE '%moderate%' THEN 2
                            WHEN LOWER(es.segment_value_text) LIKE '%mild%' OR LOWER(es.segment_value_text) LIKE '%low%' THEN 1
                            ELSE 0
                        END) / NULLIF(COUNT(*), 0) > 2 THEN 'concerning'
                        ELSE 'stable_or_improving'
                    END
                    FROM extraction_segments es
                    JOIN medical_extractions me ON es.extraction_id = me.id
                    JOIN recording_sessions rs ON me.session_id = rs.id
                    WHERE rs.patient_id = p_patient_id
                      AND es.segment_code = 'ANXIETY_POST_CONSULTATION'
                )
            )
        ),
        'financial_concerns_trend', (
            -- Check if financial concerns are recurring from FINANCIAL_CONCERNS segment
            SELECT CASE
                WHEN COUNT(*) FILTER (
                    WHERE LOWER(fc) LIKE '%significant%'
                       OR LOWER(fc) LIKE '%moderate%'
                       OR LOWER(fc) LIKE '%yes%'
                       OR LOWER(fc) LIKE '%high%'
                ) >= 2 THEN 'recurring'
                WHEN COUNT(*) FILTER (
                    WHERE LOWER(fc) LIKE '%significant%'
                       OR LOWER(fc) LIKE '%moderate%'
                       OR LOWER(fc) LIKE '%yes%'
                       OR LOWER(fc) LIKE '%high%'
                ) = 1 THEN 'occasional'
                ELSE 'none_detected'
            END
            FROM (
                SELECT es.segment_value_text as fc
                FROM extraction_segments es
                JOIN medical_extractions me ON es.extraction_id = me.id
                JOIN recording_sessions rs ON me.session_id = rs.id
                WHERE rs.patient_id = p_patient_id
                  AND es.segment_code = 'FINANCIAL_CONCERNS'
                  AND es.segment_value_text IS NOT NULL
                ORDER BY me.created_at DESC
                LIMIT 5
            ) recent
        ),
        'compliance_likelihood', (
            -- Get latest compliance likelihood from TREATMENT_COMPLIANCE_LIKELIHOOD
            SELECT es.segment_value_text
            FROM extraction_segments es
            JOIN medical_extractions me ON es.extraction_id = me.id
            JOIN recording_sessions rs ON me.session_id = rs.id
            WHERE rs.patient_id = p_patient_id
              AND es.segment_code = 'TREATMENT_COMPLIANCE_LIKELIHOOD'
              AND es.segment_value_text IS NOT NULL
            ORDER BY me.created_at DESC
            LIMIT 1
        ),
        'other_emotions', (
            -- Get other emotions detected from OTHER_EMOTIONS_DETECTED
            SELECT COALESCE(jsonb_agg(DISTINCT es.segment_value_text), '[]'::jsonb)
            FROM extraction_segments es
            JOIN medical_extractions me ON es.extraction_id = me.id
            JOIN recording_sessions rs ON me.session_id = rs.id
            WHERE rs.patient_id = p_patient_id
              AND es.segment_code = 'OTHER_EMOTIONS_DETECTED'
              AND es.segment_value_text IS NOT NULL
              AND LOWER(es.segment_value_text) NOT IN ('n/a', 'na', 'none', 'nil')
        ),
        'total_consultations', (
            -- Count total consultations for this patient
            SELECT COUNT(DISTINCT me.id)
            FROM medical_extractions me
            JOIN recording_sessions rs ON me.session_id = rs.id
            WHERE rs.patient_id = p_patient_id
        )
    ) INTO v_result;

    RETURN v_result;
END;
$$;


ALTER FUNCTION "public"."get_patient_triage_context"("p_patient_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_patient_triage_context"("p_patient_id" "uuid") IS 'Aggregates patient context from historical extractions for triage engine - includes allergies, chronic conditions, intervention outcomes, anxiety patterns, financial concerns, and compliance history';



CREATE OR REPLACE FUNCTION "public"."get_peer_comparison"("p_doctor_id" "uuid") RETURNS TABLE("metric" "text", "doctor_value" numeric, "peer_avg" numeric, "peer_p25" numeric, "peer_p75" numeric, "is_outlier" boolean, "outlier_direction" "text")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_hospital_id UUID;
    v_specialty TEXT;
    v_doctor_style doctor_practice_styles%ROWTYPE;
    v_hospital_patterns hospital_specialty_patterns%ROWTYPE;
BEGIN
    -- Get doctor's hospital and specialty
    SELECT d.hospital_id, d.specialization INTO v_hospital_id, v_specialty
    FROM doctors d
    WHERE d.id = p_doctor_id;

    IF v_hospital_id IS NULL OR v_specialty IS NULL THEN
        RETURN;
    END IF;

    -- Get doctor's practice style
    SELECT * INTO v_doctor_style
    FROM doctor_practice_styles
    WHERE doctor_id = p_doctor_id;

    -- Get hospital patterns for this specialty
    SELECT * INTO v_hospital_patterns
    FROM hospital_specialty_patterns
    WHERE hospital_id = v_hospital_id AND specialty = v_specialty;

    IF v_hospital_patterns IS NULL THEN
        -- Try to compute patterns
        v_hospital_patterns := compute_hospital_specialty_patterns(v_hospital_id, v_specialty);
    END IF;

    IF v_hospital_patterns IS NULL THEN
        RETURN;
    END IF;

    -- Return comparison metrics
    -- 1. Investigations per extraction
    metric := 'investigations_per_extraction';
    doctor_value := COALESCE(v_doctor_style.avg_investigations_per_extraction, 0);
    peer_avg := COALESCE(v_hospital_patterns.avg_suggestions_per_extraction, 0);
    peer_p25 := peer_avg * 0.7;  -- Approximation
    peer_p75 := peer_avg * 1.3;  -- Approximation
    is_outlier := (doctor_value < peer_p25 OR doctor_value > peer_p75);
    outlier_direction := CASE
        WHEN doctor_value < peer_p25 THEN 'below'
        WHEN doctor_value > peer_p75 THEN 'above'
        ELSE NULL
    END;
    RETURN NEXT;

    -- 2. Acceptance rate
    metric := 'acceptance_rate';
    doctor_value := COALESCE(v_doctor_style.acceptance_rate, 0);
    peer_avg := COALESCE(v_hospital_patterns.avg_acceptance_rate, 0);
    peer_p25 := GREATEST(peer_avg - 15, 0);
    peer_p75 := LEAST(peer_avg + 15, 100);
    is_outlier := (doctor_value < peer_p25 OR doctor_value > peer_p75);
    outlier_direction := CASE
        WHEN doctor_value < peer_p25 THEN 'below'
        WHEN doctor_value > peer_p75 THEN 'above'
        ELSE NULL
    END;
    RETURN NEXT;

    -- 3. Feedback engagement
    metric := 'feedback_engagement';
    doctor_value := COALESCE(v_doctor_style.total_feedback_entries, 0);
    peer_avg := CASE WHEN v_hospital_patterns.doctor_count > 0
        THEN v_hospital_patterns.total_feedback::NUMERIC / v_hospital_patterns.doctor_count
        ELSE 0 END;
    peer_p25 := peer_avg * 0.5;
    peer_p75 := peer_avg * 1.5;
    is_outlier := (doctor_value < peer_p25);
    outlier_direction := CASE WHEN doctor_value < peer_p25 THEN 'below' ELSE NULL END;
    RETURN NEXT;

    RETURN;
END;
$$;


ALTER FUNCTION "public"."get_peer_comparison"("p_doctor_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_peer_comparison"("p_doctor_id" "uuid") IS 'Returns peer comparison metrics for a doctor against same-specialty colleagues';



CREATE OR REPLACE FUNCTION "public"."get_pending_feedback_count_rpc"("p_doctor_id" "uuid") RETURNS integer
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM medicine_match_log
    WHERE doctor_id = p_doctor_id
      AND feedback_status IS NULL;

    RETURN v_count;
END;
$$;


ALTER FUNCTION "public"."get_pending_feedback_count_rpc"("p_doctor_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_pending_investigation_feedback_count_rpc"("p_doctor_id" "uuid") RETURNS integer
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM investigation_match_log
    WHERE doctor_id = p_doctor_id
      AND feedback_status IS NULL;

    RETURN v_count;
END;
$$;


ALTER FUNCTION "public"."get_pending_investigation_feedback_count_rpc"("p_doctor_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_processing_mode_config"("p_mode_code" character varying) RETURNS TABLE("mode_code" character varying, "mode_name" character varying, "transcription_model" character varying, "extraction_model" character varying, "transcription_api" character varying, "estimated_time_seconds" integer)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        pm.mode_code,
        pm.mode_name,
        pm.transcription_model,
        pm.extraction_model,
        pm.transcription_api,
        pm.estimated_time_seconds
    FROM processing_modes pm
    WHERE pm.mode_code = p_mode_code
      AND pm.is_active = TRUE
    LIMIT 1;
END;
$$;


ALTER FUNCTION "public"."get_processing_mode_config"("p_mode_code" character varying) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_processing_mode_config"("p_mode_code" character varying) IS 'Fetches processing mode configuration including model names and estimated processing time. Returns single row or empty if mode_code not found.';



CREATE OR REPLACE FUNCTION "public"."get_red_flags_by_specialty"("p_specialty" "text", "p_include_emergency_triggers" boolean DEFAULT true) RETURNS TABLE("condition_name" "text", "condition_code" "text", "chunk_type" "text", "content_json" "jsonb", "urgency_default" "text")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.name,
        cc.condition_id,
        ch.chunk_type,
        ch.content_json,
        ch.urgency_default
    FROM clinical_chunks ch
    JOIN clinical_conditions cc ON ch.condition_id = cc.id
    WHERE cc.is_active = TRUE
    AND cc.specialty = p_specialty
    AND (
        ch.has_red_flags = TRUE
        OR (p_include_emergency_triggers AND ch.has_emergency_triggers = TRUE)
    )
    ORDER BY cc.name, ch.chunk_type;
END;
$$;


ALTER FUNCTION "public"."get_red_flags_by_specialty"("p_specialty" "text", "p_include_emergency_triggers" boolean) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_red_flags_by_specialty"("p_specialty" "text", "p_include_emergency_triggers" boolean) IS 'Get all red flags and emergency triggers for a specialty';



CREATE OR REPLACE FUNCTION "public"."get_session_with_job"("p_correlation_id" "uuid") RETURNS TABLE("session_id" "uuid", "correlation_id" "uuid", "status" character varying, "doctor_name" character varying, "patient_identifier" character varying, "total_chunks" integer, "chunks_deleted" boolean, "job_id" "uuid", "submission_id" "uuid", "job_status" character varying, "progress_percentage" integer, "transcript" "text", "insights" "jsonb")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        rs.id,
        rs.correlation_id,
        rs.status,
        rs.doctor_name,
        rs.patient_identifier,
        rs.total_chunks,
        rs.chunks_deleted,
        pj.id,
        pj.submission_id,
        pj.status,
        pj.progress_percentage,
        pj.transcript,
        pj.insights
    FROM recording_sessions rs
    LEFT JOIN processing_jobs pj ON pj.session_id = rs.id
    WHERE rs.correlation_id = p_correlation_id;
END;
$$;


ALTER FUNCTION "public"."get_session_with_job"("p_correlation_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_template_by_code_unified"("p_doctor_id" "uuid", "p_template_code" "text") RETURNS TABLE("id" "uuid", "template_code" character varying, "template_name" character varying, "description" "text", "use_case" character varying, "is_default" boolean, "is_active" boolean, "estimated_extraction_time_seconds" numeric, "created_at" timestamp with time zone, "updated_at" timestamp with time zone, "consultation_type_id" "uuid", "specialization" character varying, "hospital_id" "uuid", "doctor_id" "uuid", "assembled_full_prompt" "text", "prompt_assembled_at" timestamp with time zone, "prompt_trigger_source" "text", "system_prompt_config_id" "uuid", "assembled_schema_json" "jsonb", "schema_assembled_at" timestamp with time zone, "schema_trigger_source" "text", "prompt_assembly_hash" character varying, "schema_assembly_hash" character varying, "source_priority" integer)
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
    SELECT
        t.id,
        t.template_code,
        t.template_name,
        t.description,
        t.use_case,
        t.is_default,
        t.is_active,
        t.estimated_extraction_time_seconds,
        t.created_at,
        t.updated_at,
        t.consultation_type_id,
        t.specialization,
        t.hospital_id,
        t.doctor_id,
        t.assembled_full_prompt,
        t.prompt_assembled_at,
        t.prompt_trigger_source,
        t.system_prompt_config_id,
        t.assembled_schema_json,
        t.schema_assembled_at,
        t.schema_trigger_source,
        t.prompt_assembly_hash,
        t.schema_assembly_hash,
        combined.priority as source_priority
    FROM (
        -- Priority 1: Doctor-owned templates (highest priority)
        SELECT t.id, 1 as priority
        FROM templates t
        WHERE t.doctor_id = p_doctor_id
          AND t.template_code = p_template_code
          AND t.is_active = true

        UNION ALL

        -- Priority 2: Shared templates via doctor_templates junction
        SELECT t.id, 2 as priority
        FROM templates t
        INNER JOIN doctor_templates dt ON t.id = dt.template_id
        WHERE dt.doctor_id = p_doctor_id
          AND t.template_code = p_template_code
          AND dt.is_active = true
          AND t.is_active = true

        UNION ALL

        -- Priority 3: Global templates (doctor_id IS NULL)
        SELECT t.id, 3 as priority
        FROM templates t
        WHERE t.doctor_id IS NULL
          AND t.template_code = p_template_code
          AND t.is_active = true
    ) combined
    INNER JOIN templates t ON combined.id = t.id
    ORDER BY combined.priority
    LIMIT 1;
$$;


ALTER FUNCTION "public"."get_template_by_code_unified"("p_doctor_id" "uuid", "p_template_code" "text") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_template_by_code_unified"("p_doctor_id" "uuid", "p_template_code" "text") IS 'Unified template lookup: owned -> shared -> global. Replaces 3 queries with 1 UNION.';



CREATE OR REPLACE FUNCTION "public"."get_template_performance_stats"("p_template_code" character varying) RETURNS TABLE("avg_processing_time" numeric, "avg_extraction_time" numeric, "avg_total_time" numeric, "success_rate" numeric, "total_uses" bigint)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        AVG(tpm.processing_time_seconds),
        AVG(tpm.extraction_time_seconds),
        AVG(tpm.total_time_seconds),
        (COUNT(*) FILTER (WHERE tpm.insights_extracted = TRUE)::DECIMAL / NULLIF(COUNT(*), 0)) * 100 AS success_rate,
        COUNT(*) AS total_uses
    FROM template_performance_metrics tpm
    JOIN prompt_templates pt ON pt.id = tpm.template_id
    WHERE pt.template_code = p_template_code;
END;
$$;


ALTER FUNCTION "public"."get_template_performance_stats"("p_template_code" character varying) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_usage_summary"("p_group_by" "text" DEFAULT 'doctor'::"text", "p_date_from" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_date_to" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_api_client_id" "uuid" DEFAULT NULL::"uuid", "p_hospital_id" "uuid" DEFAULT NULL::"uuid", "p_doctor_id" "uuid" DEFAULT NULL::"uuid", "p_limit" integer DEFAULT 100, "p_offset" integer DEFAULT 0) RETURNS TABLE("group_id" "uuid", "group_name" "text", "group_type" "text", "hospital_id" "uuid", "hospital_name" "text", "total_api_calls" bigint, "total_sessions" bigint, "total_cost_usd" numeric, "total_cache_savings_usd" numeric, "total_input_tokens" bigint, "total_output_tokens" bigint, "total_cached_tokens" bigint, "total_recording_hours" numeric, "total_transcription_hours" numeric, "avg_cache_hit_ratio" numeric, "error_count" bigint, "first_usage_at" timestamp with time zone, "last_usage_at" timestamp with time zone)
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    IF p_group_by = 'api_client' THEN
        RETURN QUERY
        SELECT
            ac.id AS group_id,
            ac.client_name::TEXT AS group_name,
            ac.client_type::TEXT AS group_type,
            ac.hospital_id,
            h.hospital_name::TEXT,
            COUNT(DISTINCT l.id)::BIGINT AS total_api_calls,
            COUNT(DISTINCT l.session_id)::BIGINT AS total_sessions,
            COALESCE(SUM(l.total_cost_usd), 0)::NUMERIC AS total_cost_usd,
            COALESCE(SUM(l.cache_savings_usd), 0)::NUMERIC AS total_cache_savings_usd,
            COALESCE(SUM(l.prompt_token_count), 0)::BIGINT AS total_input_tokens,
            COALESCE(SUM(l.candidates_token_count), 0)::BIGINT AS total_output_tokens,
            COALESCE(SUM(l.cached_content_token_count), 0)::BIGINT AS total_cached_tokens,
            COALESCE(
                (SELECT SUM(rs.total_duration_seconds) / 3600.0
                 FROM recording_sessions rs
                 WHERE rs.id IN (
                     SELECT DISTINCT ll.session_id FROM llm_usage_log ll
                     WHERE ll.api_client_id = ac.id
                     AND (p_date_from IS NULL OR ll.created_at >= p_date_from)
                     AND (p_date_to IS NULL OR ll.created_at < p_date_to)
                 )
                ), 0
            )::NUMERIC AS total_recording_hours,
            COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0)::NUMERIC AS total_transcription_hours,
            AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END)::NUMERIC AS avg_cache_hit_ratio,
            COUNT(CASE WHEN l.response_status = 'error' THEN 1 END)::BIGINT AS error_count,
            MIN(l.created_at) AS first_usage_at,
            MAX(l.created_at) AS last_usage_at
        FROM api_clients ac
        LEFT JOIN llm_usage_log l ON l.api_client_id = ac.id
            AND (p_date_from IS NULL OR l.created_at >= p_date_from)
            AND (p_date_to IS NULL OR l.created_at < p_date_to)
        LEFT JOIN hospitals h ON ac.hospital_id = h.id
        WHERE (p_api_client_id IS NULL OR ac.id = p_api_client_id)
          AND (p_hospital_id IS NULL OR ac.hospital_id = p_hospital_id)
        GROUP BY ac.id, ac.client_name, ac.client_type, ac.hospital_id, h.hospital_name
        ORDER BY COALESCE(SUM(l.total_cost_usd), 0) DESC
        LIMIT p_limit OFFSET p_offset;

    ELSIF p_group_by = 'hospital' THEN
        RETURN QUERY
        SELECT
            h.id AS group_id,
            h.hospital_name::TEXT AS group_name,
            'hospital'::TEXT AS group_type,
            h.id AS hospital_id,
            h.hospital_name::TEXT,
            COUNT(DISTINCT l.id)::BIGINT AS total_api_calls,
            COUNT(DISTINCT l.session_id)::BIGINT AS total_sessions,
            COALESCE(SUM(l.total_cost_usd), 0)::NUMERIC AS total_cost_usd,
            COALESCE(SUM(l.cache_savings_usd), 0)::NUMERIC AS total_cache_savings_usd,
            COALESCE(SUM(l.prompt_token_count), 0)::BIGINT AS total_input_tokens,
            COALESCE(SUM(l.candidates_token_count), 0)::BIGINT AS total_output_tokens,
            COALESCE(SUM(l.cached_content_token_count), 0)::BIGINT AS total_cached_tokens,
            COALESCE(
                (SELECT SUM(rs.total_duration_seconds) / 3600.0
                 FROM recording_sessions rs
                 INNER JOIN doctors dd ON rs.doctor_id = dd.id
                 WHERE dd.hospital_id = h.id
                 AND (p_date_from IS NULL OR rs.created_at >= p_date_from)
                 AND (p_date_to IS NULL OR rs.created_at < p_date_to)
                ), 0
            )::NUMERIC AS total_recording_hours,
            COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0)::NUMERIC AS total_transcription_hours,
            AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END)::NUMERIC AS avg_cache_hit_ratio,
            COUNT(CASE WHEN l.response_status = 'error' THEN 1 END)::BIGINT AS error_count,
            MIN(l.created_at) AS first_usage_at,
            MAX(l.created_at) AS last_usage_at
        FROM hospitals h
        LEFT JOIN doctors d ON d.hospital_id = h.id
        LEFT JOIN llm_usage_log l ON l.doctor_id = d.id
            AND (p_date_from IS NULL OR l.created_at >= p_date_from)
            AND (p_date_to IS NULL OR l.created_at < p_date_to)
        WHERE (p_hospital_id IS NULL OR h.id = p_hospital_id)
        GROUP BY h.id, h.hospital_name
        ORDER BY COALESCE(SUM(l.total_cost_usd), 0) DESC
        LIMIT p_limit OFFSET p_offset;

    ELSE  -- Default: doctor
        RETURN QUERY
        SELECT
            d.id AS group_id,
            d.full_name::TEXT AS group_name,
            COALESCE(d.specialization, 'General')::TEXT AS group_type,
            d.hospital_id,
            h.hospital_name::TEXT,
            COUNT(DISTINCT l.id)::BIGINT AS total_api_calls,
            COUNT(DISTINCT l.session_id)::BIGINT AS total_sessions,
            COALESCE(SUM(l.total_cost_usd), 0)::NUMERIC AS total_cost_usd,
            COALESCE(SUM(l.cache_savings_usd), 0)::NUMERIC AS total_cache_savings_usd,
            COALESCE(SUM(l.prompt_token_count), 0)::BIGINT AS total_input_tokens,
            COALESCE(SUM(l.candidates_token_count), 0)::BIGINT AS total_output_tokens,
            COALESCE(SUM(l.cached_content_token_count), 0)::BIGINT AS total_cached_tokens,
            COALESCE(
                (SELECT SUM(rs.total_duration_seconds) / 3600.0
                 FROM recording_sessions rs
                 WHERE rs.doctor_id = d.id
                 AND (p_date_from IS NULL OR rs.created_at >= p_date_from)
                 AND (p_date_to IS NULL OR rs.created_at < p_date_to)
                ), 0
            )::NUMERIC AS total_recording_hours,
            COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0)::NUMERIC AS total_transcription_hours,
            AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END)::NUMERIC AS avg_cache_hit_ratio,
            COUNT(CASE WHEN l.response_status = 'error' THEN 1 END)::BIGINT AS error_count,
            MIN(l.created_at) AS first_usage_at,
            MAX(l.created_at) AS last_usage_at
        FROM doctors d
        LEFT JOIN llm_usage_log l ON l.doctor_id = d.id
            AND (p_date_from IS NULL OR l.created_at >= p_date_from)
            AND (p_date_to IS NULL OR l.created_at < p_date_to)
        LEFT JOIN hospitals h ON d.hospital_id = h.id
        WHERE (p_doctor_id IS NULL OR d.id = p_doctor_id)
          AND (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
        GROUP BY d.id, d.full_name, d.specialization, d.hospital_id, h.hospital_name
        ORDER BY COALESCE(SUM(l.total_cost_usd), 0) DESC
        LIMIT p_limit OFFSET p_offset;
    END IF;
END;
$$;


ALTER FUNCTION "public"."get_usage_summary"("p_group_by" "text", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_api_client_id" "uuid", "p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_usage_totals"("p_date_from" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_date_to" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_api_client_id" "uuid" DEFAULT NULL::"uuid", "p_hospital_id" "uuid" DEFAULT NULL::"uuid", "p_doctor_id" "uuid" DEFAULT NULL::"uuid") RETURNS TABLE("total_api_calls" bigint, "total_sessions" bigint, "total_cost_usd" numeric, "total_cache_savings_usd" numeric, "total_input_tokens" bigint, "total_output_tokens" bigint, "total_recording_hours" numeric, "unique_doctors" bigint, "unique_hospitals" bigint, "unique_api_clients" bigint)
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT l.id)::BIGINT AS total_api_calls,
        COUNT(DISTINCT l.session_id)::BIGINT AS total_sessions,
        COALESCE(SUM(l.total_cost_usd), 0)::NUMERIC AS total_cost_usd,
        COALESCE(SUM(l.cache_savings_usd), 0)::NUMERIC AS total_cache_savings_usd,
        COALESCE(SUM(l.prompt_token_count), 0)::BIGINT AS total_input_tokens,
        COALESCE(SUM(l.candidates_token_count), 0)::BIGINT AS total_output_tokens,
        COALESCE(
            (SELECT SUM(rs.total_duration_seconds) / 3600.0
             FROM recording_sessions rs
             WHERE rs.id IN (
                 SELECT DISTINCT ll.session_id FROM llm_usage_log ll
                 WHERE (p_date_from IS NULL OR ll.created_at >= p_date_from)
                 AND (p_date_to IS NULL OR ll.created_at < p_date_to)
                 AND (p_api_client_id IS NULL OR ll.api_client_id = p_api_client_id)
                 AND (p_doctor_id IS NULL OR ll.doctor_id = p_doctor_id)
             )
            ), 0
        )::NUMERIC AS total_recording_hours,
        COUNT(DISTINCT l.doctor_id)::BIGINT AS unique_doctors,
        COUNT(DISTINCT d.hospital_id)::BIGINT AS unique_hospitals,
        COUNT(DISTINCT l.api_client_id)::BIGINT AS unique_api_clients
    FROM llm_usage_log l
    LEFT JOIN doctors d ON l.doctor_id = d.id
    WHERE (p_date_from IS NULL OR l.created_at >= p_date_from)
      AND (p_date_to IS NULL OR l.created_at < p_date_to)
      AND (p_api_client_id IS NULL OR l.api_client_id = p_api_client_id)
      AND (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
      AND (p_doctor_id IS NULL OR l.doctor_id = p_doctor_id);
END;
$$;


ALTER FUNCTION "public"."get_usage_totals"("p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_api_client_id" "uuid", "p_hospital_id" "uuid", "p_doctor_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."mark_missed_followups"() RETURNS integer
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE followup_tracking
    SET
        status = 'MISSED',
        updated_at = NOW()
    WHERE status = 'PENDING'
      AND followup_window_end IS NOT NULL
      AND followup_window_end < CURRENT_DATE;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$;


ALTER FUNCTION "public"."mark_missed_followups"() OWNER TO "postgres";


COMMENT ON FUNCTION "public"."mark_missed_followups"() IS 'Call this function daily to automatically mark PENDING follow-ups as MISSED when their window has passed';



CREATE OR REPLACE FUNCTION "public"."match_clinical_guidelines"("query_embedding" "extensions"."vector", "match_specialty" "text" DEFAULT NULL::"text", "match_topics" "text"[] DEFAULT NULL::"text"[], "match_count" integer DEFAULT 5, "similarity_threshold" double precision DEFAULT 0.5) RETURNS TABLE("id" "uuid", "source_name" "text", "source_organization" "text", "document_title" "text", "chunk_text" "text", "topics" "text"[], "presentations" "text"[], "evidence_level" "text", "publication_year" integer, "similarity" double precision)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'extensions', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        g.id,
        g.source_name,
        g.source_organization,
        g.document_title,
        g.chunk_text,
        g.topics,
        g.presentations,
        g.evidence_level,
        g.publication_year,
        1 - (ge.embedding <=> query_embedding) as similarity
    FROM clinical_guidelines g
    JOIN clinical_guideline_embeddings ge ON g.id = ge.guideline_id
    WHERE g.is_active = TRUE
    -- Optional specialty filter
    AND (match_specialty IS NULL OR g.specialty = match_specialty)
    -- Optional topics filter (match any topic)
    AND (match_topics IS NULL OR g.topics && match_topics)
    -- Similarity threshold
    AND (1 - (ge.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY ge.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."match_clinical_guidelines"("query_embedding" "extensions"."vector", "match_specialty" "text", "match_topics" "text"[], "match_count" integer, "similarity_threshold" double precision) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."match_clinical_guidelines"("query_embedding" "extensions"."vector", "match_specialty" "text", "match_topics" "text"[], "match_count" integer, "similarity_threshold" double precision) IS 'Semantic search for clinical guidelines using cosine similarity';



CREATE OR REPLACE FUNCTION "public"."notify_emotion_prompt_change"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_segment_code TEXT;
    v_is_combined BOOLEAN := false;
BEGIN
    -- Get the segment code (handle DELETE case)
    IF TG_OP = 'DELETE' THEN
        v_segment_code := OLD.segment_code;
    ELSE
        v_segment_code := NEW.segment_code;
    END IF;

    -- Only act on COMBINED_* segments or base prompt component
    IF v_segment_code LIKE 'COMBINED_%' OR v_segment_code = 'COMBINED_EMOTION_BASE_PROMPT' THEN
        v_is_combined := true;
    END IF;

    IF NOT v_is_combined THEN
        -- Not a combined emotion segment, do nothing
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;

    -- Clear assembled prompts cache to force reassembly
    UPDATE templates
    SET assembled_combined_emotion_prompt = NULL,
        assembled_combined_emotion_schema_json = NULL
    WHERE id IN (
        SELECT DISTINCT t.id
        FROM templates t
        JOIN consultation_types ct ON t.consultation_type_id = ct.id
        WHERE ct.enable_emotion_analysis = true
    );

    -- Notify application of prompt change (for cache invalidation)
    PERFORM pg_notify('emotion_prompt_changed', json_build_object(
        'segment_code', v_segment_code,
        'changed_at', NOW()
    )::text);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$;


ALTER FUNCTION "public"."notify_emotion_prompt_change"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."prevent_audit_log_deletion"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RAISE EXCEPTION 'HIPAA compliance: Audit log records cannot be deleted';
END;
$$;


ALTER FUNCTION "public"."prevent_audit_log_deletion"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."record_template_performance"("p_template_id" "uuid", "p_session_id" "uuid", "p_transcription_model" character varying, "p_audio_duration" numeric, "p_processing_time" numeric, "p_extraction_time" numeric, "p_total_time" numeric, "p_transcript_length" integer, "p_insights_extracted" boolean) RETURNS "void"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    INSERT INTO template_performance_metrics (
        template_id,
        session_id,
        transcription_model,
        audio_duration_seconds,
        processing_time_seconds,
        extraction_time_seconds,
        total_time_seconds,
        transcript_length,
        insights_extracted
    ) VALUES (
        p_template_id,
        p_session_id,
        p_transcription_model,
        p_audio_duration,
        p_processing_time,
        p_extraction_time,
        p_total_time,
        p_transcript_length,
        p_insights_extracted
    );
END;
$$;


ALTER FUNCTION "public"."record_template_performance"("p_template_id" "uuid", "p_session_id" "uuid", "p_transcription_model" character varying, "p_audio_duration" numeric, "p_processing_time" numeric, "p_extraction_time" numeric, "p_total_time" numeric, "p_transcript_length" integer, "p_insights_extracted" boolean) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."save_patient_interventions"("p_extraction_id" "uuid", "p_interventions" "jsonb") RETURNS "jsonb"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_intervention JSONB;
    v_intervention_def_id UUID;
    v_rank INTEGER := 0;
    v_saved_count INTEGER := 0;
    v_result JSONB;
BEGIN
    DELETE FROM patient_interventions WHERE extraction_id = p_extraction_id;

    FOR v_intervention IN SELECT * FROM jsonb_array_elements(p_interventions)
    LOOP
        v_rank := v_rank + 1;

        SELECT id INTO v_intervention_def_id
        FROM intervention_definitions
        WHERE intervention_code = v_intervention->>'code';

        INSERT INTO patient_interventions (
            extraction_id, intervention_id, intervention_code, priority_level,
            priority_score, trigger_reason, analysis_mode, recommendation_rank,
            is_top_recommendation, rationale_sources
        ) VALUES (
            p_extraction_id, v_intervention_def_id, v_intervention->>'code',
            v_intervention->>'priority', (v_intervention->>'priority_score')::INTEGER,
            v_intervention->>'trigger_reason',
            COALESCE(v_intervention->>'analysis_mode', 'text_only'),
            CASE WHEN v_rank <= 3 THEN v_rank ELSE NULL END,
            v_rank <= 3,
            COALESCE(v_intervention->'rationale_sources', '[]'::JSONB)
        );

        v_saved_count := v_saved_count + 1;
    END LOOP;

    v_result := jsonb_build_object(
        'success', TRUE,
        'extraction_id', p_extraction_id,
        'interventions_saved', v_saved_count,
        'top_3_count', LEAST(v_saved_count, 3)
    );

    RETURN v_result;
END;
$$;


ALTER FUNCTION "public"."save_patient_interventions"("p_extraction_id" "uuid", "p_interventions" "jsonb") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."save_triage_suggestions"("p_extraction_id" "uuid", "p_doctor_id" "uuid", "p_suggestions" "jsonb", "p_patient_context" "jsonb" DEFAULT '{}'::"jsonb") RETURNS "jsonb"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_suggestion JSONB;
    v_rank INTEGER := 0;
    v_saved_count INTEGER := 0;
    v_result JSONB;
BEGIN
    -- Delete existing suggestions for this extraction (in case of regeneration)
    DELETE FROM triage_suggestion_log WHERE extraction_id = p_extraction_id;

    -- Insert each suggestion
    FOR v_suggestion IN SELECT * FROM jsonb_array_elements(p_suggestions)
    LOOP
        v_rank := v_rank + 1;

        INSERT INTO triage_suggestion_log (
            extraction_id, doctor_id, suggestion_category, suggestion_type,
            suggestion_text, source_layer, confidence_score, priority_rank,
            patient_context_applied
        ) VALUES (
            p_extraction_id,
            p_doctor_id,
            COALESCE(v_suggestion->>'category', 'investigation'),
            COALESCE(v_suggestion->>'type', 'missing_investigation'),
            v_suggestion->>'suggestion',
            COALESCE(v_suggestion->>'source', 'gemini_synthesis'),
            (v_suggestion->>'confidence')::NUMERIC,
            v_rank,
            p_patient_context
        );

        v_saved_count := v_saved_count + 1;
    END LOOP;

    v_result := jsonb_build_object(
        'success', TRUE,
        'extraction_id', p_extraction_id,
        'suggestions_saved', v_saved_count
    );

    RETURN v_result;
END;
$$;


ALTER FUNCTION "public"."save_triage_suggestions"("p_extraction_id" "uuid", "p_doctor_id" "uuid", "p_suggestions" "jsonb", "p_patient_context" "jsonb") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."save_triage_suggestions"("p_extraction_id" "uuid", "p_doctor_id" "uuid", "p_suggestions" "jsonb", "p_patient_context" "jsonb") IS 'Batch insert triage suggestions for an extraction with patient context snapshot';



CREATE OR REPLACE FUNCTION "public"."search_by_icd_code"("p_icd_code" "text") RETURNS TABLE("condition_id" "uuid", "condition_code" "text", "condition_name" "text", "specialty" "text", "icd_codes" "text"[], "triage_metadata" "jsonb")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.id,
        cc.condition_id,
        cc.name,
        cc.specialty,
        cc.icd_codes,
        cc.triage_metadata
    FROM clinical_conditions cc
    WHERE cc.is_active = TRUE
    AND p_icd_code = ANY(cc.icd_codes);
END;
$$;


ALTER FUNCTION "public"."search_by_icd_code"("p_icd_code" "text") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."search_by_icd_code"("p_icd_code" "text") IS 'Find conditions by ICD-10 code';



CREATE OR REPLACE FUNCTION "public"."search_clinical_chunks_hybrid"("query_embedding" "extensions"."vector", "query_text" "text" DEFAULT NULL::"text", "filter_specialty" "text" DEFAULT NULL::"text", "filter_chunk_types" "text"[] DEFAULT NULL::"text"[], "filter_urgency" "text" DEFAULT NULL::"text", "filter_comorbidity" "text" DEFAULT NULL::"text", "filter_care_level" "text" DEFAULT NULL::"text", "filter_drug_class" "text" DEFAULT NULL::"text", "patient_sbp" integer DEFAULT NULL::integer, "patient_dbp" integer DEFAULT NULL::integer, "patient_hb" numeric DEFAULT NULL::numeric, "match_count" integer DEFAULT 10, "min_similarity" double precision DEFAULT 0.4) RETURNS TABLE("chunk_id" "uuid", "condition_id" "uuid", "condition_name" "text", "condition_code" "text", "specialty" "text", "chunk_type" "text", "content_json" "jsonb", "content_text" "text", "urgency_default" "text", "care_levels" "text"[], "comorbidity" "text", "numeric_thresholds" "jsonb", "similarity" double precision, "threshold_match" boolean, "match_source" "text")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'extensions', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    WITH semantic_matches AS (
        SELECT
            ch.id AS chunk_id,
            cc.id AS condition_id,
            cc.name AS condition_name,
            cc.condition_id AS condition_code,
            cc.specialty,
            ch.chunk_type,
            ch.content_json,
            ch.content_text,
            ch.urgency_default,
            ch.care_levels,
            ch.comorbidity,
            ch.numeric_thresholds,
            1 - (ce.embedding <=> query_embedding) AS similarity,
            -- Check numeric threshold match
            CASE
                WHEN patient_sbp IS NOT NULL AND ch.numeric_thresholds ? 'sbp_min'
                     AND patient_sbp >= (ch.numeric_thresholds->>'sbp_min')::INT THEN TRUE
                WHEN patient_dbp IS NOT NULL AND ch.numeric_thresholds ? 'dbp_min'
                     AND patient_dbp >= (ch.numeric_thresholds->>'dbp_min')::INT THEN TRUE
                WHEN patient_hb IS NOT NULL AND ch.numeric_thresholds ? 'hb_max'
                     AND patient_hb <= (ch.numeric_thresholds->>'hb_max')::NUMERIC THEN TRUE
                ELSE FALSE
            END AS threshold_match,
            'semantic'::TEXT AS match_source
        FROM clinical_chunks ch
        JOIN clinical_conditions cc ON ch.condition_id = cc.id
        JOIN clinical_chunk_embeddings ce ON ch.id = ce.chunk_id
        WHERE cc.is_active = TRUE
        -- Apply filters
        AND (filter_specialty IS NULL OR cc.specialty = filter_specialty)
        AND (filter_chunk_types IS NULL OR ch.chunk_type = ANY(filter_chunk_types))
        AND (filter_urgency IS NULL OR ch.urgency_default = filter_urgency)
        AND (filter_comorbidity IS NULL OR ch.comorbidity = filter_comorbidity)
        AND (filter_care_level IS NULL OR filter_care_level = ANY(ch.care_levels))
        AND (filter_drug_class IS NULL OR filter_drug_class = ANY(ch.drug_classes))
        -- Similarity threshold
        AND (1 - (ce.embedding <=> query_embedding)) >= min_similarity
        ORDER BY ce.embedding <=> query_embedding
        LIMIT match_count
    ),
    -- Add threshold-triggered results (even if semantic similarity is low)
    threshold_matches AS (
        SELECT
            ch.id AS chunk_id,
            cc.id AS condition_id,
            cc.name AS condition_name,
            cc.condition_id AS condition_code,
            cc.specialty,
            ch.chunk_type,
            ch.content_json,
            ch.content_text,
            ch.urgency_default,
            ch.care_levels,
            ch.comorbidity,
            ch.numeric_thresholds,
            0.3::FLOAT AS similarity,
            TRUE AS threshold_match,
            'threshold'::TEXT AS match_source
        FROM clinical_chunks ch
        JOIN clinical_conditions cc ON ch.condition_id = cc.id
        WHERE cc.is_active = TRUE
        AND ch.numeric_thresholds IS NOT NULL
        AND (filter_specialty IS NULL OR cc.specialty = filter_specialty)
        AND (
            (patient_sbp IS NOT NULL AND ch.numeric_thresholds ? 'sbp_min'
             AND patient_sbp >= (ch.numeric_thresholds->>'sbp_min')::INT)
            OR
            (patient_dbp IS NOT NULL AND ch.numeric_thresholds ? 'dbp_min'
             AND patient_dbp >= (ch.numeric_thresholds->>'dbp_min')::INT)
            OR
            (patient_hb IS NOT NULL AND ch.numeric_thresholds ? 'hb_max'
             AND patient_hb <= (ch.numeric_thresholds->>'hb_max')::NUMERIC)
        )
        AND ch.id NOT IN (SELECT sm.chunk_id FROM semantic_matches sm)
        LIMIT 5
    )
    SELECT * FROM semantic_matches
    UNION ALL
    SELECT * FROM threshold_matches;
END;
$$;


ALTER FUNCTION "public"."search_clinical_chunks_hybrid"("query_embedding" "extensions"."vector", "query_text" "text", "filter_specialty" "text", "filter_chunk_types" "text"[], "filter_urgency" "text", "filter_comorbidity" "text", "filter_care_level" "text", "filter_drug_class" "text", "patient_sbp" integer, "patient_dbp" integer, "patient_hb" numeric, "match_count" integer, "min_similarity" double precision) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."search_clinical_chunks_hybrid"("query_embedding" "extensions"."vector", "query_text" "text", "filter_specialty" "text", "filter_chunk_types" "text"[], "filter_urgency" "text", "filter_comorbidity" "text", "filter_care_level" "text", "filter_drug_class" "text", "patient_sbp" integer, "patient_dbp" integer, "patient_hb" numeric, "match_count" integer, "min_similarity" double precision) IS 'Hybrid search combining semantic similarity with numeric threshold matching';



CREATE OR REPLACE FUNCTION "public"."search_guidelines_by_keywords"("search_query" "text", "match_specialty" "text" DEFAULT NULL::"text", "match_count" integer DEFAULT 10) RETURNS TABLE("id" "uuid", "source_name" "text", "document_title" "text", "chunk_text" "text", "topics" "text"[], "evidence_level" "text", "rank" real)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'extensions', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        g.id,
        g.source_name,
        g.document_title,
        g.chunk_text,
        g.topics,
        g.evidence_level,
        ts_rank(to_tsvector('english', g.chunk_text), plainto_tsquery('english', search_query)) as rank
    FROM clinical_guidelines g
    WHERE g.is_active = TRUE
    AND (match_specialty IS NULL OR g.specialty = match_specialty)
    AND to_tsvector('english', g.chunk_text) @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."search_guidelines_by_keywords"("search_query" "text", "match_specialty" "text", "match_count" integer) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."search_guidelines_by_keywords"("search_query" "text", "match_specialty" "text", "match_count" integer) IS 'Full-text keyword search for guidelines (fallback when embeddings unavailable)';



CREATE OR REPLACE FUNCTION "public"."search_investigations_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_investigation_type" character varying DEFAULT NULL::character varying, "p_limit" integer DEFAULT 20) RETURNS TABLE("id" "uuid", "investigation_name" character varying, "common_names" "text"[], "investigation_type" character varying, "category" character varying, "normalized_name" character varying, "source" character varying, "priority" integer)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        di.id,
        di.investigation_name,
        di.common_names,
        di.investigation_type,
        di.category,
        di.normalized_name,
        'doctor_list'::VARCHAR as source,
        1 as priority
    FROM doctor_investigations di
    WHERE di.doctor_id = p_doctor_id
      AND di.is_active = true
      AND (p_investigation_type IS NULL OR di.investigation_type = p_investigation_type)
      AND (
          di.normalized_name ILIKE '%' || LOWER(p_search_term) || '%'
          OR di.investigation_name ILIKE '%' || p_search_term || '%'
          OR EXISTS (SELECT 1 FROM unnest(di.search_tokens) t WHERE t ILIKE '%' || LOWER(p_search_term) || '%')
      )

    UNION ALL

    SELECT
        hi.id,
        hi.investigation_name,
        hi.common_names,
        hi.investigation_type,
        hi.category,
        hi.normalized_name,
        'hospital_list'::VARCHAR as source,
        2 as priority
    FROM hospital_investigation_lists hi
    JOIN doctors d ON d.hospital_id = hi.hospital_id
    WHERE d.id = p_doctor_id
      AND hi.is_active = true
      AND (p_investigation_type IS NULL OR hi.investigation_type = p_investigation_type)
      AND (
          hi.normalized_name ILIKE '%' || LOWER(p_search_term) || '%'
          OR hi.investigation_name ILIKE '%' || p_search_term || '%'
          OR EXISTS (SELECT 1 FROM unnest(hi.search_tokens) t WHERE t ILIKE '%' || LOWER(p_search_term) || '%')
      )
      AND NOT EXISTS (
          SELECT 1 FROM doctor_investigations di2
          WHERE di2.doctor_id = p_doctor_id
            AND di2.normalized_name = hi.normalized_name
            AND di2.is_active = true
      )

    ORDER BY priority, investigation_name
    LIMIT p_limit;
END;
$$;


ALTER FUNCTION "public"."search_investigations_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_investigation_type" character varying, "p_limit" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."search_medicines_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_limit" integer DEFAULT 20) RETURNS TABLE("id" "uuid", "medicine_name" character varying, "common_names" "text"[], "category" character varying, "normalized_name" character varying, "source" character varying, "priority" integer)
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    RETURN QUERY
    -- Doctor's personal medicines (higher priority)
    SELECT
        dm.id,
        dm.medicine_name,
        dm.common_names,
        dm.category,
        dm.normalized_name,
        'doctor_list'::VARCHAR as source,
        1 as priority
    FROM doctor_medicines dm
    WHERE dm.doctor_id = p_doctor_id
      AND dm.is_active = true
      AND (
          dm.normalized_name ILIKE '%' || LOWER(p_search_term) || '%'
          OR dm.medicine_name ILIKE '%' || p_search_term || '%'
          OR EXISTS (SELECT 1 FROM unnest(dm.search_tokens) t WHERE t ILIKE '%' || LOWER(p_search_term) || '%')
      )

    UNION ALL

    -- Hospital medicines (lower priority)
    SELECT
        hm.id,
        hm.medicine_name,
        hm.common_names,
        hm.category,
        hm.normalized_name,
        'hospital_list'::VARCHAR as source,
        2 as priority
    FROM hospital_medicine_lists hm
    JOIN doctors d ON d.hospital_id = hm.hospital_id
    WHERE d.id = p_doctor_id
      AND hm.is_active = true
      AND (
          hm.normalized_name ILIKE '%' || LOWER(p_search_term) || '%'
          OR hm.medicine_name ILIKE '%' || p_search_term || '%'
          OR EXISTS (SELECT 1 FROM unnest(hm.search_tokens) t WHERE t ILIKE '%' || LOWER(p_search_term) || '%')
      )
      -- Exclude if doctor already has this medicine in personal list
      AND NOT EXISTS (
          SELECT 1 FROM doctor_medicines dm2
          WHERE dm2.doctor_id = p_doctor_id
            AND dm2.normalized_name = hm.normalized_name
            AND dm2.is_active = true
      )

    ORDER BY priority, medicine_name
    LIMIT p_limit;
END;
$$;


ALTER FUNCTION "public"."search_medicines_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_limit" integer) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."search_medicines_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_limit" integer) IS 'Combined search across doctor and hospital medicine lists';



CREATE OR REPLACE FUNCTION "public"."update_client_last_used"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    UPDATE api_clients
    SET last_used_at = now()
    WHERE id = NEW.client_id;
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_client_last_used"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_doctor_templates_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_doctor_templates_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_extraction_metrics_rpc"("p_consultation_type_code" character varying, "p_extraction_time_seconds" numeric) RETURNS "void"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    UPDATE consultation_type_system_prompts
    SET
        total_extractions = total_extractions + 1,
        avg_extraction_time_seconds = CASE
            WHEN total_extractions = 0 THEN p_extraction_time_seconds
            ELSE ((avg_extraction_time_seconds * total_extractions) + p_extraction_time_seconds) / (total_extractions + 1)
        END,
        updated_at = NOW()
    WHERE consultation_type_code = p_consultation_type_code
      AND is_active = true;
END;
$$;


ALTER FUNCTION "public"."update_extraction_metrics_rpc"("p_consultation_type_code" character varying, "p_extraction_time_seconds" numeric) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_followup_tracking_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_followup_tracking_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_hospital_ehr_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_hospital_ehr_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_intervention_outcomes_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_intervention_outcomes_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_intervention_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_intervention_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_job_progress"("p_submission_id" "uuid", "p_status" character varying, "p_progress" integer, "p_message" "text" DEFAULT NULL::"text") RETURNS "void"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    UPDATE processing_jobs
    SET
        status = p_status,
        progress_percentage = p_progress,
        progress_message = COALESCE(p_message, progress_message),
        updated_at = NOW()
    WHERE submission_id = p_submission_id;

    -- Update session status if job is completed or errored
    IF p_status IN ('COMPLETED', 'ERROR') THEN
        UPDATE recording_sessions
        SET
            status = p_status,
            completed_at = NOW()
        WHERE id = (SELECT session_id FROM processing_jobs WHERE submission_id = p_submission_id);
    END IF;
END;
$$;


ALTER FUNCTION "public"."update_job_progress"("p_submission_id" "uuid", "p_status" character varying, "p_progress" integer, "p_message" "text") OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."triage_layer_config" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "layer_code" character varying(50) NOT NULL,
    "layer_name" character varying(100) NOT NULL,
    "description" "text",
    "is_enabled" boolean DEFAULT false,
    "weight" numeric(3,2) DEFAULT 1.0,
    "config" "jsonb" DEFAULT '{}'::"jsonb",
    "display_order" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "triage_layer_config_weight_check" CHECK ((("weight" >= (0)::numeric) AND ("weight" <= (1)::numeric)))
);


ALTER TABLE "public"."triage_layer_config" OWNER TO "postgres";


COMMENT ON TABLE "public"."triage_layer_config" IS 'Configuration for triage engine layers - controls which layers are active';



COMMENT ON COLUMN "public"."triage_layer_config"."layer_code" IS 'Unique code: base_mvp, doctor_practice, hospital_intelligence, rag_guidelines';



COMMENT ON COLUMN "public"."triage_layer_config"."weight" IS 'Layer weight for conflict resolution scoring (0.0-1.0)';



COMMENT ON COLUMN "public"."triage_layer_config"."config" IS 'Layer-specific JSON configuration (e.g., min_confidence, cache_hours)';



CREATE OR REPLACE FUNCTION "public"."update_triage_layer_config"("p_layer_code" "text", "p_is_enabled" boolean DEFAULT NULL::boolean, "p_weight" numeric DEFAULT NULL::numeric) RETURNS "public"."triage_layer_config"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
DECLARE
    v_result triage_layer_config%ROWTYPE;
BEGIN
    UPDATE triage_layer_config
    SET
        is_enabled = COALESCE(p_is_enabled, is_enabled),
        weight = COALESCE(p_weight, weight),
        updated_at = NOW()
    WHERE layer_code = p_layer_code
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$$;


ALTER FUNCTION "public"."update_triage_layer_config"("p_layer_code" "text", "p_is_enabled" boolean, "p_weight" numeric) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."update_triage_layer_config"("p_layer_code" "text", "p_is_enabled" boolean, "p_weight" numeric) IS 'Update global triage layer configuration';



CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."validate_merge_sources"("p_source_extraction_ids" "uuid"[]) RETURNS TABLE("is_valid" boolean, "error_message" "text", "patient_id" "uuid", "extraction_count" integer)
    LANGUAGE "plpgsql" STABLE
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
  DECLARE
      v_distinct_patients INTEGER;
      v_patient_id UUID;
      v_extraction_count INTEGER;
  BEGIN
      SELECT
          COUNT(DISTINCT me.patient_id),
          (ARRAY_AGG(DISTINCT me.patient_id))[1],
          COUNT(*)
      INTO v_distinct_patients, v_patient_id, v_extraction_count
      FROM medical_extractions me
      WHERE me.id = ANY(p_source_extraction_ids);

      IF v_extraction_count != array_length(p_source_extraction_ids, 1) THEN
          RETURN QUERY SELECT FALSE, 'One or more extraction IDs not found'::TEXT, NULL::UUID, 0;
          RETURN;
      END IF;

      IF v_distinct_patients > 1 THEN
          RETURN QUERY SELECT FALSE, 'Cannot merge extractions from different patients'::TEXT, NULL::UUID, v_extraction_count;
          RETURN;
      END IF;

      IF v_extraction_count < 2 THEN
          RETURN QUERY SELECT FALSE, 'At least 2 extractions required for merge'::TEXT, v_patient_id, v_extraction_count;
          RETURN;
      END IF;

      RETURN QUERY SELECT TRUE, 'Valid for merge'::TEXT, v_patient_id, v_extraction_count;
  END;
  $$;


ALTER FUNCTION "public"."validate_merge_sources"("p_source_extraction_ids" "uuid"[]) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."validate_segment_configuration"("p_doctor_id" "uuid") RETURNS TABLE("is_valid" boolean, "error_message" "text")
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
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
$$;


ALTER FUNCTION "public"."validate_segment_configuration"("p_doctor_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."validate_segment_configuration"("p_doctor_id" "uuid") IS 'Validates that required segments within activated templates are in CORE category.

Updated in migration 20251127000000 to:
- Fix case sensitivity (CORE vs core) - now case-insensitive
- Only validate segments that are actually IN the template (not all global required segments)
- Ignore segments with category = excluded
- Join on segment_id instead of segment_code for correctness

Logic:
1. If doctor has no activated templates -> PASS (uses global templates)
2. Count required segments in doctor''s templates (excluding ''excluded'' category)
3. Count required segments that are in ''core'' category
4. If all required segments are in core -> PASS, otherwise FAIL

Parameters:
  p_doctor_id: Doctor UUID

Returns:
  is_valid: TRUE if configuration is valid
  error_message: NULL if valid, error description if invalid';



CREATE TABLE IF NOT EXISTS "public"."admin_action_log" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "admin_id" "uuid" NOT NULL,
    "admin_email" "text" NOT NULL,
    "admin_role" "text",
    "action" "text" NOT NULL,
    "resource_type" "text",
    "resource_id" "text",
    "endpoint" "text" NOT NULL,
    "method" "text" NOT NULL,
    "ip_address" "inet",
    "user_agent" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "request_id" "uuid",
    "status_code" integer,
    "response_time_ms" integer,
    "error_message" "text",
    "before_value" "jsonb",
    "after_value" "jsonb",
    "request_body" "jsonb"
);


ALTER TABLE "public"."admin_action_log" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."admin_users" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "auth_user_id" "uuid" NOT NULL,
    "email" "text" NOT NULL,
    "full_name" "text",
    "role" "text" DEFAULT 'admin'::"text",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "hospital_id" "uuid",
    CONSTRAINT "admin_users_role_check" CHECK (("role" = ANY (ARRAY['super_admin'::"text", 'admin'::"text", 'viewer'::"text"])))
);


ALTER TABLE "public"."admin_users" OWNER TO "postgres";


COMMENT ON TABLE "public"."admin_users" IS 'Admin users for the local web dashboard (links to Supabase auth)';



COMMENT ON COLUMN "public"."admin_users"."hospital_id" IS 'Hospital scope. NULL = global/super_admin access. Non-NULL = restricted to this hospital.';



CREATE TABLE IF NOT EXISTS "public"."allied_health_needs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "patient_id" "uuid",
    "doctor_id" "uuid",
    "priority_level" "text" DEFAULT 'NONE'::"text",
    "is_mental_health" boolean DEFAULT false,
    "is_nutritional_health" boolean DEFAULT false,
    "is_physiotherapy" boolean DEFAULT false,
    "is_homecare" boolean DEFAULT false,
    "is_sleep_therapy" boolean DEFAULT false,
    "is_rehab_cardiac" boolean DEFAULT false,
    "is_rehab_common" boolean DEFAULT false,
    "is_treatment_education" boolean DEFAULT false,
    "is_wellness" boolean DEFAULT false,
    "mental_health_reasons" "text"[] DEFAULT '{}'::"text"[],
    "nutritional_health_reasons" "text"[] DEFAULT '{}'::"text"[],
    "physiotherapy_reasons" "text"[] DEFAULT '{}'::"text"[],
    "homecare_reasons" "text"[] DEFAULT '{}'::"text"[],
    "sleep_therapy_reasons" "text"[] DEFAULT '{}'::"text"[],
    "rehab_cardiac_reasons" "text"[] DEFAULT '{}'::"text"[],
    "rehab_common_reasons" "text"[] DEFAULT '{}'::"text"[],
    "treatment_education_reasons" "text"[] DEFAULT '{}'::"text"[],
    "wellness_reasons" "text"[] DEFAULT '{}'::"text"[],
    "clinical_severity_id" "uuid",
    "other_clinical_needs_id" "uuid",
    "calculation_version" "text" DEFAULT '1.0.0'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "consultation_insights_id" "uuid",
    CONSTRAINT "allied_health_needs_priority_level_check" CHECK (("priority_level" = ANY (ARRAY['NONE'::"text", 'LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text"])))
);


ALTER TABLE "public"."allied_health_needs" OWNER TO "postgres";


COMMENT ON TABLE "public"."allied_health_needs" IS 'Allied health referral needs. Raw AI signals in consultation_insights (join via consultation_insights_id)';



COMMENT ON COLUMN "public"."allied_health_needs"."priority_level" IS 'Consolidated priority: HIGH (4+ or mental_health+any), MEDIUM (2-3), LOW (1), NONE (0)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_mental_health" IS 'Needs mental health support (severe anxiety, depression, distress)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_nutritional_health" IS 'Needs nutritional counseling (diabetes/obesity/cardiac + diet instructions)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_physiotherapy" IS 'Needs physiotherapy (musculoskeletal/injury + PT mentioned)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_homecare" IS 'Needs home care (age>70 + chronic + mobility issues)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_sleep_therapy" IS 'Needs sleep therapy (snoring/apnea/fatigue + obesity/HTN)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_rehab_cardiac" IS 'Needs cardiac rehabilitation (MI/ischemic/post-CABG)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_rehab_common" IS 'Needs general rehabilitation (ortho surgery/stroke)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_treatment_education" IS 'Needs treatment education (new diagnosis + understanding barrier)';



COMMENT ON COLUMN "public"."allied_health_needs"."is_wellness" IS 'Needs wellness program (lifestyle disease + prevention discussion)';



COMMENT ON COLUMN "public"."allied_health_needs"."consultation_insights_id" IS 'Reference to consultation_insights for raw AI signals (analytics joins)';



CREATE TABLE IF NOT EXISTS "public"."api_client_usage" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "client_id" "uuid",
    "endpoint" "text" NOT NULL,
    "method" "text" NOT NULL,
    "doctor_id" "uuid",
    "patient_id" "text",
    "status_code" integer,
    "response_time_ms" integer,
    "error_message" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."api_client_usage" OWNER TO "postgres";


COMMENT ON TABLE "public"."api_client_usage" IS 'API usage tracking for rate limiting and analytics';



CREATE TABLE IF NOT EXISTS "public"."api_clients" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "client_name" "text" NOT NULL,
    "client_type" "text" NOT NULL,
    "api_key_hash" "text",
    "api_key_prefix" character varying(8),
    "jwt_secret" "text",
    "hospital_id" "uuid",
    "allowed_doctor_ids" "uuid"[],
    "scopes" "text"[] DEFAULT ARRAY['read:extractions'::"text", 'write:extractions'::"text"],
    "is_active" boolean DEFAULT true,
    "rate_limit_per_hour" integer DEFAULT 1000,
    "contact_email" "text",
    "description" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "last_used_at" timestamp with time zone,
    "auth_mode" "text" DEFAULT 'api_key'::"text" NOT NULL,
    "client_secret_hash" "text",
    "token_expiry_minutes" integer DEFAULT 120 NOT NULL,
    CONSTRAINT "api_clients_auth_mode_check" CHECK (("auth_mode" = ANY (ARRAY['api_key'::"text", 'token'::"text"]))),
    CONSTRAINT "api_clients_client_type_check" CHECK (("client_type" = ANY (ARRAY['ehr'::"text", 'mobile_app'::"text", 'web_app'::"text"]))),
    CONSTRAINT "api_clients_token_expiry_check" CHECK ((("token_expiry_minutes" >= 1) AND ("token_expiry_minutes" <= 1440))),
    CONSTRAINT "ehr_requires_hospital" CHECK ((("client_type" <> 'ehr'::"text") OR ("hospital_id" IS NOT NULL)))
);


ALTER TABLE "public"."api_clients" OWNER TO "postgres";


COMMENT ON TABLE "public"."api_clients" IS 'API clients for EHR integrations, mobile apps, and external web apps';



CREATE TABLE IF NOT EXISTS "public"."app_settings" (
    "key" "text" NOT NULL,
    "value" "text" NOT NULL,
    "description" "text",
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."app_settings" OWNER TO "postgres";


COMMENT ON TABLE "public"."app_settings" IS 'Runtime application settings that can be toggled without redeployment';



CREATE TABLE IF NOT EXISTS "public"."audio_chunks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "session_id" "uuid" NOT NULL,
    "chunk_index" integer NOT NULL,
    "chunk_timestamp" timestamp with time zone NOT NULL,
    "audio_data" "text",
    "mime_type" character varying(100) DEFAULT 'audio/webm'::character varying NOT NULL,
    "duration_seconds" numeric(10,2),
    "file_size_bytes" integer,
    "is_last" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."audio_chunks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."audio_validation_warnings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "session_id" "uuid" NOT NULL,
    "chunk_index" integer,
    "warning_type" "text" NOT NULL,
    "declared_mime_type" "text",
    "detected_format" "text",
    "message" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."audio_validation_warnings" OWNER TO "postgres";


COMMENT ON TABLE "public"."audio_validation_warnings" IS 'Stores audio validation warnings for debugging. Warnings are logged when MIME type mismatches or unsupported formats are detected.';



CREATE TABLE IF NOT EXISTS "public"."bill_line_items" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "bill_id" "uuid" NOT NULL,
    "category" character varying(50) NOT NULL,
    "description" "text" NOT NULL,
    "item_code" character varying(50),
    "quantity" numeric(10,2) DEFAULT 1,
    "unit_price" numeric(10,2),
    "total_price" numeric(12,2),
    "confidence" character varying(20) DEFAULT 'medium'::character varying,
    "billing_action" character varying(30) DEFAULT 'pending_review'::character varying,
    "source_segment" character varying(50),
    "source_item_index" integer,
    "matched_master_id" "uuid",
    "matched_master_table" character varying(50),
    "match_confidence" numeric(4,2),
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."bill_line_items" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bills" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid",
    "hospital_id" "uuid" NOT NULL,
    "patient_id" "uuid",
    "doctor_id" "uuid",
    "bill_type" character varying(20) DEFAULT 'OP'::character varying NOT NULL,
    "bill_status" character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    "consultation_type_code" character varying(50),
    "is_merged_bill" boolean DEFAULT false,
    "superseded_by_bill_id" "uuid",
    "total_amount" numeric(12,2) DEFAULT 0,
    "auto_billed_amount" numeric(12,2) DEFAULT 0,
    "pending_review_amount" numeric(12,2) DEFAULT 0,
    "flagged_amount" numeric(12,2) DEFAULT 0,
    "generation_metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "visit_id" character varying(255),
    "visit_date" timestamp with time zone,
    "billed_by" character varying(255)
);


ALTER TABLE "public"."bills" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."care_quality_risk" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "patient_id" "uuid",
    "doctor_id" "uuid",
    "care_quality_score" numeric(5,2) NOT NULL,
    "risk_level" "text" NOT NULL,
    "is_medication_issue" boolean DEFAULT false,
    "is_missed_red_flag" boolean DEFAULT false,
    "is_incomplete_treatment" boolean DEFAULT false,
    "is_followup_gap" boolean DEFAULT false,
    "medication_issue_reasons" "text"[] DEFAULT '{}'::"text"[],
    "missed_red_flag_reasons" "text"[] DEFAULT '{}'::"text"[],
    "incomplete_treatment_reasons" "text"[] DEFAULT '{}'::"text"[],
    "followup_gap_reasons" "text"[] DEFAULT '{}'::"text"[],
    "medication_issue_severity" "text",
    "missed_red_flag_severity" "text",
    "incomplete_treatment_severity" "text",
    "followup_gap_severity" "text",
    "reasons" "text"[] DEFAULT '{}'::"text"[],
    "base_score" numeric(5,2),
    "indicator_count" integer,
    "primary_risk_driver" "text",
    "input_data" "jsonb" DEFAULT '{}'::"jsonb",
    "calculation_version" "text" DEFAULT '1.0.0'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "care_quality_risk_risk_level_check" CHECK (("risk_level" = ANY (ARRAY['LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'CRITICAL'::"text"])))
);


ALTER TABLE "public"."care_quality_risk" OWNER TO "postgres";


COMMENT ON TABLE "public"."care_quality_risk" IS 'Care quality risk assessment identifying medication issues, missed red flags, incomplete treatment plans, and follow-up gaps';



COMMENT ON COLUMN "public"."care_quality_risk"."care_quality_score" IS 'Risk score 0-100% indicating care quality concerns';



COMMENT ON COLUMN "public"."care_quality_risk"."reasons" IS 'Consolidated human-readable array of all triggered indicator reasons';



CREATE TABLE IF NOT EXISTS "public"."clinical_chunk_embeddings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "chunk_id" "uuid" NOT NULL,
    "embedding" "extensions"."vector"(1536),
    "embedding_model" "text" DEFAULT 'cohere-embed-english-v3.0'::"text",
    "embedding_model_id" "uuid",
    "content_hash" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."clinical_chunk_embeddings" OWNER TO "postgres";


COMMENT ON TABLE "public"."clinical_chunk_embeddings" IS 'Vector embeddings for clinical chunks (semantic search)';



CREATE TABLE IF NOT EXISTS "public"."clinical_chunks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "condition_id" "uuid" NOT NULL,
    "chunk_type" "text" NOT NULL,
    "chunk_index" integer DEFAULT 0,
    "content_json" "jsonb" NOT NULL,
    "content_text" "text" NOT NULL,
    "urgency_default" "text",
    "has_emergency_triggers" boolean DEFAULT false,
    "has_red_flags" boolean DEFAULT false,
    "care_levels" "text"[] DEFAULT '{}'::"text"[],
    "comorbidity" "text",
    "numeric_thresholds" "jsonb",
    "drug_classes" "text"[] DEFAULT '{}'::"text"[],
    "drug_names" "text"[] DEFAULT '{}'::"text"[],
    "contraindications" "text"[] DEFAULT '{}'::"text"[],
    "source_section" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "clinical_chunks_chunk_type_check" CHECK (("chunk_type" = ANY (ARRAY['triage_criteria'::"text", 'classification'::"text", 'presentation'::"text", 'differential'::"text", 'investigation'::"text", 'treatment_primary'::"text", 'treatment_district'::"text", 'treatment_tertiary'::"text", 'treatment_escalation'::"text", 'comorbidity_pathway'::"text", 'drug_formulary'::"text", 'emergency_protocol'::"text", 'follow_up'::"text", 'patient_education'::"text", 'step_protocol'::"text", 'decision_node'::"text"]))),
    CONSTRAINT "clinical_chunks_urgency_default_check" CHECK (("urgency_default" = ANY (ARRAY['routine'::"text", 'urgent'::"text", 'emergency'::"text"])))
);


ALTER TABLE "public"."clinical_chunks" OWNER TO "postgres";


COMMENT ON TABLE "public"."clinical_chunks" IS 'Semantic chunks of clinical conditions for RAG retrieval';



COMMENT ON COLUMN "public"."clinical_chunks"."chunk_type" IS 'Semantic type: triage_criteria, treatment_primary, comorbidity_pathway, etc.';



COMMENT ON COLUMN "public"."clinical_chunks"."care_levels" IS 'Healthcare facility levels where this applies: phc, district, tertiary';



COMMENT ON COLUMN "public"."clinical_chunks"."numeric_thresholds" IS 'Quantitative thresholds for direct matching (BP, Hb, etc.)';



CREATE TABLE IF NOT EXISTS "public"."clinical_condition_ingestion_jobs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "file_name" "text" NOT NULL,
    "file_path" "text",
    "source_name" "text" NOT NULL,
    "specialty" "text" NOT NULL,
    "document_type" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text",
    "error_message" "text",
    "validation_errors" "jsonb",
    "total_conditions" integer DEFAULT 0,
    "processed_conditions" integer DEFAULT 0,
    "total_chunks" integer DEFAULT 0,
    "embedded_chunks" integer DEFAULT 0,
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "clinical_condition_ingestion_jobs_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'validating'::"text", 'processing'::"text", 'embedding'::"text", 'completed'::"text", 'failed'::"text"])))
);


ALTER TABLE "public"."clinical_condition_ingestion_jobs" OWNER TO "postgres";


COMMENT ON TABLE "public"."clinical_condition_ingestion_jobs" IS 'Track clinical condition JSON ingestion jobs';



CREATE TABLE IF NOT EXISTS "public"."clinical_conditions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "condition_id" "text" NOT NULL,
    "name" "text" NOT NULL,
    "aliases" "text"[] DEFAULT '{}'::"text"[],
    "icd_codes" "text"[] DEFAULT '{}'::"text"[],
    "source_name" "text" NOT NULL,
    "specialty" "text" NOT NULL,
    "document_type" "text" NOT NULL,
    "version" "text",
    "language" "text" DEFAULT 'en'::"text",
    "classification" "jsonb",
    "triage_metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "clinical_presentation" "jsonb",
    "differential_diagnosis" "jsonb",
    "investigations" "jsonb",
    "treatment_by_care_level" "jsonb",
    "comorbidity_pathways" "jsonb",
    "drug_formulary" "jsonb",
    "step_wise_management" "jsonb",
    "emergency_protocols" "jsonb",
    "follow_up" "jsonb",
    "patient_education" "jsonb",
    "full_json" "jsonb",
    "is_active" boolean DEFAULT true,
    "is_verified" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "clinical_conditions_document_type_check" CHECK (("document_type" = ANY (ARRAY['narrative_guideline'::"text", 'visual_workflow'::"text", 'step_protocol'::"text"])))
);


ALTER TABLE "public"."clinical_conditions" OWNER TO "postgres";


COMMENT ON TABLE "public"."clinical_conditions" IS 'Master registry of clinical conditions with structured treatment guidelines';



COMMENT ON COLUMN "public"."clinical_conditions"."condition_id" IS 'Unique condition identifier (e.g., cardio_htn_001)';



COMMENT ON COLUMN "public"."clinical_conditions"."document_type" IS 'STG format: narrative_guideline, visual_workflow, or step_protocol';



COMMENT ON COLUMN "public"."clinical_conditions"."triage_metadata" IS 'Critical triage info: urgency_levels, emergency_triggers, red_flags, referral_triggers';



COMMENT ON COLUMN "public"."clinical_conditions"."comorbidity_pathways" IS 'Condition-specific management for common comorbidities';



CREATE TABLE IF NOT EXISTS "public"."clinical_guideline_embeddings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "guideline_id" "uuid" NOT NULL,
    "embedding" "extensions"."vector"(1536),
    "embedding_model" "text" DEFAULT 'cohere-embed-english-v3.0'::"text",
    "embedding_model_id" "uuid",
    "content_hash" "text",
    "token_count" integer,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."clinical_guideline_embeddings" OWNER TO "postgres";


COMMENT ON TABLE "public"."clinical_guideline_embeddings" IS 'Vector embeddings for clinical guidelines RAG search';



COMMENT ON COLUMN "public"."clinical_guideline_embeddings"."embedding" IS '1536-dim vector for semantic similarity search (cosine)';



CREATE TABLE IF NOT EXISTS "public"."clinical_guidelines" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_name" "text" NOT NULL,
    "source_organization" "text",
    "source_url" "text",
    "document_title" "text" NOT NULL,
    "specialty" "text" NOT NULL,
    "topics" "text"[] DEFAULT '{}'::"text"[],
    "presentations" "text"[] DEFAULT '{}'::"text"[],
    "icd_codes" "text"[] DEFAULT '{}'::"text"[],
    "full_text" "text",
    "chunk_text" "text" NOT NULL,
    "chunk_index" integer DEFAULT 0,
    "publication_year" integer,
    "version" "text",
    "evidence_level" "text",
    "region" "text" DEFAULT 'India'::"text",
    "is_active" boolean DEFAULT true,
    "is_verified" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."clinical_guidelines" OWNER TO "postgres";


COMMENT ON TABLE "public"."clinical_guidelines" IS 'Clinical guidelines library for RAG-based triage recommendations';



COMMENT ON COLUMN "public"."clinical_guidelines"."topics" IS 'Array of topic keywords for filtering (fever, infection, etc.)';



COMMENT ON COLUMN "public"."clinical_guidelines"."chunk_text" IS 'Chunked text (800-1000 tokens) optimized for embedding';



COMMENT ON COLUMN "public"."clinical_guidelines"."evidence_level" IS 'Evidence quality: Level A (high), Level B (moderate), Expert Consensus';



CREATE TABLE IF NOT EXISTS "public"."clinical_severity_assessments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "patient_id" "uuid",
    "doctor_id" "uuid",
    "severity_level" "text" NOT NULL,
    "total_score" integer NOT NULL,
    "was_overridden" boolean DEFAULT false,
    "override_reason" "text",
    "score_breakdown" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "contributing_factors" "text"[] DEFAULT '{}'::"text"[],
    "calculation_version" "text" DEFAULT '1.0.0'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "is_surgical" boolean DEFAULT false,
    "is_chronic" boolean DEFAULT false,
    "is_second_opinion" boolean DEFAULT false,
    "is_alternate_procedure" boolean DEFAULT false,
    "reasons" "text"[] DEFAULT '{}'::"text"[],
    "consultation_insights_id" "uuid",
    CONSTRAINT "clinical_severity_assessments_severity_level_check" CHECK (("severity_level" = ANY (ARRAY['LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text"])))
);


ALTER TABLE "public"."clinical_severity_assessments" OWNER TO "postgres";


COMMENT ON TABLE "public"."clinical_severity_assessments" IS 'Clinical severity scores. Raw AI signals in consultation_insights (join via consultation_insights_id)';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."severity_level" IS 'LOW (0-4 pts), MEDIUM (5-8 pts), HIGH (9+ pts or override)';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."was_overridden" IS 'True if severity was auto-set to HIGH due to critical conditions (cancer, MI, stroke, etc.)';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."score_breakdown" IS 'JSON breakdown of score components: icd_score, specialty_score, surgical_score, modifier_score';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."is_surgical" IS 'Whether treatment involves surgery (duplicated from input_data for querying)';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."is_chronic" IS 'Whether condition is chronic (duplicated from input_data for querying)';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."is_second_opinion" IS 'Whether doctor recommends specialist consultation (duplicated from input_data for querying)';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."is_alternate_procedure" IS 'Whether alternate treatment is suggested if first fails (duplicated from input_data for querying)';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."reasons" IS 'Human-readable array of reasons explaining the severity assessment';



COMMENT ON COLUMN "public"."clinical_severity_assessments"."consultation_insights_id" IS 'Reference to consultation_insights for raw AI signals (analytics joins)';



CREATE TABLE IF NOT EXISTS "public"."consultation_insights" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "patient_id" "uuid",
    "doctor_id" "uuid",
    "patient_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "clinical_severity_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "diagnostic_needs" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "medication_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "nutritional_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "physiotherapy_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "homecare_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "sleep_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "rehabilitation_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "wellness_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "mental_health_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "education_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "competitor_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "access_logistics_signals" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "model_used" character varying(50) DEFAULT 'gemini-2.5-flash'::character varying,
    "extraction_version" character varying(20) DEFAULT '1.0.0'::character varying,
    "extraction_duration_ms" integer,
    "raw_response" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."consultation_insights" OWNER TO "postgres";


COMMENT ON TABLE "public"."consultation_insights" IS 'Raw AI-extracted clinical signals from Gemini (14 signal groups) for analytics and downstream scoring';



COMMENT ON COLUMN "public"."consultation_insights"."patient_signals" IS 'Age, demographics from consultation';



COMMENT ON COLUMN "public"."consultation_insights"."clinical_severity_signals" IS 'ICD codes, specialty, surgical, chronic flags for severity scoring';



COMMENT ON COLUMN "public"."consultation_insights"."diagnostic_needs" IS 'Followup tests, recurring diagnostics, refill needs';



COMMENT ON COLUMN "public"."consultation_insights"."medication_signals" IS 'Medication count, complexity, injection needed, controlled substances';



COMMENT ON COLUMN "public"."consultation_insights"."competitor_signals" IS 'Second opinion mentions, competitor hospital references, price sensitivity';



COMMENT ON COLUMN "public"."consultation_insights"."access_logistics_signals" IS 'Travel barriers, time constraints, pharmacy access issues';



CREATE TABLE IF NOT EXISTS "public"."consultation_type_segments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "consultation_type_id" "uuid" NOT NULL,
    "segment_code" character varying(50) NOT NULL,
    "default_category" character varying(20) NOT NULL,
    "default_display_order" integer NOT NULL,
    "default_brevity_level" character varying(20) DEFAULT 'balanced'::character varying,
    "default_terminology_style" character varying(20) DEFAULT 'medical_terms'::character varying,
    "is_required_for_type" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "segment_id" "uuid",
    "consultation_type_name" "text",
    CONSTRAINT "consultation_type_segment_defau_default_terminology_style_check" CHECK ((("default_terminology_style")::"text" = ANY (ARRAY[('medical_terms'::character varying)::"text", ('simple_terms'::character varying)::"text", ('as_spoken'::character varying)::"text"]))),
    CONSTRAINT "consultation_type_segment_defaults_default_brevity_level_check" CHECK ((("default_brevity_level")::"text" = ANY (ARRAY[('concise'::character varying)::"text", ('balanced'::character varying)::"text", ('detailed'::character varying)::"text"]))),
    CONSTRAINT "consultation_type_segment_defaults_default_category_check" CHECK ((("default_category")::"text" = ANY (ARRAY[('core'::character varying)::"text", ('additional'::character varying)::"text", ('excluded'::character varying)::"text"])))
);


ALTER TABLE "public"."consultation_type_segments" OWNER TO "postgres";


COMMENT ON TABLE "public"."consultation_type_segments" IS 'Junction table: Maps segments to consultation types with type-specific configurations';



COMMENT ON COLUMN "public"."consultation_type_segments"."segment_id" IS 'Foreign key to segment_definitions.id (canonical reference)';



COMMENT ON COLUMN "public"."consultation_type_segments"."consultation_type_name" IS 'Denormalized consultation type name for performance (reduces JOINs)';



CREATE TABLE IF NOT EXISTS "public"."consultation_type_system_prompts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "consultation_type_id" "uuid" NOT NULL,
    "system_prompt_config_id" "uuid" NOT NULL,
    "consultation_type_code" character varying(50) NOT NULL,
    "config_code" character varying(100) NOT NULL,
    "is_active" boolean DEFAULT false,
    "total_extractions" integer DEFAULT 0,
    "avg_extraction_time_seconds" numeric(6,2),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."consultation_type_system_prompts" OWNER TO "postgres";


COMMENT ON TABLE "public"."consultation_type_system_prompts" IS 'Links consultation types to system prompt configurations';



COMMENT ON COLUMN "public"."consultation_type_system_prompts"."avg_extraction_time_seconds" IS 'Running average of extraction times for this config';



CREATE TABLE IF NOT EXISTS "public"."consultation_types" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "type_code" character varying(50) NOT NULL,
    "type_name" character varying(255) NOT NULL,
    "description" "text",
    "specialty_applicable" "text"[],
    "is_active" boolean DEFAULT true,
    "display_order" integer NOT NULL,
    "icon_name" character varying(50),
    "color_code" character varying(20),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "enable_emotion_analysis" boolean DEFAULT false,
    "visible_to_hospitals" "uuid"[],
    "visible_to_doctors" "uuid"[],
    "visible_to_specializations" "text"[],
    "emotion_extraction_mode" "text" DEFAULT 'none'::"text",
    "audio_emotion_mode" "text" DEFAULT 'none'::"text",
    "enable_triage_analysis" boolean DEFAULT true,
    "enable_consultation_insights" boolean DEFAULT true,
    "skip_transcription" boolean DEFAULT false,
    "extraction_includes_audio" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."consultation_types" OWNER TO "postgres";


COMMENT ON COLUMN "public"."consultation_types"."enable_emotion_analysis" IS 'Enable background emotion/subtext analysis for this consultation type. Runs 20s after main extraction starts.';



COMMENT ON COLUMN "public"."consultation_types"."enable_triage_analysis" IS 'Enable/disable triage suggestions generation for this consultation type. Default TRUE.';



COMMENT ON COLUMN "public"."consultation_types"."enable_consultation_insights" IS 'Enable/disable consultation insights extraction and all downstream assessments (severity, allied health, dropoff risk, quality, interventions). Default TRUE.';



COMMENT ON COLUMN "public"."consultation_types"."skip_transcription" IS 'When true, skip transcription and extract insights directly from audio. Auto-disables emotion/triage/insights.';



COMMENT ON COLUMN "public"."consultation_types"."extraction_includes_audio" IS 'When true, the main extraction call attaches the audio bytes alongside the transcript so Gemini can reason over both. Use only for templates whose prompts depend on voice cues. Adds latency.';



CREATE TABLE IF NOT EXISTS "public"."extraction_segments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "segment_code" character varying(50) NOT NULL,
    "segment_value" "jsonb" NOT NULL,
    "segment_value_text" "text" GENERATED ALWAYS AS (
CASE
    WHEN ("jsonb_typeof"("segment_value") = 'string'::"text") THEN ("segment_value" #>> '{}'::"text"[])
    ELSE ("segment_value")::"text"
END) STORED,
    "brevity_level" character varying(20),
    "terminology_style" character varying(50),
    "display_format" character varying(20),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "version_type" character varying(20) DEFAULT 'original'::character varying,
    CONSTRAINT "extraction_segments_version_type_check" CHECK ((("version_type")::"text" = ANY ((ARRAY['original'::character varying, 'edited'::character varying])::"text"[])))
);


ALTER TABLE "public"."extraction_segments" OWNER TO "postgres";


COMMENT ON COLUMN "public"."extraction_segments"."version_type" IS 'Version type: "original" for AI-generated, "edited" for doctor edits. NULL segment_value in edited row means deleted.';



CREATE OR REPLACE VIEW "public"."current_extraction_state" WITH ("security_invoker"='true') AS
 SELECT DISTINCT ON ("extraction_id", "segment_code") "extraction_id",
    "segment_code",
    "segment_value",
    "version_type",
    "brevity_level",
    "terminology_style",
    "display_format",
    "created_at",
    "updated_at",
        CASE
            WHEN (("version_type")::"text" = 'edited'::"text") THEN true
            ELSE false
        END AS "is_edited",
        CASE
            WHEN ((("version_type")::"text" = 'edited'::"text") AND ("segment_value" IS NULL)) THEN true
            ELSE false
        END AS "is_deleted"
   FROM "public"."extraction_segments"
  ORDER BY "extraction_id", "segment_code",
        CASE "version_type"
            WHEN 'edited'::"text" THEN 1
            WHEN 'original'::"text" THEN 2
            ELSE NULL::integer
        END;


ALTER VIEW "public"."current_extraction_state" OWNER TO "postgres";


COMMENT ON VIEW "public"."current_extraction_state" IS 'Current state of extraction segments. Returns edited version if exists (even if NULL/deleted), otherwise original.
Use this view for displaying current extraction data to users.';



CREATE TABLE IF NOT EXISTS "public"."doctor_doctor_patients" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "linked_doctor_id" "uuid" NOT NULL,
    "patient_ids" "uuid"[],
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "doctor_doctor_patients_check" CHECK (("doctor_id" <> "linked_doctor_id"))
);


ALTER TABLE "public"."doctor_doctor_patients" OWNER TO "postgres";


COMMENT ON TABLE "public"."doctor_doctor_patients" IS 'Doctor-to-doctor patient sharing. patient_ids=NULL shares all patients (practice-wide). patient_ids=[uuid,...] shares only those patients (selective handoff). Bidirectional: both rows (A→B and B→A) stored on link creation.';



CREATE TABLE IF NOT EXISTS "public"."doctor_investigations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "investigation_name" character varying(255) NOT NULL,
    "common_names" "text"[],
    "investigation_type" character varying(50) NOT NULL,
    "category" character varying(100),
    "normal_range" "text",
    "loinc_code" character varying(50),
    "cpt_code" character varying(50),
    "normalized_name" character varying(255) NOT NULL,
    "search_tokens" "text"[],
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "external_id" character varying(100),
    CONSTRAINT "valid_investigation_type" CHECK ((("investigation_type")::"text" = ANY (ARRAY[('laboratory'::character varying)::"text", ('imaging'::character varying)::"text", ('other'::character varying)::"text"])))
);


ALTER TABLE "public"."doctor_investigations" OWNER TO "postgres";


COMMENT ON COLUMN "public"."doctor_investigations"."external_id" IS 'External system ID (e.g., TestID from EHR systems)';



CREATE TABLE IF NOT EXISTS "public"."doctor_layer_preferences" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "enable_doctor_practice_layer" boolean DEFAULT true,
    "enable_hospital_intelligence_layer" boolean DEFAULT true,
    "enable_rag_guidelines_layer" boolean DEFAULT true,
    "weight_base_mvp" numeric(3,2) DEFAULT 1.0,
    "weight_doctor_practice" numeric(3,2) DEFAULT 0.8,
    "weight_hospital_intelligence" numeric(3,2) DEFAULT 0.7,
    "weight_rag_guidelines" numeric(3,2) DEFAULT 0.9,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "doctor_layer_preferences_weight_base_mvp_check" CHECK ((("weight_base_mvp" >= (0)::numeric) AND ("weight_base_mvp" <= (1)::numeric))),
    CONSTRAINT "doctor_layer_preferences_weight_doctor_practice_check" CHECK ((("weight_doctor_practice" >= (0)::numeric) AND ("weight_doctor_practice" <= (1)::numeric))),
    CONSTRAINT "doctor_layer_preferences_weight_hospital_intelligence_check" CHECK ((("weight_hospital_intelligence" >= (0)::numeric) AND ("weight_hospital_intelligence" <= (1)::numeric))),
    CONSTRAINT "doctor_layer_preferences_weight_rag_guidelines_check" CHECK ((("weight_rag_guidelines" >= (0)::numeric) AND ("weight_rag_guidelines" <= (1)::numeric)))
);


ALTER TABLE "public"."doctor_layer_preferences" OWNER TO "postgres";


COMMENT ON TABLE "public"."doctor_layer_preferences" IS 'Per-doctor layer enable/disable and weight configuration';



COMMENT ON COLUMN "public"."doctor_layer_preferences"."weight_rag_guidelines" IS 'RAG guidelines get high weight (0.9) as they are evidence-based';



CREATE TABLE IF NOT EXISTS "public"."doctor_medicines" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "medicine_name" character varying(255) NOT NULL,
    "common_names" "text"[],
    "category" character varying(100),
    "typical_dosage" character varying(255),
    "form" character varying(50),
    "snomed_code" character varying(50),
    "formulary_name" character varying(255),
    "medicine_type" character varying(20),
    "normalized_name" character varying(255) NOT NULL,
    "search_tokens" "text"[],
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "external_id" character varying(100),
    "product_code" "text",
    CONSTRAINT "valid_medicine_type" CHECK ((("medicine_type" IS NULL) OR (("medicine_type")::"text" = ANY (ARRAY[('generic'::character varying)::"text", ('branded'::character varying)::"text"]))))
);


ALTER TABLE "public"."doctor_medicines" OWNER TO "postgres";


COMMENT ON TABLE "public"."doctor_medicines" IS 'Per-doctor medicine list for prescription matching';



COMMENT ON COLUMN "public"."doctor_medicines"."common_names" IS 'Alternative names doctors commonly use (e.g., dolo tablet)';



COMMENT ON COLUMN "public"."doctor_medicines"."normalized_name" IS 'Lowercase, no prefix (TAB./CAP.) for matching';



COMMENT ON COLUMN "public"."doctor_medicines"."search_tokens" IS 'Tokenized words for GIN index search';



COMMENT ON COLUMN "public"."doctor_medicines"."external_id" IS 'External system ID (e.g., BrandID from EHR systems)';



COMMENT ON COLUMN "public"."doctor_medicines"."product_code" IS 'Product code from EHR system (e.g., Raster productCode). Populated from CSV upload.';



CREATE TABLE IF NOT EXISTS "public"."doctor_segment_configurations_backup_014" (
    "id" "uuid",
    "doctor_id" "uuid",
    "segment_code" character varying(50),
    "category" character varying(20),
    "display_order" integer,
    "brevity_level" character varying(20),
    "terminology_style" character varying(20),
    "custom_prompt_section" "text",
    "custom_schema_json" "jsonb",
    "created_at" timestamp with time zone,
    "updated_at" timestamp with time zone,
    "template_id" "uuid"
);


ALTER TABLE "public"."doctor_segment_configurations_backup_014" OWNER TO "postgres";


COMMENT ON TABLE "public"."doctor_segment_configurations_backup_014" IS 'Backup of doctor_segment_configurations before migration 014. Safe to drop after verification.';



CREATE TABLE IF NOT EXISTS "public"."doctor_templates" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "template_id" "uuid" NOT NULL,
    "access_level" "text" DEFAULT 'use'::"text" NOT NULL,
    "is_active" boolean DEFAULT false,
    "activated_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "doctor_templates_access_level_check" CHECK (("access_level" = ANY (ARRAY['view'::"text", 'use'::"text"])))
);


ALTER TABLE "public"."doctor_templates" OWNER TO "postgres";


COMMENT ON TABLE "public"."doctor_templates" IS 'Junction table for template sharing and activation.
- Templates with doctor_id=NULL are common (auto-available to all doctors)
- Templates with doctor_id=UUID are owned (access controlled by this table)
- access_level: "view" (read-only) or "use" (can apply for extractions)
- is_active: Currently selected default template for this doctor+consultation_type';



COMMENT ON COLUMN "public"."doctor_templates"."access_level" IS 'Access level: "view" (read-only), "use" (can apply in extractions).
Owner (template.doctor_id) can always edit regardless of this field.';



COMMENT ON COLUMN "public"."doctor_templates"."is_active" IS 'Whether this template is currently activated for this doctor.
Only one template per consultation_type can be active per doctor.';



CREATE TABLE IF NOT EXISTS "public"."doctors" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "email" character varying(255) NOT NULL,
    "full_name" character varying(255) NOT NULL,
    "specialization" character varying(100),
    "auth_user_id" "uuid",
    "default_transcription_engine" character varying(50) DEFAULT 'gemini'::character varying,
    "default_transcription_model" character varying(100) DEFAULT 'gemini-2.5-pro'::character varying,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "last_login_at" timestamp with time zone,
    "hospital_id" "uuid",
    "default_template_id" "uuid",
    "ehr_type_id" "uuid",
    "op_consultation_fee" numeric(10,2) DEFAULT NULL::numeric,
    "ip_primary_consultation_fee" numeric(10,2) DEFAULT NULL::numeric,
    "ip_secondary_consultation_fee" numeric(10,2) DEFAULT NULL::numeric,
    "translation_language" character varying(20) DEFAULT NULL::character varying
);


ALTER TABLE "public"."doctors" OWNER TO "postgres";


COMMENT ON COLUMN "public"."doctors"."default_template_id" IS 'Doctor-specific default template (overrides hospital default)';



COMMENT ON COLUMN "public"."doctors"."ehr_type_id" IS 'Which EHR this doctor uses. NULL = no EHR sync. Determines routing on extraction.';



COMMENT ON COLUMN "public"."doctors"."translation_language" IS 'Target Indic language for post-extraction translation (e.g., tamil, hindi, telugu). NULL = no translation.';



CREATE TABLE IF NOT EXISTS "public"."ehr_types" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "ehr_code" character varying(50) NOT NULL,
    "ehr_name" character varying(100) NOT NULL,
    "default_api_url" "text",
    "description" "text",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."ehr_types" OWNER TO "postgres";


COMMENT ON TABLE "public"."ehr_types" IS 'Master table for EHR providers. Each row represents an EHR system like Aosta, Raster, Neopead.';



COMMENT ON COLUMN "public"."ehr_types"."ehr_code" IS 'Unique identifier code: aosta, raster, neopead, etc.';



COMMENT ON COLUMN "public"."ehr_types"."default_api_url" IS 'Default API URL. Hospital config can override this.';



CREATE TABLE IF NOT EXISTS "public"."embedding_models" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "model_code" character varying(50) NOT NULL,
    "model_name" character varying(100) NOT NULL,
    "provider" character varying(50) NOT NULL,
    "dimensions" integer NOT NULL,
    "description" "text",
    "is_default" boolean DEFAULT false,
    "is_active" boolean DEFAULT true,
    "price_per_million_tokens" numeric(10,6),
    "max_tokens" integer DEFAULT 8192,
    "supports_batching" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."embedding_models" OWNER TO "postgres";


COMMENT ON TABLE "public"."embedding_models" IS 'Available embedding models for Q&A Engine. Cohere v4 is the recommended default for healthcare applications.';



COMMENT ON COLUMN "public"."embedding_models"."model_code" IS 'Unique identifier used in API calls (e.g., cohere_v4, openai_large)';



COMMENT ON COLUMN "public"."embedding_models"."dimensions" IS 'Vector dimensions for this model (768, 1536, 3072)';



CREATE TABLE IF NOT EXISTS "public"."extraction_accuracy_metrics" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "doctor_id" "uuid",
    "overall_wer" numeric(5,4) DEFAULT 0.0,
    "segment_metrics" "jsonb" DEFAULT '[]'::"jsonb",
    "entity_error_rate" numeric(7,4) DEFAULT 0.0,
    "entity_errors" "jsonb" DEFAULT '{}'::"jsonb",
    "total_words_ai_original" integer DEFAULT 0,
    "total_words_doctor_edit" integer DEFAULT 0,
    "doctor_additions_count" integer DEFAULT 0,
    "segments_unchanged" integer DEFAULT 0,
    "segments_modified" integer DEFAULT 0,
    "segments_total" integer DEFAULT 0,
    "computed_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "overall_wer_adjusted" numeric,
    "overall_wer_adjusted_descriptions" numeric(5,4)
);


ALTER TABLE "public"."extraction_accuracy_metrics" OWNER TO "postgres";


COMMENT ON COLUMN "public"."extraction_accuracy_metrics"."overall_wer_adjusted_descriptions" IS 'WER after subtracting clinical paraphrases AND deletion errors. Deletions in description-style free-text fields (chiefComplaints, etc.) are typically doctor trims, not AI errors.';



CREATE TABLE IF NOT EXISTS "public"."extraction_edit_history" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "version_number" integer NOT NULL,
    "edited_extraction_json" "jsonb" NOT NULL,
    "changed_segments" "text"[] DEFAULT '{}'::"text"[],
    "change_summary" "jsonb" DEFAULT '{}'::"jsonb",
    "edited_by" "uuid",
    "edited_by_type" character varying(20) DEFAULT 'doctor'::character varying,
    "edited_at" timestamp with time zone DEFAULT "now"(),
    "edit_source" character varying(20) DEFAULT 'webapp'::character varying
);


ALTER TABLE "public"."extraction_edit_history" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."extraction_embeddings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "model_id" "uuid" NOT NULL,
    "embedding" "extensions"."vector"(1536),
    "embedded_content" "text" NOT NULL,
    "content_hash" character varying(64),
    "hospital_id" "uuid",
    "doctor_id" "uuid",
    "patient_id" "uuid",
    "consultation_type_id" "uuid",
    "token_count" integer,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."extraction_embeddings" OWNER TO "postgres";


COMMENT ON TABLE "public"."extraction_embeddings" IS 'Document-level embeddings for full medical extractions (transcript + all segments)';



COMMENT ON COLUMN "public"."extraction_embeddings"."embedding" IS 'Vector embedding (1536 dims max). Supports Cohere v4, OpenAI small, Gemini. HNSW indexed for fast search.';



COMMENT ON COLUMN "public"."extraction_embeddings"."content_hash" IS 'SHA256 hash of embedded_content for detecting when re-embedding is needed';



CREATE TABLE IF NOT EXISTS "public"."extraction_photos" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "label" "text" NOT NULL,
    "original_filename" "text",
    "storage_path" "text" NOT NULL,
    "mime_type" "text" NOT NULL,
    "file_size_bytes" bigint NOT NULL,
    "uploaded_by" "uuid",
    "uploaded_by_type" character varying(20),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."extraction_photos" OWNER TO "postgres";


COMMENT ON TABLE "public"."extraction_photos" IS 'Photos/images attached to a medical_extractions row. Cascades on extraction delete; storage objects must be cleaned up by the backend service.';



COMMENT ON COLUMN "public"."extraction_photos"."label" IS 'User-provided caption for the photo.';



COMMENT ON COLUMN "public"."extraction_photos"."storage_path" IS 'Object path within the extraction-photos bucket.';



COMMENT ON COLUMN "public"."extraction_photos"."uploaded_by_type" IS 'Client type that uploaded: admin | web_app | ehr.';



CREATE TABLE IF NOT EXISTS "public"."extraction_relationships" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "merged_extraction_id" "uuid" NOT NULL,
    "source_extraction_id" "uuid" NOT NULL,
    "merge_order" integer NOT NULL,
    "merge_strategy" character varying(50) DEFAULT 'ai_contextual'::character varying NOT NULL,
    "source_metadata" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "valid_merge_order" CHECK (("merge_order" > 0))
);


ALTER TABLE "public"."extraction_relationships" OWNER TO "postgres";


COMMENT ON TABLE "public"."extraction_relationships" IS 'Tracks relationships between merged extractions and their source extractions';



COMMENT ON COLUMN "public"."extraction_relationships"."merge_order" IS 'Chronological order (1=oldest source, N=newest source) used for conflict resolution';



COMMENT ON COLUMN "public"."extraction_relationships"."merge_strategy" IS 'Strategy used for merging: ai_contextual, rule_based, manual, hybrid';



CREATE OR REPLACE VIEW "public"."extraction_segment_comparison" WITH ("security_invoker"='true') AS
 SELECT "orig"."extraction_id",
    "orig"."segment_code",
    "orig"."segment_value" AS "original_value",
    "edit"."segment_value" AS "edited_value",
    "orig"."brevity_level" AS "original_brevity",
    "edit"."brevity_level" AS "edited_brevity",
    "orig"."terminology_style" AS "original_terminology",
    "edit"."terminology_style" AS "edited_terminology",
    "orig"."created_at" AS "original_created_at",
    "edit"."created_at" AS "edited_created_at",
    "edit"."updated_at" AS "last_edited_at",
        CASE
            WHEN ("edit"."segment_value" IS NULL) THEN 'deleted'::"text"
            WHEN ("edit"."segment_value" IS NOT NULL) THEN 'edited'::"text"
            ELSE 'original'::"text"
        END AS "edit_status"
   FROM ("public"."extraction_segments" "orig"
     LEFT JOIN "public"."extraction_segments" "edit" ON ((("orig"."extraction_id" = "edit"."extraction_id") AND (("orig"."segment_code")::"text" = ("edit"."segment_code")::"text") AND (("edit"."version_type")::"text" = 'edited'::"text"))))
  WHERE (("orig"."version_type")::"text" = 'original'::"text");


ALTER VIEW "public"."extraction_segment_comparison" OWNER TO "postgres";


COMMENT ON VIEW "public"."extraction_segment_comparison" IS 'Side-by-side comparison of original vs edited segments.
edit_status: "original" (no edit), "edited" (modified), "deleted" (edited but NULL).';



CREATE TABLE IF NOT EXISTS "public"."extraction_translations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "target_language" character varying(20) NOT NULL,
    "translated_extraction_json" "jsonb" NOT NULL,
    "edited_translated_json" "jsonb",
    "translation_edit_count" integer DEFAULT 0,
    "last_translation_edited_at" timestamp with time zone,
    "last_translation_edited_by" "uuid",
    "translation_edited_by_type" character varying(10),
    "translation_started" boolean DEFAULT false,
    "translation_completed" boolean DEFAULT false,
    "translation_failed" boolean DEFAULT false,
    "translation_error" "text",
    "translation_time_seconds" numeric(10,2),
    "model_used" character varying(50),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."extraction_translations" OWNER TO "postgres";


COMMENT ON TABLE "public"."extraction_translations" IS 'Stores Indic language translations of medical extractions with independent edit tracking';



CREATE TABLE IF NOT EXISTS "public"."followup_tracking" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "patient_id" "uuid" NOT NULL,
    "doctor_id" "uuid",
    "hospital_id" "uuid",
    "consultation_date" "date" NOT NULL,
    "consultation_type_id" "uuid",
    "expected_followup_date" "date",
    "followup_window_start" "date",
    "followup_window_end" "date",
    "followup_window_days" integer DEFAULT 7,
    "followup_source" character varying(50) DEFAULT 'FOLLOW_UP_segment'::character varying,
    "followup_text" "text",
    "parsed_duration_days" integer,
    "status" character varying(20) DEFAULT 'PENDING'::character varying,
    "return_extraction_id" "uuid",
    "return_date" "date",
    "contacted_at" timestamp with time zone,
    "contacted_by_user_id" "uuid",
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "followup_tracking_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['PENDING'::character varying, 'RETURNED'::character varying, 'MISSED'::character varying, 'RESCHEDULED'::character varying, 'CANCELLED'::character varying, 'NO_FOLLOWUP'::character varying])::"text"[])))
);


ALTER TABLE "public"."followup_tracking" OWNER TO "postgres";


COMMENT ON TABLE "public"."followup_tracking" IS 'Tracks expected patient follow-up dates and detects missed follow-ups for dashboard alerts';



COMMENT ON COLUMN "public"."followup_tracking"."expected_followup_date" IS 'Calculated date when patient should return (consultation_date + parsed_duration_days)';



COMMENT ON COLUMN "public"."followup_tracking"."followup_window_days" IS 'Grace period in days - patient is considered on-time if they return within this window';



COMMENT ON COLUMN "public"."followup_tracking"."parsed_duration_days" IS 'Duration parsed from followup_text (e.g., "2 weeks" = 14, "1 month" = 30, "5 days" = 5)';



COMMENT ON COLUMN "public"."followup_tracking"."status" IS 'Follow-up status: PENDING (waiting), RETURNED (patient came back), MISSED (window passed), RESCHEDULED (new date set), CANCELLED (no longer needed), NO_FOLLOWUP (no follow-up specified)';



CREATE TABLE IF NOT EXISTS "public"."guideline_ingestion_jobs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "file_name" "text" NOT NULL,
    "file_path" "text",
    "source_name" "text" NOT NULL,
    "source_organization" "text",
    "specialty" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text",
    "error_message" "text",
    "total_chunks" integer DEFAULT 0,
    "processed_chunks" integer DEFAULT 0,
    "embedded_chunks" integer DEFAULT 0,
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "guideline_ingestion_jobs_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'processing'::"text", 'completed'::"text", 'failed'::"text"])))
);


ALTER TABLE "public"."guideline_ingestion_jobs" OWNER TO "postgres";


COMMENT ON TABLE "public"."guideline_ingestion_jobs" IS 'Track clinical guideline PDF ingestion jobs';



CREATE TABLE IF NOT EXISTS "public"."hospital_ehr" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "ehr_integration_type" character varying(50) NOT NULL,
    "api_url" "text",
    "api_key" "text",
    "is_enabled" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "ehr_type_id" "uuid",
    "is_default" boolean DEFAULT false
);


ALTER TABLE "public"."hospital_ehr" OWNER TO "postgres";


COMMENT ON TABLE "public"."hospital_ehr" IS 'Junction table for hospital EHR integrations. Each hospital can have multiple EHR systems configured.';



COMMENT ON COLUMN "public"."hospital_ehr"."ehr_integration_type" IS 'EHR system identifier: aosta, raster, epic, etc.';



COMMENT ON COLUMN "public"."hospital_ehr"."api_url" IS 'EHR API endpoint URL. If NULL, integration is disabled.';



COMMENT ON COLUMN "public"."hospital_ehr"."api_key" IS 'Optional API key for authentication. If NULL, sends without auth.';



COMMENT ON COLUMN "public"."hospital_ehr"."ehr_type_id" IS 'Foreign key to ehr_types. Replaces ehr_integration_type string.';



COMMENT ON COLUMN "public"."hospital_ehr"."is_default" IS 'If true, new doctors in this hospital are auto-assigned this EHR type.';



CREATE TABLE IF NOT EXISTS "public"."hospital_intervention_pricing" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "intervention_type" character varying(50) NOT NULL,
    "service_name" character varying(100) NOT NULL,
    "revenue_estimate" numeric(10,2) NOT NULL,
    "currency" character varying(3) DEFAULT 'INR'::character varying,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."hospital_intervention_pricing" OWNER TO "postgres";


COMMENT ON TABLE "public"."hospital_intervention_pricing" IS 'Hospital-specific pricing catalog for revenue interventions';



COMMENT ON COLUMN "public"."hospital_intervention_pricing"."intervention_type" IS 'Intervention type code: NUTRITIONAL_REFERRAL, PHYSIOTHERAPY_REFERRAL, etc.';



COMMENT ON COLUMN "public"."hospital_intervention_pricing"."service_name" IS 'Human-readable service name for display';



COMMENT ON COLUMN "public"."hospital_intervention_pricing"."revenue_estimate" IS 'Estimated revenue in hospital currency';



CREATE TABLE IF NOT EXISTS "public"."hospital_investigation_lists" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "investigation_name" character varying(255) NOT NULL,
    "common_names" "text"[],
    "investigation_type" character varying(50) NOT NULL,
    "category" character varying(100),
    "normal_range" "text",
    "loinc_code" character varying(50),
    "cpt_code" character varying(50),
    "normalized_name" character varying(255) NOT NULL,
    "search_tokens" "text"[],
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "external_id" character varying(100),
    "unit_price" numeric(10,2) DEFAULT NULL::numeric,
    CONSTRAINT "valid_hospital_investigation_type" CHECK ((("investigation_type")::"text" = ANY (ARRAY[('laboratory'::character varying)::"text", ('imaging'::character varying)::"text", ('other'::character varying)::"text"])))
);


ALTER TABLE "public"."hospital_investigation_lists" OWNER TO "postgres";


COMMENT ON COLUMN "public"."hospital_investigation_lists"."external_id" IS 'External system ID (e.g., TestID from EHR systems)';



CREATE TABLE IF NOT EXISTS "public"."hospital_medicine_lists" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "medicine_name" character varying(255) NOT NULL,
    "common_names" "text"[],
    "category" character varying(100),
    "typical_dosage" character varying(255),
    "form" character varying(50),
    "snomed_code" character varying(50),
    "formulary_name" character varying(255),
    "medicine_type" character varying(20),
    "normalized_name" character varying(255) NOT NULL,
    "search_tokens" "text"[],
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "quantity" integer,
    "external_id" character varying(100),
    "unit_price" numeric(10,2) DEFAULT NULL::numeric,
    "product_code" "text",
    CONSTRAINT "valid_hospital_medicine_type" CHECK ((("medicine_type" IS NULL) OR (("medicine_type")::"text" = ANY (ARRAY[('generic'::character varying)::"text", ('branded'::character varying)::"text"]))))
);


ALTER TABLE "public"."hospital_medicine_lists" OWNER TO "postgres";


COMMENT ON TABLE "public"."hospital_medicine_lists" IS 'Hospital-level shared medicine lists';



COMMENT ON COLUMN "public"."hospital_medicine_lists"."quantity" IS 'Available quantity/stock of the medicine';



COMMENT ON COLUMN "public"."hospital_medicine_lists"."external_id" IS 'External system ID (e.g., BrandID from EHR systems)';



COMMENT ON COLUMN "public"."hospital_medicine_lists"."product_code" IS 'Product code from EHR system (e.g., Raster productCode). Populated from CSV upload.';



CREATE TABLE IF NOT EXISTS "public"."hospitals" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_name" character varying(255) NOT NULL,
    "hospital_code" character varying(50),
    "address" "text",
    "city" character varying(100),
    "state" character varying(100),
    "country" character varying(100) DEFAULT 'India'::character varying,
    "phone" character varying(50),
    "email" character varying(255),
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "default_template_id" "uuid",
    "use_ffmpeg_stitching" boolean DEFAULT false,
    "audio_quality_block_threshold" "text" DEFAULT 'poor'::"text",
    "min_transcript_length" integer DEFAULT 20,
    "max_silence_ratio" numeric(3,2) DEFAULT 0.90,
    "enable_realtime_subscription" boolean DEFAULT false,
    "enable_audio_validation" boolean DEFAULT true,
    "min_snr_db" double precision DEFAULT 10.0,
    "min_rms_db" double precision DEFAULT '-57.0'::numeric,
    "min_speech_ratio" double precision DEFAULT 0.0,
    "op_registration_fee" numeric(10,2) DEFAULT NULL::numeric,
    "ip_admission_fee" numeric(10,2) DEFAULT NULL::numeric,
    "feature_flags" "jsonb" DEFAULT '{"ocr": false, "iris": false, "merge": true, "upload": true, "billing": false, "care_plan": true, "doctor_qa": true, "nudge_plan": false, "patient_qa": true, "edit_record": true, "interventions": true, "triage_support": false, "edit_prescription": true, "edit_investigation": true, "patient_registration": true, "template_configuration": true}'::"jsonb" NOT NULL,
    "default_translation_language" character varying(20) DEFAULT NULL::character varying,
    "silence_thresh_dbfs" double precision DEFAULT '-60'::integer,
    "min_silence_len_ms" integer DEFAULT 5000,
    "silence_padding_ms" integer DEFAULT 200
);


ALTER TABLE "public"."hospitals" OWNER TO "postgres";


COMMENT ON COLUMN "public"."hospitals"."default_template_id" IS 'Default template for all doctors in this hospital';



COMMENT ON COLUMN "public"."hospitals"."use_ffmpeg_stitching" IS 'When true, use FFmpeg for audio stitching instead of simple concatenation. Produces better quality but adds ~1-2s processing time.';



COMMENT ON COLUMN "public"."hospitals"."audio_quality_block_threshold" IS 'Block processing if audio quality is at or below this level. Options: poor, fair, none (never block). Default: poor.';



COMMENT ON COLUMN "public"."hospitals"."min_transcript_length" IS 'Minimum transcript length (characters) to proceed with extraction. Blocks if transcript is shorter. Default: 20.';



COMMENT ON COLUMN "public"."hospitals"."max_silence_ratio" IS 'Block if silence ratio exceeds this threshold (0.0 to 1.0). Default: 0.90 (90% silence).';



COMMENT ON COLUMN "public"."hospitals"."default_translation_language" IS 'Default translation language for all doctors in this hospital. Doctor setting overrides this.';



COMMENT ON COLUMN "public"."hospitals"."silence_thresh_dbfs" IS 'Silence removal: volume threshold below which audio is considered silence (dBFS). More negative = more lenient. Default: -57';



COMMENT ON COLUMN "public"."hospitals"."min_silence_len_ms" IS 'Silence removal: minimum continuous silence duration (ms) to remove. Default: 5000 (5s)';



COMMENT ON COLUMN "public"."hospitals"."silence_padding_ms" IS 'Silence removal: padding to keep around each speech segment (ms). Default: 200';



CREATE TABLE IF NOT EXISTS "public"."intervention_definitions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "intervention_code" "text" NOT NULL,
    "intervention_name" "text" NOT NULL,
    "description" "text",
    "priority_level" "text" NOT NULL,
    "priority_score" integer NOT NULL,
    "category" "text" DEFAULT 'general'::"text" NOT NULL,
    "trigger_conditions" "jsonb" DEFAULT '{}'::"jsonb",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "intervention_definitions_category_check" CHECK (("category" = ANY (ARRAY['OP_TO_IP'::"text", 'FOLLOWUP_DUE'::"text", 'RX_REFILL'::"text", 'DIAGNOSTICS_DUE'::"text", 'ALLIED_HEALTH'::"text", 'RETENTION_RISK'::"text", 'QUALITY_RISK'::"text"]))),
    CONSTRAINT "intervention_definitions_priority_level_check" CHECK (("priority_level" = ANY (ARRAY['CRITICAL'::"text", 'HIGH'::"text", 'MEDIUM'::"text", 'LOW'::"text"]))),
    CONSTRAINT "intervention_definitions_priority_score_check" CHECK ((("priority_score" >= 0) AND ("priority_score" <= 100)))
);


ALTER TABLE "public"."intervention_definitions" OWNER TO "postgres";


COMMENT ON TABLE "public"."intervention_definitions" IS 'Master list of interventions - REVENUE (16), RETENTION (8), QUALITY (10) = 34 total active types';



COMMENT ON COLUMN "public"."intervention_definitions"."category" IS 'Dashboard category: OP_TO_IP (surgical), FOLLOWUP_DUE (return visits), RX_REFILL (prescriptions), DIAGNOSTICS_DUE (tests), ALLIED_HEALTH (referrals), RETENTION_RISK (dropoff prevention), QUALITY_RISK (safety alerts)';



CREATE TABLE IF NOT EXISTS "public"."medical_extractions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "session_id" "uuid",
    "consultation_type_id" "uuid" NOT NULL,
    "doctor_id" "uuid",
    "patient_id" "uuid",
    "extraction_mode" character varying(20) NOT NULL,
    "model_used" character varying(50) NOT NULL,
    "segment_count" integer NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "original_extraction_json" "jsonb",
    "edited_extraction_json" "jsonb",
    "edit_count" integer DEFAULT 0,
    "last_edited_at" timestamp with time zone,
    "last_edited_by" "uuid",
    "emotion_extraction_started" boolean DEFAULT false,
    "emotion_extraction_completed" boolean DEFAULT false,
    "emotion_extraction_failed" boolean DEFAULT false,
    "emotion_extraction_error" "text",
    "emotion_extraction_started_at" timestamp with time zone,
    "emotion_extraction_completed_at" timestamp with time zone,
    "submission_id" "uuid",
    "transcript_text" "text",
    "stitching_time_seconds" numeric(10,2),
    "transcription_time_seconds" numeric(10,2),
    "extraction_time_seconds" numeric(10,2),
    "total_processing_time_seconds" numeric(10,2),
    "is_merged" boolean DEFAULT false,
    "merge_metadata" "jsonb",
    "merge_prompt" "text",
    "merged_into_extraction_id" "uuid",
    "audio_emotion_extraction_completed" boolean DEFAULT false,
    "congruence_analysis_completed" boolean DEFAULT false,
    "audio_emotion_extraction_started" boolean DEFAULT false,
    "audio_emotion_extraction_failed" boolean DEFAULT false,
    "audio_emotion_extraction_error" "text",
    "audio_emotion_extraction_started_at" timestamp with time zone,
    "audio_emotion_extraction_completed_at" timestamp with time zone,
    "congruence_analysis_started" boolean DEFAULT false,
    "congruence_analysis_failed" boolean DEFAULT false,
    "congruence_analysis_error" "text",
    "congruence_analysis_started_at" timestamp with time zone,
    "congruence_analysis_completed_at" timestamp with time zone,
    "edited_by_type" character varying(10),
    "recording_metadata_json" "jsonb" DEFAULT '{}'::"jsonb",
    "audio_emotion_extraction_fallback_used" boolean DEFAULT false,
    "ehr_payload_json" "jsonb",
    "is_continuation" boolean DEFAULT false,
    "parent_extraction_ids" "uuid"[] DEFAULT '{}'::"uuid"[],
    CONSTRAINT "medical_extractions_edited_by_type_check" CHECK ((("edited_by_type")::"text" = ANY ((ARRAY['doctor'::character varying, 'nurse'::character varying])::"text"[]))),
    CONSTRAINT "medical_extractions_extraction_mode_check" CHECK ((("extraction_mode")::"text" = ANY ((ARRAY['core'::character varying, 'additional'::character varying, 'full'::character varying])::"text"[])))
);


ALTER TABLE "public"."medical_extractions" OWNER TO "postgres";


COMMENT ON COLUMN "public"."medical_extractions"."original_extraction_json" IS 'Original AI-generated extraction (JSON). This is the single source of truth for AI extraction results. Edited version stored in edited_extraction_json.';



COMMENT ON COLUMN "public"."medical_extractions"."edited_extraction_json" IS 'Latest edited version by doctor (NULL if never edited)';



COMMENT ON COLUMN "public"."medical_extractions"."edit_count" IS 'Number of times this extraction has been edited';



COMMENT ON COLUMN "public"."medical_extractions"."last_edited_at" IS 'Timestamp of last edit';



COMMENT ON COLUMN "public"."medical_extractions"."last_edited_by" IS 'UUID of the user who last edited. Check edited_by_type to determine if this is a doctor_id or nurse_id.';



COMMENT ON COLUMN "public"."medical_extractions"."emotion_extraction_started" IS 'Background task started flag';



COMMENT ON COLUMN "public"."medical_extractions"."emotion_extraction_completed" IS 'Background task completed successfully flag';



COMMENT ON COLUMN "public"."medical_extractions"."emotion_extraction_failed" IS 'Background task failed flag';



COMMENT ON COLUMN "public"."medical_extractions"."emotion_extraction_error" IS 'Error message if emotion extraction failed';



COMMENT ON COLUMN "public"."medical_extractions"."emotion_extraction_started_at" IS 'Timestamp when emotion extraction started';



COMMENT ON COLUMN "public"."medical_extractions"."emotion_extraction_completed_at" IS 'Timestamp when emotion extraction completed';



COMMENT ON COLUMN "public"."medical_extractions"."submission_id" IS 'Reference to processing_jobs.submission_id (the job that created this extraction). NULL for extractions not from recording workflow (e.g., manual uploads, API calls). FK with ON DELETE SET NULL to preserve extractions when jobs are cleaned up.';



COMMENT ON COLUMN "public"."medical_extractions"."transcript_text" IS 'Transcript text for this extraction. Migrated from processing_jobs.transcript (primary) and recording_sessions.transcript_text (fallback).';



COMMENT ON COLUMN "public"."medical_extractions"."stitching_time_seconds" IS 'Time taken to stitch audio chunks (seconds). NULL for RecordTab (no stitching).';



COMMENT ON COLUMN "public"."medical_extractions"."transcription_time_seconds" IS 'Time taken for AI transcription (seconds).';



COMMENT ON COLUMN "public"."medical_extractions"."extraction_time_seconds" IS 'Time taken for medical insights extraction (seconds).';



COMMENT ON COLUMN "public"."medical_extractions"."total_processing_time_seconds" IS 'Total processing time from start to completion (seconds).';



COMMENT ON COLUMN "public"."medical_extractions"."is_merged" IS 'TRUE if this extraction is a result of merging multiple extractions';



COMMENT ON COLUMN "public"."medical_extractions"."merge_metadata" IS 'JSON metadata about the merge operation (source count, conflicts, notes, etc.)';



COMMENT ON COLUMN "public"."medical_extractions"."merge_prompt" IS 'AI prompt used for contextual merge (for audit and debugging)';



COMMENT ON COLUMN "public"."medical_extractions"."merged_into_extraction_id" IS 'Reference to merged extraction if this was merged into another';



COMMENT ON COLUMN "public"."medical_extractions"."edited_by_type" IS 'Type of user who edited: doctor or nurse';



COMMENT ON COLUMN "public"."medical_extractions"."recording_metadata_json" IS 'Copy of recording metadata for easy retrieval via status API';



COMMENT ON COLUMN "public"."medical_extractions"."audio_emotion_extraction_fallback_used" IS 'True when audio emotion extraction completed via fallback (empty emotions due to JSON parse failure)';



COMMENT ON COLUMN "public"."medical_extractions"."ehr_payload_json" IS 'Formatted EHR payload (lookup-normalized for Neopaed, Aosta/Raster-formatted). Updated on creation, edit, and EHR send.';



COMMENT ON COLUMN "public"."medical_extractions"."is_continuation" IS 'Whether this extraction is a continuation of a prior consultation in the same visit';



COMMENT ON COLUMN "public"."medical_extractions"."parent_extraction_ids" IS 'Array of extraction IDs from prior recordings in the same visit chain';



CREATE TABLE IF NOT EXISTS "public"."patient_interventions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "intervention_id" "uuid" NOT NULL,
    "intervention_code" "text" NOT NULL,
    "priority_level" "text" NOT NULL,
    "priority_score" integer NOT NULL,
    "trigger_reason" "text" NOT NULL,
    "analysis_mode" "text" NOT NULL,
    "recommendation_rank" integer,
    "is_top_recommendation" boolean DEFAULT false,
    "rationale_sources" "jsonb" DEFAULT '[]'::"jsonb",
    "status" "text" DEFAULT 'recommended'::"text",
    "status_updated_at" timestamp with time zone,
    "status_updated_by" "text",
    "status_notes" "text",
    "outcome" "text",
    "outcome_notes" "text",
    "outcome_recorded_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "intervention_category" character varying(20),
    "intervention_sub_type" character varying(30),
    "consultation_insights_id" "uuid",
    "revenue_estimate" numeric(10,2),
    "action" "text",
    "linked_assessment_type" character varying(50),
    "linked_assessment_id" "uuid",
    "take_up_likelihood" smallint,
    CONSTRAINT "patient_interventions_analysis_mode_check" CHECK (("analysis_mode" = ANY (ARRAY['text_only'::"text", 'audio_only'::"text", 'combined'::"text"]))),
    CONSTRAINT "patient_interventions_intervention_category_check" CHECK ((("intervention_category")::"text" = ANY ((ARRAY['OP_TO_IP'::character varying, 'FOLLOWUP_DUE'::character varying, 'RX_REFILL'::character varying, 'DIAGNOSTICS_DUE'::character varying, 'ALLIED_HEALTH'::character varying, 'RETENTION_RISK'::character varying, 'QUALITY_RISK'::character varying])::"text"[]))),
    CONSTRAINT "patient_interventions_outcome_check" CHECK (("outcome" = ANY (ARRAY['effective'::"text", 'partially_effective'::"text", 'not_effective'::"text", 'unknown'::"text"]))),
    CONSTRAINT "patient_interventions_status_check" CHECK (("status" = ANY (ARRAY['recommended'::"text", 'acknowledged'::"text", 'in_progress'::"text", 'completed'::"text", 'declined'::"text", 'not_applicable'::"text"]))),
    CONSTRAINT "patient_interventions_take_up_likelihood_check" CHECK ((("take_up_likelihood" >= 0) AND ("take_up_likelihood" <= 100)))
);


ALTER TABLE "public"."patient_interventions" OWNER TO "postgres";


COMMENT ON COLUMN "public"."patient_interventions"."intervention_category" IS 'Dashboard category: OP_TO_IP (surgical), FOLLOWUP_DUE (return visits), RX_REFILL (prescriptions), DIAGNOSTICS_DUE (tests), ALLIED_HEALTH (referrals), RETENTION_RISK (dropoff prevention), QUALITY_RISK (safety alerts)';



COMMENT ON COLUMN "public"."patient_interventions"."intervention_sub_type" IS 'Sub-category: allied_health, clinical_upsell, diagnostics_rx, medication_safety, documentation, followup, retention';



COMMENT ON COLUMN "public"."patient_interventions"."consultation_insights_id" IS 'FK to consultation_insights that generated this intervention';



COMMENT ON COLUMN "public"."patient_interventions"."revenue_estimate" IS 'Estimated revenue for REVENUE category interventions (from hospital pricing)';



COMMENT ON COLUMN "public"."patient_interventions"."action" IS 'Simple action statement: what should be done';



COMMENT ON COLUMN "public"."patient_interventions"."linked_assessment_type" IS 'Assessment type that triggered: allied_health_needs, clinical_severity, other_clinical_needs, patient_dropoff_risk, care_quality_risk';



COMMENT ON COLUMN "public"."patient_interventions"."linked_assessment_id" IS 'UUID of the assessment record that triggered this intervention';



COMMENT ON COLUMN "public"."patient_interventions"."take_up_likelihood" IS 'Predicted likelihood (0-100) that patient will accept/follow this intervention. Calculated from clinical severity, anxiety (post-level + trajectory), financial concerns, compliance likelihood, and fear/distress emotions.';



CREATE TABLE IF NOT EXISTS "public"."recording_sessions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "correlation_id" "uuid" NOT NULL,
    "transcription_engine" character varying(50) DEFAULT 'gemini'::character varying NOT NULL,
    "transcription_model" character varying(100) DEFAULT 'gemini-2.5-pro'::character varying NOT NULL,
    "doctor_id" "uuid",
    "patient_id" "uuid",
    "patient_identifier" character varying(100) NOT NULL,
    "status" character varying(20) DEFAULT 'RECORDING'::character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "submitted_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "chunk_duration_seconds" integer DEFAULT 10,
    "total_chunks" integer DEFAULT 0,
    "total_duration_seconds" numeric(10,2),
    "full_audio_data" "text",
    "full_audio_mime_type" character varying(100),
    "full_audio_size_bytes" integer,
    "full_audio_url" "text",
    "chunks_deleted" boolean DEFAULT false,
    "chunks_deleted_at" timestamp with time zone,
    "consultation_type_id" "uuid",
    "extraction_model" "text" DEFAULT 'gemini-2.5-pro'::"text",
    "template_name" "text",
    "processing_mode" character varying(50),
    "extraction_mode" character varying(20),
    "transcript_text" "text",
    "template_code" character varying(100),
    "session_context_json" "jsonb" DEFAULT '{}'::"jsonb",
    "nurse_id" "uuid",
    "audio_quality_json" "jsonb",
    "recording_metadata_json" "jsonb" DEFAULT '{}'::"jsonb",
    "api_client_id" "uuid",
    "validation_status" character varying(20) DEFAULT 'completed'::character varying,
    "error_message" "text",
    "processed_audio_data" "text",
    "has_processed_audio" boolean DEFAULT false,
    CONSTRAINT "check_extraction_mode" CHECK (((("extraction_mode")::"text" = ANY ((ARRAY['core'::character varying, 'additional'::character varying, 'full'::character varying])::"text"[])) OR ("extraction_mode" IS NULL))),
    CONSTRAINT "check_processing_mode" CHECK ((("processing_mode")::"text" = ANY ((ARRAY['fast'::character varying, 'default'::character varying, 'thorough'::character varying, 'ultra'::character varying, 'ultra_fast'::character varying])::"text"[]))),
    CONSTRAINT "recording_sessions_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['RECORDING'::character varying, 'SUBMITTED'::character varying, 'PROCESSING'::character varying, 'COMPLETED'::character varying, 'CANCELLED'::character varying, 'ERROR'::character varying, 'validation_failed'::character varying, 'CHUNK_TIMEOUT'::character varying])::"text"[])))
);


ALTER TABLE "public"."recording_sessions" OWNER TO "postgres";


COMMENT ON TABLE "public"."recording_sessions" IS 'Recording sessions table. Status values: pending, processing, completed, failed, validation_failed.';



COMMENT ON COLUMN "public"."recording_sessions"."doctor_id" IS 'Doctor UUID who performed the recording';



COMMENT ON COLUMN "public"."recording_sessions"."consultation_type_id" IS 'Actual consultation type used for extraction (derived from activated template). Set during processing.';



COMMENT ON COLUMN "public"."recording_sessions"."extraction_model" IS 'Gemini model used for medical insights extraction (gemini-2.5-pro or gemini-2.5-flash)';



COMMENT ON COLUMN "public"."recording_sessions"."template_name" IS 'Display name of the template (human readable)';



COMMENT ON COLUMN "public"."recording_sessions"."processing_mode" IS 'Processing mode code: fast, default, thorough, ultra, ultra_fast';



COMMENT ON COLUMN "public"."recording_sessions"."extraction_mode" IS 'Extraction mode: core, additional, full, or NULL (for TRANSCRIPT_ONLY)';



COMMENT ON COLUMN "public"."recording_sessions"."transcript_text" IS 'Full transcript text from recording session (live, chunked, or file upload). Auto-saved during extraction via /extract endpoint.';



COMMENT ON COLUMN "public"."recording_sessions"."nurse_id" IS 'Nurse who initiated/managed the recording session (if any)';



COMMENT ON COLUMN "public"."recording_sessions"."audio_quality_json" IS 'Audio quality analysis result containing: overall_quality (good/fair/poor), is_acceptable (bool), issues[] (list of detected problems), metrics{} (snr_db, rms_db, peak_db, clipping_ratio, silence_ratio, speech_detected, duration_seconds), and summary_message (human-readable)';



COMMENT ON COLUMN "public"."recording_sessions"."recording_metadata_json" IS 'Metadata passed during recording start (patient info, doctor info, custom fields)';



COMMENT ON COLUMN "public"."recording_sessions"."api_client_id" IS 'Reference to the API client that started this recording session. NULL for admin users.';



COMMENT ON COLUMN "public"."recording_sessions"."error_message" IS 'Error message when session fails (e.g., audio quality validation failure)';



CREATE OR REPLACE VIEW "public"."intervention_analytics" WITH ("security_invoker"='true') AS
 SELECT "pi"."id",
    "pi"."extraction_id",
    "pi"."intervention_code",
    "pi"."intervention_id",
    "idef"."intervention_name",
    "idef"."category" AS "intervention_category",
    "pi"."priority_level",
    "pi"."priority_score",
    "pi"."trigger_reason",
    "pi"."analysis_mode",
    "pi"."recommendation_rank",
    "pi"."is_top_recommendation",
    "pi"."status",
    "pi"."outcome",
    "pi"."created_at" AS "recommended_at",
    "pi"."status_updated_at",
    "me"."session_id",
    "me"."doctor_id",
    "me"."consultation_type_id",
    "me"."created_at" AS "extraction_created_at",
    "rs"."patient_id",
    "rs"."template_code",
    "d"."full_name" AS "doctor_name",
    "d"."specialization" AS "doctor_specialty",
    "ct"."type_code" AS "consultation_type_code",
    "ct"."type_name" AS "consultation_type_name"
   FROM ((((("public"."patient_interventions" "pi"
     JOIN "public"."intervention_definitions" "idef" ON (("pi"."intervention_id" = "idef"."id")))
     JOIN "public"."medical_extractions" "me" ON (("pi"."extraction_id" = "me"."id")))
     LEFT JOIN "public"."recording_sessions" "rs" ON (("me"."session_id" = "rs"."id")))
     LEFT JOIN "public"."doctors" "d" ON (("me"."doctor_id" = "d"."id")))
     LEFT JOIN "public"."consultation_types" "ct" ON (("me"."consultation_type_id" = "ct"."id")));


ALTER VIEW "public"."intervention_analytics" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."intervention_outcomes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "intervention_id" "uuid" NOT NULL,
    "status" character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    "generated_at" timestamp with time zone NOT NULL,
    "first_contact_at" timestamp with time zone,
    "status_updated_at" timestamp with time zone DEFAULT "now"(),
    "completed_at" timestamp with time zone,
    "expired_at" timestamp with time zone,
    "actual_revenue" numeric(12,2),
    "decline_reason" character varying(100),
    "notes" "text",
    "updated_by_user_id" "uuid",
    "updated_by_user_type" character varying(20),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "intervention_outcomes_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['PENDING'::character varying, 'CONTACTED'::character varying, 'ACCEPTED'::character varying, 'DECLINED'::character varying, 'COMPLETED'::character varying, 'EXPIRED'::character varying])::"text"[])))
);


ALTER TABLE "public"."intervention_outcomes" OWNER TO "postgres";


COMMENT ON TABLE "public"."intervention_outcomes" IS 'Tracks intervention lifecycle: status progression, time-to-action, and revenue capture for ROI measurement';



COMMENT ON COLUMN "public"."intervention_outcomes"."status" IS 'Intervention status: PENDING (not started), CONTACTED (staff reached out), ACCEPTED (patient agreed), DECLINED (patient refused), COMPLETED (action taken), EXPIRED (time limit passed)';



COMMENT ON COLUMN "public"."intervention_outcomes"."generated_at" IS 'When the intervention was generated (copied from patient_interventions.created_at for time-to-action calculations)';



COMMENT ON COLUMN "public"."intervention_outcomes"."first_contact_at" IS 'When staff first contacted the patient about this intervention (for time-to-contact metrics)';



COMMENT ON COLUMN "public"."intervention_outcomes"."actual_revenue" IS 'Actual revenue captured when intervention is COMPLETED (for ROI calculation)';



CREATE OR REPLACE VIEW "public"."intervention_summary_stats" WITH ("security_invoker"='true') AS
 SELECT "intervention_code",
    "intervention_name",
    "intervention_category",
    "priority_level",
    "count"(*) AS "total_recommendations",
    "count"(*) FILTER (WHERE "is_top_recommendation") AS "top_3_recommendations",
    "count"(*) FILTER (WHERE ("status" = 'completed'::"text")) AS "completed_count",
    "count"(*) FILTER (WHERE ("status" = 'declined'::"text")) AS "declined_count",
    "count"(*) FILTER (WHERE ("status" = 'in_progress'::"text")) AS "in_progress_count",
    "count"(*) FILTER (WHERE ("outcome" = 'effective'::"text")) AS "effective_count",
    "count"(*) FILTER (WHERE ("outcome" = 'partially_effective'::"text")) AS "partial_effective_count",
    "count"(*) FILTER (WHERE ("outcome" = 'not_effective'::"text")) AS "not_effective_count",
        CASE
            WHEN ("count"(*) FILTER (WHERE ("outcome" IS NOT NULL)) > 0) THEN "round"(((("count"(*) FILTER (WHERE ("outcome" = 'effective'::"text")))::numeric / ("count"(*) FILTER (WHERE ("outcome" IS NOT NULL)))::numeric) * (100)::numeric), 1)
            ELSE NULL::numeric
        END AS "effectiveness_rate_pct",
    "min"("recommended_at") AS "first_recommendation",
    "max"("recommended_at") AS "latest_recommendation"
   FROM "public"."intervention_analytics" "ia"
  GROUP BY "intervention_code", "intervention_name", "intervention_category", "priority_level"
  ORDER BY ("count"(*)) DESC;


ALTER VIEW "public"."intervention_summary_stats" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."investigation_list_uploads" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "doctor_id" "uuid",
    "hospital_id" "uuid",
    "filename" character varying(255) NOT NULL,
    "file_size_bytes" integer,
    "row_count" integer,
    "successful_imports" integer,
    "failed_imports" integer,
    "error_details" "jsonb",
    "status" character varying(20) DEFAULT 'pending'::character varying,
    "uploaded_at" timestamp with time zone DEFAULT "now"(),
    "processed_at" timestamp with time zone,
    CONSTRAINT "check_upload_owner" CHECK (((("doctor_id" IS NOT NULL) AND ("hospital_id" IS NULL)) OR (("doctor_id" IS NULL) AND ("hospital_id" IS NOT NULL))))
);


ALTER TABLE "public"."investigation_list_uploads" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."investigation_match_log" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid",
    "submission_id" character varying(100),
    "doctor_id" "uuid",
    "original_investigation_name" character varying(255) NOT NULL,
    "investigation_type" character varying(50),
    "matched_investigation_id" "uuid",
    "matched_hospital_investigation_id" "uuid",
    "matched_investigation_name" character varying(255),
    "match_confidence" numeric(5,4),
    "match_method" character varying(50),
    "match_source" character varying(20),
    "feedback_status" character varying(20),
    "feedback_at" timestamp with time zone,
    "correct_investigation_id" "uuid",
    "correct_investigation_name" character varying(255),
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."investigation_match_log" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."llm_usage_log" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "session_id" "uuid",
    "extraction_id" "uuid",
    "doctor_id" "uuid",
    "call_type" character varying(50) NOT NULL,
    "call_subtype" character varying(100),
    "consultation_type_code" character varying(50),
    "template_code" character varying(100),
    "model" character varying(100) NOT NULL,
    "prompt_token_count" integer,
    "cached_content_token_count" integer,
    "candidates_token_count" integer,
    "total_token_count" integer,
    "system_prompt_tokens" integer,
    "user_prompt_tokens" integer,
    "schema_tokens" integer,
    "audio_duration_seconds" numeric(10,2),
    "audio_size_bytes" integer,
    "input_cost_usd" numeric(10,6),
    "output_cost_usd" numeric(10,6),
    "cache_savings_usd" numeric(10,6),
    "total_cost_usd" numeric(10,6),
    "api_duration_seconds" numeric(10,3),
    "cache_hit" boolean DEFAULT false,
    "cache_hit_ratio" numeric(5,2),
    "request_timestamp" timestamp with time zone DEFAULT "now"(),
    "response_status" character varying(20) DEFAULT 'success'::character varying,
    "error_message" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "api_client_id" "uuid",
    "thoughts_token_count" integer
);


ALTER TABLE "public"."llm_usage_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."llm_usage_log" IS 'Tracks token usage and cost for all Gemini API calls (transcription, extraction, emotion analysis, merge)';



COMMENT ON COLUMN "public"."llm_usage_log"."call_type" IS 'Type of LLM call: transcription, extraction, emotion, merge, generation';



COMMENT ON COLUMN "public"."llm_usage_log"."call_subtype" IS 'Specific function: neo_daily, ophthal_discharge_part1, dynamic_core, etc.';



COMMENT ON COLUMN "public"."llm_usage_log"."prompt_token_count" IS 'Total input tokens from usage_metadata.prompt_token_count';



COMMENT ON COLUMN "public"."llm_usage_log"."cached_content_token_count" IS 'Tokens from cache (usage_metadata.cached_content_token_count)';



COMMENT ON COLUMN "public"."llm_usage_log"."candidates_token_count" IS 'Output tokens from usage_metadata.candidates_token_count';



COMMENT ON COLUMN "public"."llm_usage_log"."total_token_count" IS 'Total tokens - may exceed sum for Gemini 2.5 (includes thinking)';



COMMENT ON COLUMN "public"."llm_usage_log"."cache_savings_usd" IS 'Estimated savings from cache (cached tokens charged at 25% rate)';



COMMENT ON COLUMN "public"."llm_usage_log"."cache_hit" IS 'TRUE if cached_content_token_count > 0';



COMMENT ON COLUMN "public"."llm_usage_log"."cache_hit_ratio" IS 'Percentage: (cached_content_token_count / prompt_token_count) * 100';



COMMENT ON COLUMN "public"."llm_usage_log"."api_client_id" IS 'Reference to the API client that made this request. NULL for admin users.';



COMMENT ON COLUMN "public"."llm_usage_log"."thoughts_token_count" IS 'Gemini thinking/reasoning tokens (separate from candidates_token_count)';



CREATE TABLE IF NOT EXISTS "public"."medicine_list_uploads" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "filename" character varying(255) NOT NULL,
    "file_size_bytes" integer,
    "row_count" integer,
    "successful_imports" integer,
    "failed_imports" integer,
    "error_details" "jsonb",
    "status" character varying(20) DEFAULT 'pending'::character varying,
    "uploaded_at" timestamp with time zone DEFAULT "now"(),
    "processed_at" timestamp with time zone
);


ALTER TABLE "public"."medicine_list_uploads" OWNER TO "postgres";


COMMENT ON TABLE "public"."medicine_list_uploads" IS 'Tracks CSV uploads for medicine lists';



CREATE TABLE IF NOT EXISTS "public"."medicine_match_log" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid",
    "submission_id" character varying(100),
    "doctor_id" "uuid",
    "original_medicine_name" character varying(255) NOT NULL,
    "matched_medicine_id" "uuid",
    "matched_medicine_name" character varying(255),
    "match_confidence" numeric(5,4),
    "match_method" character varying(50),
    "match_source" character varying(20),
    "diagnosis_context" "text",
    "feedback_status" character varying(20),
    "feedback_at" timestamp with time zone,
    "correct_medicine_id" "uuid",
    "correct_medicine_name" character varying(255),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "matched_hospital_medicine_id" "uuid"
);


ALTER TABLE "public"."medicine_match_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."medicine_match_log" IS 'Audit trail for medicine matching with feedback mechanism';



COMMENT ON COLUMN "public"."medicine_match_log"."matched_medicine_id" IS 'Reference to doctor_medicines when match_source is doctor_list';



COMMENT ON COLUMN "public"."medicine_match_log"."match_method" IS 'exact, fuzzy, common_name, feedback, no_match';



COMMENT ON COLUMN "public"."medicine_match_log"."match_source" IS 'doctor_list, hospital_list, feedback_history';



COMMENT ON COLUMN "public"."medicine_match_log"."feedback_status" IS 'NULL=pending, agreed, disagreed';



COMMENT ON COLUMN "public"."medicine_match_log"."matched_hospital_medicine_id" IS 'Reference to hospital_medicine_lists when match_source is hospital_list';



CREATE TABLE IF NOT EXISTS "public"."models_master" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "model_id" "text" NOT NULL,
    "display_name" "text" NOT NULL,
    "provider" "text" DEFAULT 'gemini'::"text" NOT NULL,
    "tier" "text" DEFAULT 'standard'::"text" NOT NULL,
    "use_for" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "input_price_per_million" numeric(10,4),
    "output_price_per_million" numeric(10,4),
    "cached_input_price_per_million" numeric(10,4),
    "is_active" boolean DEFAULT true NOT NULL,
    "display_order" integer DEFAULT 100 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "audio_price_per_minute" numeric,
    "thinking_price_per_million" numeric(10,4),
    "thinking_budgets" "jsonb"
);


ALTER TABLE "public"."models_master" OWNER TO "postgres";


COMMENT ON COLUMN "public"."models_master"."thinking_price_per_million" IS 'Price per million thinking/reasoning tokens (Gemini 2.5+ models)';



COMMENT ON COLUMN "public"."models_master"."thinking_budgets" IS 'Per-call-type thinking budget config. Keys: transcription, extraction, emotion, triage, consultation_insights, merge. Value 0 = disabled, null key = model default.';



CREATE TABLE IF NOT EXISTS "public"."nurse_doctors" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "nurse_id" "uuid" NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."nurse_doctors" OWNER TO "postgres";


COMMENT ON TABLE "public"."nurse_doctors" IS 'Junction table linking nurses to their supervising doctors';



CREATE TABLE IF NOT EXISTS "public"."nurse_templates" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "nurse_id" "uuid" NOT NULL,
    "template_id" "uuid" NOT NULL,
    "template_code" character varying(50) NOT NULL,
    "access_level" character varying(10) DEFAULT 'use'::character varying,
    "is_active" boolean DEFAULT false,
    "activated_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "nurse_templates_access_level_check" CHECK ((("access_level")::"text" = ANY ((ARRAY['view'::character varying, 'use'::character varying])::"text"[])))
);


ALTER TABLE "public"."nurse_templates" OWNER TO "postgres";


COMMENT ON TABLE "public"."nurse_templates" IS 'Junction table controlling which templates nurses can access';



COMMENT ON COLUMN "public"."nurse_templates"."template_code" IS 'Denormalized template_code for easy readability in database queries';



COMMENT ON COLUMN "public"."nurse_templates"."access_level" IS 'view = read-only, use = can use for extractions';



COMMENT ON COLUMN "public"."nurse_templates"."is_active" IS 'Whether this template is currently activated for the nurse';



CREATE TABLE IF NOT EXISTS "public"."nurses" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "email" character varying(255) NOT NULL,
    "full_name" character varying(255) NOT NULL,
    "qualification" character varying(100),
    "hospital_id" "uuid",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "default_template_id" "uuid"
);


ALTER TABLE "public"."nurses" OWNER TO "postgres";


COMMENT ON TABLE "public"."nurses" IS 'Nurse users who can perform recording and extraction operations under doctor supervision';



COMMENT ON COLUMN "public"."nurses"."qualification" IS 'Nursing qualification: RN (Registered Nurse), LPN (Licensed Practical Nurse), BSN (Bachelor of Science in Nursing), etc.';



COMMENT ON COLUMN "public"."nurses"."default_template_id" IS 'Nurse-specific default template (used in nurse fallback chain)';



CREATE TABLE IF NOT EXISTS "public"."other_clinical_needs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "patient_id" "uuid",
    "doctor_id" "uuid",
    "is_followup_diagnostics" boolean DEFAULT false,
    "is_recurring_diagnostics" boolean DEFAULT false,
    "is_rx_refill" boolean DEFAULT false,
    "followup_diagnostics_reasons" "text"[] DEFAULT '{}'::"text"[],
    "recurring_diagnostics_reasons" "text"[] DEFAULT '{}'::"text"[],
    "rx_refill_reasons" "text"[] DEFAULT '{}'::"text"[],
    "clinical_severity_id" "uuid",
    "calculation_version" "text" DEFAULT '1.0.0'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "priority_level" "text" DEFAULT 'NONE'::"text",
    "consultation_insights_id" "uuid",
    CONSTRAINT "other_clinical_needs_priority_level_check" CHECK (("priority_level" = ANY (ARRAY['NONE'::"text", 'LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text"])))
);


ALTER TABLE "public"."other_clinical_needs" OWNER TO "postgres";


COMMENT ON TABLE "public"."other_clinical_needs" IS 'Other clinical needs assessment. Raw AI signals in consultation_insights (join via consultation_insights_id)';



COMMENT ON COLUMN "public"."other_clinical_needs"."is_followup_diagnostics" IS 'TRUE if patient needs diagnostic tests before/at next visit';



COMMENT ON COLUMN "public"."other_clinical_needs"."is_recurring_diagnostics" IS 'TRUE if patient needs periodic/recurring tests based on chronic conditions';



COMMENT ON COLUMN "public"."other_clinical_needs"."is_rx_refill" IS 'TRUE if patient will need prescription refill (duration >30 days or chronic)';



COMMENT ON COLUMN "public"."other_clinical_needs"."clinical_severity_id" IS 'Reference to clinical severity assessment for is_chronic flag access';



COMMENT ON COLUMN "public"."other_clinical_needs"."priority_level" IS 'Consolidated priority: HIGH (all 3 flags or recurring+refill), MEDIUM (2 flags or recurring alone), LOW (1 flag), NONE (0 flags)';



COMMENT ON COLUMN "public"."other_clinical_needs"."consultation_insights_id" IS 'Reference to consultation_insights for raw AI signals (analytics joins)';



CREATE TABLE IF NOT EXISTS "public"."patient_dropoff_risk" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "patient_id" "uuid",
    "doctor_id" "uuid",
    "dropoff_probability" numeric(5,2) NOT NULL,
    "risk_level" "text" NOT NULL,
    "is_financial_risk" boolean DEFAULT false,
    "is_competitor_risk" boolean DEFAULT false,
    "is_dissatisfaction_risk" boolean DEFAULT false,
    "is_access_risk" boolean DEFAULT false,
    "is_compliance_risk" boolean DEFAULT false,
    "financial_risk_reasons" "text"[] DEFAULT '{}'::"text"[],
    "competitor_risk_reasons" "text"[] DEFAULT '{}'::"text"[],
    "dissatisfaction_risk_reasons" "text"[] DEFAULT '{}'::"text"[],
    "access_risk_reasons" "text"[] DEFAULT '{}'::"text"[],
    "compliance_risk_reasons" "text"[] DEFAULT '{}'::"text"[],
    "anxiety_pre_level" "text",
    "anxiety_post_level" "text",
    "anxiety_trajectory" "text",
    "anxiety_modifier" numeric(3,2),
    "compliance_likelihood" "text",
    "compliance_modifier" numeric(3,2),
    "base_probability" numeric(5,2),
    "indicator_count" integer,
    "primary_risk_driver" "text",
    "calculation_version" "text" DEFAULT '1.0.0'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "reasons" "text"[] DEFAULT '{}'::"text"[],
    "consultation_insights_id" "uuid",
    CONSTRAINT "patient_dropoff_risk_risk_level_check" CHECK (("risk_level" = ANY (ARRAY['LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'CRITICAL'::"text"])))
);


ALTER TABLE "public"."patient_dropoff_risk" OWNER TO "postgres";


COMMENT ON TABLE "public"."patient_dropoff_risk" IS 'Patient dropoff/churn risk. Raw AI signals in consultation_insights (join via consultation_insights_id)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."dropoff_probability" IS 'Probability (0-100%) that patient will not return for follow-up or abandon treatment';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."risk_level" IS 'Risk category: LOW (5-29%), MEDIUM (30-49%), HIGH (50-69%), CRITICAL (70-95%)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."is_financial_risk" IS 'C1: Financial concerns or price sensitivity detected (25% weight)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."is_competitor_risk" IS 'C2: Patient considering other healthcare providers (10% weight)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."is_dissatisfaction_risk" IS 'C3: Dissatisfaction or weak rapport with doctor (25% weight)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."is_access_risk" IS 'C4: Access or logistics barriers to care (10% weight)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."is_compliance_risk" IS 'C5: Compliance concerns or treatment confusion (30% weight)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."anxiety_modifier" IS 'Multiplier based on anxiety trajectory: 0.75 (improved) to 1.30 (worsened)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."compliance_modifier" IS 'Multiplier based on compliance likelihood: 0.85 (high) to 1.25 (very low)';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."primary_risk_driver" IS 'The highest-weighted TRUE indicator driving the risk score';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."reasons" IS 'Consolidated human-readable array of all triggered risk indicator reasons';



COMMENT ON COLUMN "public"."patient_dropoff_risk"."consultation_insights_id" IS 'Reference to consultation_insights for raw AI signals (analytics joins)';



CREATE TABLE IF NOT EXISTS "public"."patient_sharing" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_doctor_id" "uuid" NOT NULL,
    "target_doctor_id" "uuid" NOT NULL,
    "patient_id" "uuid" NOT NULL,
    "access_level" character varying(20) DEFAULT 'read'::character varying,
    "shared_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone,
    "revoked_at" timestamp with time zone,
    "reason" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."patient_sharing" OWNER TO "postgres";


COMMENT ON TABLE "public"."patient_sharing" IS 'Doctor-to-doctor patient sharing for cross-doctor Q&A Engine access';



COMMENT ON COLUMN "public"."patient_sharing"."access_level" IS 'Permission level: read (view only) or read_write (can add notes)';



CREATE TABLE IF NOT EXISTS "public"."patients" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "patient_id" character varying(100) NOT NULL,
    "full_name" character varying(255),
    "date_of_birth" "date",
    "gender" character varying(20),
    "is_anonymized" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "add_info" "jsonb",
    "ip_id" character varying(255),
    "op_id" character varying(255),
    "doctor_ids" "uuid"[] DEFAULT '{}'::"uuid"[],
    "hospital_id" "uuid",
    "preferred_language" character varying(50) DEFAULT NULL::character varying,
    CONSTRAINT "chk_gender" CHECK ((("gender")::"text" = ANY ((ARRAY['Male'::character varying, 'Female'::character varying, 'Other'::character varying, 'Prefer not to say'::character varying, NULL::character varying])::"text"[])))
);


ALTER TABLE "public"."patients" OWNER TO "postgres";


COMMENT ON COLUMN "public"."patients"."add_info" IS 'Additional info from external hospital systems (e.g., NICU data: visitNumber, roomNo, bedNo, gestation)';



COMMENT ON COLUMN "public"."patients"."ip_id" IS 'Inpatient visit/admission ID (optional, from EHR)';



COMMENT ON COLUMN "public"."patients"."op_id" IS 'Outpatient visit ID (optional, from EHR)';



COMMENT ON COLUMN "public"."patients"."doctor_ids" IS 'Array of doctor UUIDs that this patient is linked to. Used for doctor-specific patient lists.';



CREATE TABLE IF NOT EXISTS "public"."phi_audit_log" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "client_id" "uuid",
    "client_type" "text" NOT NULL,
    "client_name" "text" NOT NULL,
    "user_id" "uuid",
    "user_email" "text",
    "action" "text" NOT NULL,
    "resource_type" "text" NOT NULL,
    "resource_id" "text",
    "patient_id" "text",
    "doctor_id" "uuid",
    "hospital_id" "uuid",
    "endpoint" "text" NOT NULL,
    "method" "text" NOT NULL,
    "ip_address" "inet",
    "user_agent" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "request_id" "uuid",
    "status_code" integer,
    "response_time_ms" integer,
    "error_message" "text",
    "phi_fields_accessed" "text"[],
    "data_exported" boolean DEFAULT false,
    "access_reason" "text"
);


ALTER TABLE "public"."phi_audit_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."phi_audit_log" IS 'HIPAA-compliant audit log for all PHI access. Retain for minimum 6 years.';



CREATE TABLE IF NOT EXISTS "public"."procedure_fee_master" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "procedure_name" character varying(255) NOT NULL,
    "cpt_code" character varying(20),
    "icd_pcs_code" character varying(20),
    "fee" numeric(10,2) NOT NULL,
    "category" character varying(50) DEFAULT 'minor'::character varying,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."procedure_fee_master" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."processing_jobs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "submission_id" "uuid" NOT NULL,
    "session_id" "uuid" NOT NULL,
    "status" character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    "progress_percentage" integer DEFAULT 0,
    "progress_message" "text",
    "stitched_audio_path" "text",
    "transcript" "text",
    "insights" "jsonb",
    "stitching_time_seconds" numeric(10,2),
    "transcription_time_seconds" numeric(10,2),
    "extraction_time_seconds" numeric(10,2),
    "total_processing_time_seconds" numeric(10,2),
    "error_message" "text",
    "error_details" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "progress_json" "jsonb",
    CONSTRAINT "processing_jobs_progress_percentage_check" CHECK ((("progress_percentage" >= 0) AND ("progress_percentage" <= 100))),
    CONSTRAINT "processing_jobs_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['PENDING'::character varying, 'STITCHING'::character varying, 'TRANSCRIBING'::character varying, 'EXTRACTING'::character varying, 'COMPLETED'::character varying, 'ERROR'::character varying])::"text"[])))
);

ALTER TABLE ONLY "public"."processing_jobs" REPLICA IDENTITY FULL;


ALTER TABLE "public"."processing_jobs" OWNER TO "postgres";


COMMENT ON COLUMN "public"."processing_jobs"."error_details" IS 'JSON object with error details. May include: exception_type (str), keep_chunks (bool for validation failures).';



CREATE TABLE IF NOT EXISTS "public"."processing_modes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "mode_code" character varying(50) NOT NULL,
    "mode_name" character varying(100) NOT NULL,
    "description" "text",
    "transcription_api" character varying(50) NOT NULL,
    "transcription_model" character varying(100) NOT NULL,
    "extraction_model" character varying(100) NOT NULL,
    "estimated_time_seconds" integer,
    "display_order" integer DEFAULT 999 NOT NULL,
    "is_active" boolean DEFAULT true,
    "is_default" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "triage_model" character varying(100) DEFAULT 'gemini-3-flash-preview'::character varying,
    "merge_model" character varying(100) DEFAULT 'gemini-3-pro-preview'::character varying,
    "compare_model" character varying(100) DEFAULT 'gemini-3-flash-preview'::character varying,
    "emotion_model" character varying(100) DEFAULT 'gemini-3-flash-preview'::character varying,
    "insights_model" character varying(100) DEFAULT 'gemini-3-flash-preview'::character varying,
    "translation_model" character varying(100) DEFAULT 'gemini-2.5-flash'::character varying,
    "validator_model" character varying(100),
    CONSTRAINT "processing_modes_mode_code_check" CHECK ((("mode_code")::"text" = ANY (ARRAY['fast'::"text", 'default'::"text", 'thorough'::"text", 'ultra'::"text", 'ultra_fast'::"text"]))),
    CONSTRAINT "processing_modes_transcription_api_check" CHECK ((("transcription_api")::"text" = ANY ((ARRAY['gemini_batch'::character varying, 'gemini_live'::character varying])::"text"[])))
);


ALTER TABLE "public"."processing_modes" OWNER TO "postgres";


COMMENT ON TABLE "public"."processing_modes" IS 'Stores processing mode configurations that determine which Gemini models to use for transcription and extraction';



COMMENT ON COLUMN "public"."processing_modes"."transcription_api" IS 'API type: gemini_batch (standard batch processing) or gemini_live (real-time WebSocket API)';



COMMENT ON COLUMN "public"."processing_modes"."transcription_model" IS 'Gemini model for transcription (e.g., gemini-2.5-flash, gemini-2.5-pro, gemini-2.5-flash-native-audio-preview)';



COMMENT ON COLUMN "public"."processing_modes"."extraction_model" IS 'Gemini model for extraction (e.g., gemini-2.5-flash, gemini-2.5-pro)';



COMMENT ON COLUMN "public"."processing_modes"."translation_model" IS 'Model used for post-extraction Indic language translation';



CREATE TABLE IF NOT EXISTS "public"."qa_engine_settings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "embedding_model_id" "uuid" NOT NULL,
    "is_enabled" boolean DEFAULT true,
    "allow_analytics_queries" boolean DEFAULT true,
    "allow_cross_doctor_search" boolean DEFAULT false,
    "max_results_per_query" integer DEFAULT 20,
    "max_queries_per_day" integer DEFAULT 1000,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."qa_engine_settings" OWNER TO "postgres";


COMMENT ON TABLE "public"."qa_engine_settings" IS 'Per-hospital Q&A Engine configuration including embedding model selection';



COMMENT ON COLUMN "public"."qa_engine_settings"."allow_cross_doctor_search" IS 'When true, doctors can search across all doctors in the hospital';



CREATE TABLE IF NOT EXISTS "public"."qa_query_history" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "doctor_id" "uuid",
    "user_role" character varying(50),
    "query_text" "text" NOT NULL,
    "query_intent" character varying(50),
    "search_level" character varying(50),
    "result_count" integer DEFAULT 0,
    "response_format" character varying(50),
    "embedding_time_ms" integer,
    "search_time_ms" integer,
    "synthesis_time_ms" integer,
    "total_time_ms" integer,
    "embedding_model_id" "uuid",
    "synthesis_model" character varying(100),
    "total_tokens" integer,
    "total_cost_usd" numeric(10,6),
    "error_message" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "reframed_query" "text",
    "reframe_expansions" "jsonb" DEFAULT '[]'::"jsonb",
    "reframe_corrections" "jsonb" DEFAULT '[]'::"jsonb",
    "reframe_confidence" numeric(3,2),
    "reframe_time_ms" integer
);


ALTER TABLE "public"."qa_query_history" OWNER TO "postgres";


COMMENT ON TABLE "public"."qa_query_history" IS 'Audit trail for Q&A Engine queries with performance metrics and cost tracking';



COMMENT ON COLUMN "public"."qa_query_history"."reframed_query" IS 'The reframed/normalized version of the original query after preprocessing';



COMMENT ON COLUMN "public"."qa_query_history"."reframe_expansions" IS 'JSON array of expansions applied, e.g., [{"original": "BP", "expanded": "blood pressure"}]';



COMMENT ON COLUMN "public"."qa_query_history"."reframe_corrections" IS 'JSON array of corrections applied, e.g., [{"original": "diabeties", "corrected": "diabetes"}]';



COMMENT ON COLUMN "public"."qa_query_history"."reframe_confidence" IS 'Confidence score of the reframing (0.0-1.0)';



COMMENT ON COLUMN "public"."qa_query_history"."reframe_time_ms" IS 'Time taken for query reframing in milliseconds';



CREATE TABLE IF NOT EXISTS "public"."radiology_plan_library" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "template_id" "uuid" NOT NULL,
    "plan_code" character varying(64) NOT NULL,
    "plan_name" character varying(255) NOT NULL,
    "rt_intent" character varying(64),
    "rt_indication" "text",
    "rt_dose_gy" character varying(32),
    "rt_fractions" character varying(32),
    "rt_dose_per_fraction_gy" character varying(32),
    "rt_weeks" character varying(32),
    "rt_technique" character varying(128),
    "concurrent_systemic_therapy" "text",
    "display_order" integer DEFAULT 0,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."radiology_plan_library" OWNER TO "postgres";


COMMENT ON TABLE "public"."radiology_plan_library" IS 'Per-template plan templates substituted into PLAN segment {{LIBRARY_PLAN}} placeholder';



CREATE TABLE IF NOT EXISTS "public"."radiology_toxicity_library" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "template_id" "uuid" NOT NULL,
    "toxicity_code" character varying(64) NOT NULL,
    "phase" character varying(16) NOT NULL,
    "text" "text" NOT NULL,
    "conditional_trigger" character varying(64),
    "display_order" integer DEFAULT 0,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "radiology_toxicity_library_phase_check" CHECK ((("phase")::"text" = ANY ((ARRAY['early'::character varying, 'late'::character varying])::"text"[])))
);


ALTER TABLE "public"."radiology_toxicity_library" OWNER TO "postgres";


COMMENT ON TABLE "public"."radiology_toxicity_library" IS 'Per-template early/late toxicity items substituted into TOXICITY segment {{LIBRARY_TOXICITY}} placeholder';



COMMENT ON COLUMN "public"."radiology_toxicity_library"."conditional_trigger" IS 'Optional trigger flag (e.g. BRACHYTHERAPY, SCF, LEFT_HEART) for items only included when trigger is met. Mirrors prompt id-prefix conventions GY_BR_*, BR_SCF_*, BR_LH_*.';



CREATE TABLE IF NOT EXISTS "public"."realtime_extraction_responses" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "submission_id" character varying(100) NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "doctor_id" "uuid",
    "extraction_id" "uuid",
    "response" "jsonb" NOT NULL,
    "hospital_code" character varying(50),
    "created_at" timestamp with time zone DEFAULT "now"()
);

ALTER TABLE ONLY "public"."realtime_extraction_responses" REPLICA IDENTITY FULL;


ALTER TABLE "public"."realtime_extraction_responses" OWNER TO "postgres";


COMMENT ON TABLE "public"."realtime_extraction_responses" IS 'Stores extraction results for Supabase Realtime subscriptions. Records auto-deleted after 24 hours.';



COMMENT ON COLUMN "public"."realtime_extraction_responses"."response" IS 'EHR status response JSON containing submission_id, status, progress, message, extraction_id, and insights';



CREATE TABLE IF NOT EXISTS "public"."refresh_tokens" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "client_id" "uuid" NOT NULL,
    "token_hash" "text" NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "is_revoked" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "revoked_at" timestamp with time zone
);


ALTER TABLE "public"."refresh_tokens" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."room_rate_master" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hospital_id" "uuid" NOT NULL,
    "room_category" character varying(100) NOT NULL,
    "room_sub_category" character varying(100),
    "rate_per_day" numeric(10,2) NOT NULL,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."room_rate_master" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."segment_definitions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "segment_code" character varying(50) NOT NULL,
    "segment_name" character varying(255) NOT NULL,
    "prompt_section_text" "text" NOT NULL,
    "schema_definition_json" "jsonb" NOT NULL,
    "default_category" character varying(20) DEFAULT 'core'::character varying NOT NULL,
    "is_required" boolean DEFAULT false,
    "display_order" integer NOT NULL,
    "segment_type" character varying(50),
    "default_brevity_level" character varying(20) DEFAULT 'balanced'::character varying,
    "default_terminology_style" character varying(20) DEFAULT 'medical_terms'::character varying,
    "description" "text",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "status" character varying(20) DEFAULT 'active'::character varying,
    "approved_by_admin_id" "uuid",
    "approved_at" timestamp with time zone,
    "parent_segment_code" character varying(50),
    "is_cloned_from_parent" boolean DEFAULT false,
    "cloned_at" timestamp with time zone,
    "diverged_from_parent" boolean DEFAULT false,
    "last_parent_sync_at" timestamp with time zone,
    "doctor_id" "uuid",
    CONSTRAINT "segment_definitions_default_brevity_level_check" CHECK ((("default_brevity_level")::"text" = ANY ((ARRAY['concise'::character varying, 'balanced'::character varying, 'detailed'::character varying])::"text"[]))),
    CONSTRAINT "segment_definitions_default_category_check" CHECK ((("default_category")::"text" = ANY ((ARRAY['core'::character varying, 'additional'::character varying, 'excluded'::character varying])::"text"[]))),
    CONSTRAINT "segment_definitions_default_terminology_style_check" CHECK ((("default_terminology_style")::"text" = ANY ((ARRAY['medical_terms'::character varying, 'simple_terms'::character varying, 'as_spoken'::character varying])::"text"[]))),
    CONSTRAINT "segment_definitions_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['draft'::character varying, 'pending_approval'::character varying, 'active'::character varying, 'rejected'::character varying])::"text"[]))),
    CONSTRAINT "segment_ownership_check" CHECK ((((("segment_type")::"text" = 'system'::"text") AND ("doctor_id" IS NULL)) OR ((("segment_type")::"text" = 'doctor'::"text") AND ("doctor_id" IS NOT NULL))))
);


ALTER TABLE "public"."segment_definitions" OWNER TO "postgres";


COMMENT ON TABLE "public"."segment_definitions" IS 'Segment definitions including combined emotion analysis segments (COMBINED_ANXIETY, COMBINED_FINANCIAL_CONCERNS, COMBINED_OTHER_EMOTIONS, COMBINED_COMPLIANCE, COMBINED_DOCTOR_STYLE, COMBINED_INTERACTION_DYNAMICS, COMBINED_CONGRUENCE_SUMMARY)';



COMMENT ON COLUMN "public"."segment_definitions"."default_category" IS 'Segment category: core (always extracted), additional (optional), excluded (hidden from this type)';



COMMENT ON COLUMN "public"."segment_definitions"."segment_type" IS 'Type of segment: "system" (admin-created) or "doctor" (doctor-requested and approved)';



COMMENT ON COLUMN "public"."segment_definitions"."is_active" IS 'Soft delete flag: false means deleted or pending approval';



COMMENT ON COLUMN "public"."segment_definitions"."status" IS 'Segment lifecycle status: draft (incomplete), pending_approval (submitted by doctor), active (approved and usable), rejected (declined by admin)';



COMMENT ON COLUMN "public"."segment_definitions"."approved_by_admin_id" IS 'Admin who approved this segment (NULL for pending or admin-created segments)';



COMMENT ON COLUMN "public"."segment_definitions"."parent_segment_code" IS 'Tracks which segment this was cloned from (e.g., DIAGNOSIS_CARDIOLOGY parent is DIAGNOSIS).
Enables "show differences from parent" and optional "propagate changes" features.';



COMMENT ON COLUMN "public"."segment_definitions"."is_cloned_from_parent" IS 'TRUE if this segment was created by cloning another segment (via "Clone from..." UI).
FALSE if created from scratch or for consultation-type-specific overrides.';



COMMENT ON COLUMN "public"."segment_definitions"."cloned_at" IS 'Timestamp when this segment was cloned from its parent.
NULL if not cloned or if consultation-type-specific override.';



COMMENT ON COLUMN "public"."segment_definitions"."diverged_from_parent" IS 'TRUE if this segment has been manually edited after cloning and differs from parent.
Helps identify which cloned segments have customizations vs. still matching parent.';



COMMENT ON COLUMN "public"."segment_definitions"."last_parent_sync_at" IS 'Timestamp of last successful sync from parent (for optional "pull changes from parent" feature).
NULL if never synced or if diverged_from_parent is TRUE.';



CREATE TABLE IF NOT EXISTS "public"."segment_embeddings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "segment_id" "uuid",
    "model_id" "uuid" NOT NULL,
    "segment_code" character varying(100) NOT NULL,
    "segment_name" character varying(200),
    "embedding" "extensions"."vector"(1536),
    "embedded_content" "text" NOT NULL,
    "content_hash" character varying(64),
    "hospital_id" "uuid",
    "doctor_id" "uuid",
    "patient_id" "uuid",
    "token_count" integer,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."segment_embeddings" OWNER TO "postgres";


COMMENT ON TABLE "public"."segment_embeddings" IS 'Segment-level embeddings for individual extraction segments (e.g., CHIEF_COMPLAINT, DIAGNOSIS)';



COMMENT ON COLUMN "public"."segment_embeddings"."segment_code" IS 'Segment code for filtering (e.g., CHIEF_COMPLAINT, PRESCRIPTION)';



COMMENT ON COLUMN "public"."segment_embeddings"."embedding" IS 'Vector embedding (1536 dims max). Supports Cohere v4, OpenAI small, Gemini. HNSW indexed for fast search.';



CREATE TABLE IF NOT EXISTS "public"."session_audit_log" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "session_id" "uuid" NOT NULL,
    "action" character varying(50) NOT NULL,
    "old_values" "jsonb",
    "new_values" "jsonb",
    "changed_by" character varying(255),
    "changed_at" timestamp with time zone DEFAULT "now"(),
    "ip_address" "inet",
    "user_agent" "text"
);


ALTER TABLE "public"."session_audit_log" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."specialty_benchmarks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "specialty" "text" NOT NULL,
    "total_doctors" integer DEFAULT 0,
    "total_hospitals" integer DEFAULT 0,
    "total_extractions" integer DEFAULT 0,
    "avg_investigations_ordered" numeric(5,2),
    "avg_acceptance_rate" numeric(5,2),
    "common_presentations" "jsonb" DEFAULT '[]'::"jsonb",
    "common_red_flags_detected" "jsonb" DEFAULT '[]'::"jsonb",
    "benchmark_investigation_rates" "jsonb" DEFAULT '{}'::"jsonb",
    "last_computed_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."specialty_benchmarks" OWNER TO "postgres";


COMMENT ON TABLE "public"."specialty_benchmarks" IS 'Cross-hospital specialty benchmarks for national/regional comparisons';



COMMENT ON COLUMN "public"."specialty_benchmarks"."benchmark_investigation_rates" IS 'National/regional benchmark rates for common investigations';



CREATE TABLE IF NOT EXISTS "public"."system_prompt_components" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "component_code" character varying(50) NOT NULL,
    "component_name" character varying(255) NOT NULL,
    "component_type" character varying(50) NOT NULL,
    "content_text" "text" NOT NULL,
    "content_version" character varying(20) DEFAULT '1.0.0'::character varying,
    "description" "text",
    "is_base_component" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_active" boolean DEFAULT true
);


ALTER TABLE "public"."system_prompt_components" OWNER TO "postgres";


COMMENT ON TABLE "public"."system_prompt_components" IS 'Reusable building blocks for system prompts (role, capabilities, guidelines, etc.)';



COMMENT ON COLUMN "public"."system_prompt_components"."component_type" IS 'Flexible type: role, capabilities, critical_guidelines, processing_info, processing_rules, special_handling, validation_checklist';



COMMENT ON COLUMN "public"."system_prompt_components"."is_base_component" IS 'True for default/template components that can be cloned';



COMMENT ON COLUMN "public"."system_prompt_components"."is_active" IS 'Soft delete flag - inactive components are hidden from selection';



CREATE TABLE IF NOT EXISTS "public"."system_prompt_config_components" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "config_id" "uuid" NOT NULL,
    "component_id" "uuid" NOT NULL,
    "config_code" character varying(100) NOT NULL,
    "component_code" character varying(50) NOT NULL,
    "display_order" integer DEFAULT 0 NOT NULL,
    "is_included" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."system_prompt_config_components" OWNER TO "postgres";


COMMENT ON TABLE "public"."system_prompt_config_components" IS 'Junction table linking configs to components with ordering';



COMMENT ON COLUMN "public"."system_prompt_config_components"."is_included" IS 'Set to false to exclude component from assembly without removing';



CREATE TABLE IF NOT EXISTS "public"."system_prompt_configurations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "config_code" character varying(100) NOT NULL,
    "config_name" character varying(255) NOT NULL,
    "config_version" character varying(20) DEFAULT '1.0.0'::character varying,
    "is_active" boolean DEFAULT true,
    "is_draft" boolean DEFAULT true,
    "inherits_from_id" "uuid",
    "assembled_system_prompt" "text",
    "assembled_at" timestamp with time zone,
    "assembly_hash" character varying(64),
    "description" "text",
    "estimated_token_count" integer,
    "usage_count" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."system_prompt_configurations" OWNER TO "postgres";


COMMENT ON TABLE "public"."system_prompt_configurations" IS 'Versioned assemblies of prompt components';



COMMENT ON COLUMN "public"."system_prompt_configurations"."is_draft" IS 'Draft configs are not used in production extractions';



COMMENT ON COLUMN "public"."system_prompt_configurations"."assembly_hash" IS 'SHA-256 hash for detecting changes';



CREATE TABLE IF NOT EXISTS "public"."temp_audio_files" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "storage_path" "text" NOT NULL,
    "session_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone DEFAULT ("now"() + '24:00:00'::interval)
);


ALTER TABLE "public"."temp_audio_files" OWNER TO "postgres";


COMMENT ON TABLE "public"."temp_audio_files" IS 'Tracks temporary audio files in Supabase Storage for 24-hour auto-cleanup via pg_cron.';



CREATE TABLE IF NOT EXISTS "public"."template_ehr" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "template_id" "uuid" NOT NULL,
    "ehr_type_id" "uuid" NOT NULL,
    "url_suffix" character varying(255),
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."template_ehr" OWNER TO "postgres";


COMMENT ON TABLE "public"."template_ehr" IS 'Junction table for template-specific EHR URL suffixes. Used for Neopead templates that need different endpoints.';



COMMENT ON COLUMN "public"."template_ehr"."url_suffix" IS 'URL suffix appended to base URL. E.g., /store-daycare-transcribed-data for NEO_DAILY';



CREATE TABLE IF NOT EXISTS "public"."template_segments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "template_id" "uuid" NOT NULL,
    "segment_code" character varying(50) NOT NULL,
    "category" character varying(20) NOT NULL,
    "display_order" integer NOT NULL,
    "brevity_level" character varying(20) DEFAULT 'balanced'::character varying,
    "terminology_style" character varying(20) DEFAULT 'medical_terms'::character varying,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "segment_id" "uuid",
    "template_name" "text",
    "gap_analysis_fields_json" "jsonb",
    "include_in_empty_payload" boolean,
    CONSTRAINT "preset_segment_configurations_brevity_level_check" CHECK ((("brevity_level")::"text" = ANY (ARRAY[('concise'::character varying)::"text", ('balanced'::character varying)::"text", ('detailed'::character varying)::"text"]))),
    CONSTRAINT "preset_segment_configurations_category_check" CHECK ((("category")::"text" = ANY (ARRAY[('core'::character varying)::"text", ('additional'::character varying)::"text", ('excluded'::character varying)::"text"]))),
    CONSTRAINT "preset_segment_configurations_terminology_style_check" CHECK ((("terminology_style")::"text" = ANY (ARRAY[('medical_terms'::character varying)::"text", ('simple_terms'::character varying)::"text", ('as_spoken'::character varying)::"text"]))),
    CONSTRAINT "template_segment_configurations_category_check" CHECK ((("category")::"text" = ANY (ARRAY[('core'::character varying)::"text", ('additional'::character varying)::"text", ('excluded'::character varying)::"text"])))
);


ALTER TABLE "public"."template_segments" OWNER TO "postgres";


COMMENT ON TABLE "public"."template_segments" IS 'Junction table: Maps segments to doctor templates with template-specific configurations';



COMMENT ON COLUMN "public"."template_segments"."segment_id" IS 'Foreign key to segment_definitions.id (canonical reference)';



COMMENT ON COLUMN "public"."template_segments"."template_name" IS 'Denormalized template name for performance (reduces JOINs)';



COMMENT ON COLUMN "public"."template_segments"."gap_analysis_fields_json" IS 'Dot-path list of fields tracked by extraction-gaps. NULL = default (all leaves of recognized shape). [] = segment excluded from gap analysis. ["spo2","pulse"] = only those leaves tracked. Dot-paths: "dm.status", "pnd.present", etc.';



COMMENT ON COLUMN "public"."template_segments"."include_in_empty_payload" IS 'Admin opt-in to trim the empty-extraction payload. NULL = legacy (segment included). FALSE = segment omitted from both the segments list and empty_extraction object. TRUE = explicitly included.';



CREATE TABLE IF NOT EXISTS "public"."template_standard_texts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "template_id" "uuid" NOT NULL,
    "key" character varying(64) NOT NULL,
    "label" character varying(255),
    "text" "text" NOT NULL,
    "display_order" integer DEFAULT 0,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."template_standard_texts" OWNER TO "postgres";


COMMENT ON TABLE "public"."template_standard_texts" IS 'Per-template named text blocks merged into extraction JSON before EHR dispatch';



CREATE TABLE IF NOT EXISTS "public"."templates" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "template_code" character varying(50) NOT NULL,
    "template_name" character varying(255) NOT NULL,
    "description" "text",
    "use_case" character varying(100),
    "is_default" boolean DEFAULT false,
    "is_active" boolean DEFAULT true,
    "estimated_extraction_time_seconds" numeric(10,2),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "consultation_type_id" "uuid",
    "specialization" character varying(100),
    "hospital_id" "uuid",
    "doctor_id" "uuid",
    "assembled_full_prompt" "text",
    "prompt_assembled_at" timestamp with time zone,
    "prompt_trigger_source" "text",
    "system_prompt_config_id" "uuid",
    "assembled_schema_json" "jsonb",
    "schema_assembled_at" timestamp with time zone,
    "schema_trigger_source" "text",
    "prompt_assembly_hash" character varying,
    "schema_assembly_hash" character varying,
    "excluded_segment_codes" "text"[] DEFAULT '{}'::"text"[],
    "assembled_audio_prompt" "text",
    "audio_prompt_assembled_at" timestamp with time zone,
    "audio_prompt_trigger_source" "text",
    "audio_prompt_assembly_hash" character varying(64),
    "assembled_audio_schema_json" "jsonb",
    "audio_schema_assembled_at" timestamp with time zone,
    "audio_schema_trigger_source" "text",
    "audio_schema_assembly_hash" character varying(64),
    "assembled_text_emotion_prompt" "text",
    "text_emotion_prompt_assembled_at" timestamp with time zone,
    "text_emotion_prompt_trigger_source" "text",
    "text_emotion_prompt_assembly_hash" character varying(64),
    "assembled_text_emotion_schema_json" "jsonb",
    "text_emotion_schema_assembled_at" timestamp with time zone,
    "text_emotion_schema_trigger_source" "text",
    "text_emotion_schema_assembly_hash" character varying(64),
    "assembled_combined_emotion_prompt" "text",
    "assembled_combined_emotion_schema_json" "jsonb",
    "formatter_code" character varying(50),
    "letter_template_jinja" "text"
);


ALTER TABLE "public"."templates" OWNER TO "postgres";


COMMENT ON COLUMN "public"."templates"."template_code" IS 'Unique template identifier code (e.g., FULL_EXTRACTION, PSYCHIATRY_CORE)';



COMMENT ON COLUMN "public"."templates"."template_name" IS 'Display name for the template';



COMMENT ON COLUMN "public"."templates"."description" IS 'Detailed description of what this template extracts';



COMMENT ON COLUMN "public"."templates"."is_active" IS 'Whether this template is active. Replaces doctor_active_templates functionality.';



COMMENT ON COLUMN "public"."templates"."consultation_type_id" IS 'NULL = universal preset (works for all types), FK = preset only for this consultation type';



COMMENT ON COLUMN "public"."templates"."assembled_audio_prompt" IS 'Pre-assembled audio emotion analysis system prompt (combines base + AUDIO_ segment instructions)';



COMMENT ON COLUMN "public"."templates"."audio_prompt_assembled_at" IS 'Timestamp when audio prompt was last assembled';



COMMENT ON COLUMN "public"."templates"."audio_prompt_trigger_source" IS 'What triggered the last audio prompt assembly (e.g., segment:uuid:update, manual)';



COMMENT ON COLUMN "public"."templates"."audio_prompt_assembly_hash" IS 'SHA256 hash of assembled_audio_prompt for change detection';



COMMENT ON COLUMN "public"."templates"."assembled_audio_schema_json" IS 'Pre-assembled JSON schema for audio emotion extraction (combines AUDIO_ segment schemas)';



COMMENT ON COLUMN "public"."templates"."audio_schema_assembled_at" IS 'Timestamp when audio schema was last assembled';



COMMENT ON COLUMN "public"."templates"."audio_schema_trigger_source" IS 'What triggered the last audio schema assembly';



COMMENT ON COLUMN "public"."templates"."audio_schema_assembly_hash" IS 'SHA256 hash of assembled_audio_schema_json for change detection';



COMMENT ON COLUMN "public"."templates"."assembled_text_emotion_prompt" IS 'Pre-assembled text emotion analysis system prompt (combines base + TEXT_EMOTION_ segment instructions)';



COMMENT ON COLUMN "public"."templates"."text_emotion_prompt_assembled_at" IS 'Timestamp when text emotion prompt was last assembled';



COMMENT ON COLUMN "public"."templates"."text_emotion_prompt_trigger_source" IS 'What triggered the last text emotion prompt assembly (e.g., segment:uuid:update, manual)';



COMMENT ON COLUMN "public"."templates"."text_emotion_prompt_assembly_hash" IS 'SHA256 hash of assembled_text_emotion_prompt for change detection';



COMMENT ON COLUMN "public"."templates"."assembled_text_emotion_schema_json" IS 'Pre-assembled JSON schema for text emotion extraction (combines TEXT_EMOTION_ segment schemas)';



COMMENT ON COLUMN "public"."templates"."text_emotion_schema_assembled_at" IS 'Timestamp when text emotion schema was last assembled';



COMMENT ON COLUMN "public"."templates"."text_emotion_schema_trigger_source" IS 'What triggered the last text emotion schema assembly';



COMMENT ON COLUMN "public"."templates"."text_emotion_schema_assembly_hash" IS 'SHA256 hash of assembled_text_emotion_schema_json for change detection';



COMMENT ON COLUMN "public"."templates"."formatter_code" IS 'EHR formatter identifier (e.g., aosta, raster_op, raster_new_op, neopead, kg_initial, kg_reassess). NULL = no formatter.';



COMMENT ON COLUMN "public"."templates"."letter_template_jinja" IS 'Optional Jinja2 layout used by letter_render_service to produce consult_letter at extraction tail. NULL => no rendering.';



CREATE TABLE IF NOT EXISTS "public"."triage_conflict_log" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "conflict_type" "text" NOT NULL,
    "layer_1" "text" NOT NULL,
    "layer_1_suggestion" "text",
    "layer_1_priority" "text",
    "layer_2" "text" NOT NULL,
    "layer_2_suggestion" "text",
    "layer_2_priority" "text",
    "resolution_strategy" "text",
    "final_suggestion" "text",
    "final_priority" "text",
    "resolution_notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."triage_conflict_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."triage_conflict_log" IS 'Log of conflicts between triage layers for debugging and tuning resolution rules';



CREATE TABLE IF NOT EXISTS "public"."triage_feedback" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "suggestion_id" "uuid" NOT NULL,
    "doctor_id" "uuid" NOT NULL,
    "feedback_type" "text" NOT NULL,
    "rejection_reason" "text",
    "modified_text" "text",
    "feedback_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "triage_feedback_feedback_type_check" CHECK (("feedback_type" = ANY (ARRAY['accepted'::"text", 'rejected'::"text", 'maybe'::"text", 'modified'::"text"])))
);


ALTER TABLE "public"."triage_feedback" OWNER TO "postgres";


COMMENT ON TABLE "public"."triage_feedback" IS 'Optional doctor feedback on triage suggestions - used to learn doctor preferences and patterns';



COMMENT ON COLUMN "public"."triage_feedback"."feedback_type" IS 'Type of feedback: accepted (will act on), rejected (not applicable), maybe (consider later), modified (changed the suggestion)';



CREATE TABLE IF NOT EXISTS "public"."triage_suggestion_log" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "doctor_id" "uuid",
    "suggestion_category" "text" NOT NULL,
    "suggestion_type" "text" NOT NULL,
    "suggestion_text" "text" NOT NULL,
    "source_layer" "text" NOT NULL,
    "confidence_score" numeric(3,2),
    "priority_rank" integer,
    "patient_context_applied" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "layer_sources" "jsonb" DEFAULT '[]'::"jsonb",
    "rationale" "text"
);


ALTER TABLE "public"."triage_suggestion_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."triage_suggestion_log" IS 'Logs all triage suggestions generated for analytics, learning, and building doctor patterns';



COMMENT ON COLUMN "public"."triage_suggestion_log"."source_layer" IS 'Which layer of the multi-layered triage engine generated this suggestion';



COMMENT ON COLUMN "public"."triage_suggestion_log"."patient_context_applied" IS 'Snapshot of patient context (allergies, emotions, financial concerns) that was used to generate/filter suggestions';



COMMENT ON COLUMN "public"."triage_suggestion_log"."layer_sources" IS 'Array of layer codes that contributed to this suggestion (e.g., ["base_mvp", "doctor_practice", "rag_guideline:ICMR_STG"])';



COMMENT ON COLUMN "public"."triage_suggestion_log"."rationale" IS 'Explanation/reasoning for the triage suggestion';



CREATE OR REPLACE VIEW "public"."triage_doctor_stats" WITH ("security_invoker"='true') AS
 SELECT "d"."id" AS "doctor_id",
    "d"."full_name",
    "d"."specialization",
    "d"."hospital_id",
    "count"(DISTINCT "tsl"."extraction_id") AS "extractions_with_suggestions",
    "count"("tsl"."id") AS "total_suggestions",
    "count"("tf"."id") AS "total_feedback_given",
    "count"("tf"."id") FILTER (WHERE ("tf"."feedback_type" = 'accepted'::"text")) AS "accepted_count",
    "count"("tf"."id") FILTER (WHERE ("tf"."feedback_type" = 'rejected'::"text")) AS "rejected_count",
    "count"("tf"."id") FILTER (WHERE ("tf"."feedback_type" = 'modified'::"text")) AS "modified_count",
        CASE
            WHEN ("count"("tf"."id") > 0) THEN "round"(((("count"("tf"."id") FILTER (WHERE ("tf"."feedback_type" = 'accepted'::"text")))::numeric / ("count"("tf"."id"))::numeric) * (100)::numeric), 1)
            ELSE NULL::numeric
        END AS "acceptance_rate_pct",
    "max"("tsl"."created_at") AS "last_suggestion_at"
   FROM (("public"."doctors" "d"
     LEFT JOIN "public"."triage_suggestion_log" "tsl" ON (("d"."id" = "tsl"."doctor_id")))
     LEFT JOIN "public"."triage_feedback" "tf" ON (("tsl"."id" = "tf"."suggestion_id")))
  WHERE ("d"."is_active" = true)
  GROUP BY "d"."id", "d"."full_name", "d"."specialization", "d"."hospital_id";


ALTER VIEW "public"."triage_doctor_stats" OWNER TO "postgres";


COMMENT ON VIEW "public"."triage_doctor_stats" IS 'Aggregated triage statistics per doctor for admin visibility';



CREATE OR REPLACE VIEW "public"."triage_suggestion_analytics" WITH ("security_invoker"='true') AS
 SELECT "tsl"."id",
    "tsl"."extraction_id",
    "tsl"."doctor_id",
    "tsl"."suggestion_category",
    "tsl"."suggestion_type",
    "tsl"."suggestion_text",
    "tsl"."source_layer",
    "tsl"."confidence_score",
    "tsl"."priority_rank",
    "tsl"."created_at" AS "suggested_at",
    "tf"."id" AS "feedback_id",
    "tf"."feedback_type",
    "tf"."rejection_reason",
    "tf"."feedback_at",
    "me"."session_id",
    "me"."consultation_type_id",
    "rs"."patient_id",
    "d"."full_name" AS "doctor_name",
    "d"."specialization" AS "doctor_specialty",
    "d"."hospital_id"
   FROM (((("public"."triage_suggestion_log" "tsl"
     LEFT JOIN "public"."triage_feedback" "tf" ON (("tsl"."id" = "tf"."suggestion_id")))
     LEFT JOIN "public"."medical_extractions" "me" ON (("tsl"."extraction_id" = "me"."id")))
     LEFT JOIN "public"."recording_sessions" "rs" ON (("me"."session_id" = "rs"."id")))
     LEFT JOIN "public"."doctors" "d" ON (("tsl"."doctor_id" = "d"."id")));


ALTER VIEW "public"."triage_suggestion_analytics" OWNER TO "postgres";


COMMENT ON VIEW "public"."triage_suggestion_analytics" IS 'Analytics view joining suggestions with feedback and doctor/patient context';



CREATE OR REPLACE VIEW "public"."v_api_client_usage_summary" WITH ("security_invoker"='true') AS
 SELECT "ac"."id" AS "api_client_id",
    "ac"."client_name",
    "ac"."client_type",
    "ac"."hospital_id",
    "h"."hospital_name",
    "count"(DISTINCT "l"."id") AS "total_api_calls",
    "count"(DISTINCT "l"."session_id") AS "total_sessions",
    COALESCE("sum"("l"."total_cost_usd"), (0)::numeric) AS "total_cost_usd",
    COALESCE("sum"("l"."cache_savings_usd"), (0)::numeric) AS "total_cache_savings_usd",
    COALESCE("sum"("l"."prompt_token_count"), (0)::bigint) AS "total_input_tokens",
    COALESCE("sum"("l"."candidates_token_count"), (0)::bigint) AS "total_output_tokens",
    COALESCE("sum"("l"."cached_content_token_count"), (0)::bigint) AS "total_cached_tokens",
    COALESCE(( SELECT ("sum"("rs"."total_duration_seconds") / 3600.0)
           FROM "public"."recording_sessions" "rs"
          WHERE ("rs"."id" IN ( SELECT DISTINCT "llm_usage_log"."session_id"
                   FROM "public"."llm_usage_log"
                  WHERE ("llm_usage_log"."api_client_id" = "ac"."id")))), (0)::numeric) AS "total_recording_hours",
    COALESCE(("sum"(
        CASE
            WHEN (("l"."call_type")::"text" = 'transcription'::"text") THEN "l"."audio_duration_seconds"
            ELSE (0)::numeric
        END) / 3600.0), (0)::numeric) AS "total_transcription_hours",
    "avg"(
        CASE
            WHEN "l"."cache_hit" THEN "l"."cache_hit_ratio"
            ELSE NULL::numeric
        END) AS "avg_cache_hit_ratio",
    "count"(
        CASE
            WHEN (("l"."response_status")::"text" = 'error'::"text") THEN 1
            ELSE NULL::integer
        END) AS "error_count",
    "min"("l"."created_at") AS "first_usage_at",
    "max"("l"."created_at") AS "last_usage_at"
   FROM (("public"."api_clients" "ac"
     LEFT JOIN "public"."llm_usage_log" "l" ON (("l"."api_client_id" = "ac"."id")))
     LEFT JOIN "public"."hospitals" "h" ON (("ac"."hospital_id" = "h"."id")))
  GROUP BY "ac"."id", "ac"."client_name", "ac"."client_type", "ac"."hospital_id", "h"."hospital_name";


ALTER VIEW "public"."v_api_client_usage_summary" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."v_consultation_type_summary" WITH ("security_invoker"='true') AS
 SELECT "ct"."id" AS "consultation_type_id",
    "ct"."type_code",
    "ct"."type_name",
    "ct"."description",
    "ct"."is_active",
    "count"(DISTINCT "t"."id") AS "template_count",
    "count"(DISTINCT "sd"."id") AS "total_segments",
    "count"(DISTINCT
        CASE
            WHEN "ctsd"."is_required_for_type" THEN "sd"."id"
            ELSE NULL::"uuid"
        END) AS "required_segments"
   FROM ((("public"."consultation_types" "ct"
     LEFT JOIN "public"."templates" "t" ON ((("t"."consultation_type_id" = "ct"."id") AND ("t"."is_active" = true))))
     LEFT JOIN "public"."consultation_type_segments" "ctsd" ON (("ct"."id" = "ctsd"."consultation_type_id")))
     LEFT JOIN "public"."segment_definitions" "sd" ON ((("ctsd"."segment_code")::"text" = ("sd"."segment_code")::"text")))
  GROUP BY "ct"."id", "ct"."type_code", "ct"."type_name", "ct"."description", "ct"."is_active"
  ORDER BY "ct"."type_code";


ALTER VIEW "public"."v_consultation_type_summary" OWNER TO "postgres";


COMMENT ON VIEW "public"."v_consultation_type_summary" IS 'Summary of consultation types with template and segment counts';



CREATE OR REPLACE VIEW "public"."v_daily_usage_summary" WITH ("security_invoker"='true') AS
 SELECT "date"("created_at") AS "usage_date",
    "call_type",
    "model",
    "count"(*) AS "call_count",
    "sum"("prompt_token_count") AS "total_input_tokens",
    "sum"("candidates_token_count") AS "total_output_tokens",
    "sum"("cached_content_token_count") AS "total_cached_tokens",
    "sum"("total_cost_usd") AS "total_cost_usd",
    "sum"("cache_savings_usd") AS "total_cache_savings_usd",
    "avg"("api_duration_seconds") AS "avg_api_duration_seconds",
    "avg"("cache_hit_ratio") AS "avg_cache_hit_ratio",
    "count"(*) FILTER (WHERE ("cache_hit" = true)) AS "cache_hit_count",
    "count"(*) FILTER (WHERE (("response_status")::"text" = 'error'::"text")) AS "error_count"
   FROM "public"."llm_usage_log"
  GROUP BY ("date"("created_at")), "call_type", "model"
  ORDER BY ("date"("created_at")) DESC, "call_type", "model";


ALTER VIEW "public"."v_daily_usage_summary" OWNER TO "postgres";


COMMENT ON VIEW "public"."v_daily_usage_summary" IS 'Daily aggregated LLM usage for cost monitoring and trends';



CREATE OR REPLACE VIEW "public"."v_doctor_usage_summary" WITH ("security_invoker"='true') AS
 SELECT "l"."doctor_id",
    "d"."full_name" AS "doctor_name",
    "d"."specialization",
    "count"(*) AS "total_calls",
    "sum"("l"."total_cost_usd") AS "total_cost_usd",
    "sum"("l"."cache_savings_usd") AS "total_cache_savings_usd",
    "avg"("l"."cache_hit_ratio") AS "avg_cache_hit_ratio",
    "count"(DISTINCT "l"."session_id") AS "total_sessions",
    ("sum"("l"."total_cost_usd") / (NULLIF("count"(DISTINCT "l"."session_id"), 0))::numeric) AS "avg_cost_per_session"
   FROM ("public"."llm_usage_log" "l"
     LEFT JOIN "public"."doctors" "d" ON (("l"."doctor_id" = "d"."id")))
  WHERE ("l"."doctor_id" IS NOT NULL)
  GROUP BY "l"."doctor_id", "d"."full_name", "d"."specialization";


ALTER VIEW "public"."v_doctor_usage_summary" OWNER TO "postgres";


COMMENT ON VIEW "public"."v_doctor_usage_summary" IS 'LLM usage and costs aggregated by doctor';



CREATE OR REPLACE VIEW "public"."v_doctor_usage_summary_v2" WITH ("security_invoker"='true') AS
 SELECT "d"."id" AS "doctor_id",
    "d"."full_name" AS "doctor_name",
    "d"."specialization",
    "d"."hospital_id",
    "h"."hospital_name",
    "count"(DISTINCT "l"."id") AS "total_api_calls",
    "count"(DISTINCT "l"."session_id") AS "total_sessions",
    COALESCE("sum"("l"."total_cost_usd"), (0)::numeric) AS "total_cost_usd",
    COALESCE("sum"("l"."cache_savings_usd"), (0)::numeric) AS "total_cache_savings_usd",
    COALESCE("sum"("l"."prompt_token_count"), (0)::bigint) AS "total_input_tokens",
    COALESCE("sum"("l"."candidates_token_count"), (0)::bigint) AS "total_output_tokens",
    COALESCE("sum"("l"."cached_content_token_count"), (0)::bigint) AS "total_cached_tokens",
    COALESCE(( SELECT ("sum"("rs"."total_duration_seconds") / 3600.0)
           FROM "public"."recording_sessions" "rs"
          WHERE ("rs"."doctor_id" = "d"."id")), (0)::numeric) AS "total_recording_hours",
    COALESCE(("sum"(
        CASE
            WHEN (("l"."call_type")::"text" = 'transcription'::"text") THEN "l"."audio_duration_seconds"
            ELSE (0)::numeric
        END) / 3600.0), (0)::numeric) AS "total_transcription_hours",
    "avg"(
        CASE
            WHEN "l"."cache_hit" THEN "l"."cache_hit_ratio"
            ELSE NULL::numeric
        END) AS "avg_cache_hit_ratio",
    "count"(
        CASE
            WHEN (("l"."response_status")::"text" = 'error'::"text") THEN 1
            ELSE NULL::integer
        END) AS "error_count",
        CASE
            WHEN ("count"(DISTINCT "l"."session_id") > 0) THEN (COALESCE("sum"("l"."total_cost_usd"), (0)::numeric) / ("count"(DISTINCT "l"."session_id"))::numeric)
            ELSE (0)::numeric
        END AS "avg_cost_per_session",
    "min"("l"."created_at") AS "first_usage_at",
    "max"("l"."created_at") AS "last_usage_at"
   FROM (("public"."doctors" "d"
     LEFT JOIN "public"."llm_usage_log" "l" ON (("l"."doctor_id" = "d"."id")))
     LEFT JOIN "public"."hospitals" "h" ON (("d"."hospital_id" = "h"."id")))
  GROUP BY "d"."id", "d"."full_name", "d"."specialization", "d"."hospital_id", "h"."hospital_name";


ALTER VIEW "public"."v_doctor_usage_summary_v2" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."v_hospital_accuracy_metrics" WITH ("security_invoker"='true') AS
 SELECT "d"."hospital_id",
    "d"."id" AS "doctor_id",
    "d"."full_name" AS "doctor_name",
    "count"(*) AS "total_extractions",
    "round"("avg"("eam"."overall_wer"), 4) AS "avg_wer",
    "round"(("percentile_cont"((0.5)::double precision) WITHIN GROUP (ORDER BY (("eam"."overall_wer")::double precision)))::numeric, 4) AS "median_wer",
    "round"("avg"("eam"."entity_error_rate"), 4) AS "avg_entity_error_rate",
    "round"("avg"("eam"."segments_modified"), 1) AS "avg_segments_modified",
    "round"("avg"("eam"."segments_unchanged"), 1) AS "avg_segments_unchanged",
    "round"("avg"("eam"."doctor_additions_count"), 1) AS "avg_doctor_additions",
    "max"("eam"."computed_at") AS "last_computed_at"
   FROM ("public"."extraction_accuracy_metrics" "eam"
     JOIN "public"."doctors" "d" ON (("d"."id" = "eam"."doctor_id")))
  GROUP BY "d"."hospital_id", "d"."id", "d"."full_name";


ALTER VIEW "public"."v_hospital_accuracy_metrics" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."v_hospital_usage_summary" WITH ("security_invoker"='true') AS
 SELECT "h"."id" AS "hospital_id",
    "h"."hospital_name",
    "h"."hospital_code",
    "count"(DISTINCT "l"."id") AS "total_api_calls",
    "count"(DISTINCT "l"."session_id") AS "total_sessions",
    "count"(DISTINCT "l"."doctor_id") AS "unique_doctors",
    "count"(DISTINCT "l"."api_client_id") AS "unique_api_clients",
    COALESCE("sum"("l"."total_cost_usd"), (0)::numeric) AS "total_cost_usd",
    COALESCE("sum"("l"."cache_savings_usd"), (0)::numeric) AS "total_cache_savings_usd",
    COALESCE("sum"("l"."prompt_token_count"), (0)::bigint) AS "total_input_tokens",
    COALESCE("sum"("l"."candidates_token_count"), (0)::bigint) AS "total_output_tokens",
    COALESCE("sum"("l"."cached_content_token_count"), (0)::bigint) AS "total_cached_tokens",
    COALESCE(( SELECT ("sum"("rs"."total_duration_seconds") / 3600.0)
           FROM ("public"."recording_sessions" "rs"
             JOIN "public"."doctors" "d_1" ON (("rs"."doctor_id" = "d_1"."id")))
          WHERE ("d_1"."hospital_id" = "h"."id")), (0)::numeric) AS "total_recording_hours",
    COALESCE(("sum"(
        CASE
            WHEN (("l"."call_type")::"text" = 'transcription'::"text") THEN "l"."audio_duration_seconds"
            ELSE (0)::numeric
        END) / 3600.0), (0)::numeric) AS "total_transcription_hours",
    "avg"(
        CASE
            WHEN "l"."cache_hit" THEN "l"."cache_hit_ratio"
            ELSE NULL::numeric
        END) AS "avg_cache_hit_ratio",
    "count"(
        CASE
            WHEN (("l"."response_status")::"text" = 'error'::"text") THEN 1
            ELSE NULL::integer
        END) AS "error_count",
    "min"("l"."created_at") AS "first_usage_at",
    "max"("l"."created_at") AS "last_usage_at"
   FROM (("public"."hospitals" "h"
     LEFT JOIN "public"."doctors" "d" ON (("d"."hospital_id" = "h"."id")))
     LEFT JOIN "public"."llm_usage_log" "l" ON (("l"."doctor_id" = "d"."id")))
  GROUP BY "h"."id", "h"."hospital_name", "h"."hospital_code";


ALTER VIEW "public"."v_hospital_usage_summary" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."v_session_usage_summary" WITH ("security_invoker"='true') AS
 SELECT "session_id",
    "count"(*) AS "total_calls",
    "count"(*) FILTER (WHERE (("call_type")::"text" = 'transcription'::"text")) AS "transcription_calls",
    "count"(*) FILTER (WHERE (("call_type")::"text" = 'extraction'::"text")) AS "extraction_calls",
    "count"(*) FILTER (WHERE (("call_type")::"text" = 'emotion'::"text")) AS "emotion_calls",
    "sum"("prompt_token_count") AS "total_input_tokens",
    "sum"("candidates_token_count") AS "total_output_tokens",
    "sum"("cached_content_token_count") AS "total_cached_tokens",
    "sum"("total_cost_usd") AS "total_cost_usd",
    "sum"("cache_savings_usd") AS "total_cache_savings_usd",
    "sum"("api_duration_seconds") AS "total_api_duration_seconds",
    "avg"("cache_hit_ratio") FILTER (WHERE (("call_type")::"text" = 'extraction'::"text")) AS "avg_extraction_cache_hit_ratio"
   FROM "public"."llm_usage_log"
  WHERE ("session_id" IS NOT NULL)
  GROUP BY "session_id";


ALTER VIEW "public"."v_session_usage_summary" OWNER TO "postgres";


COMMENT ON VIEW "public"."v_session_usage_summary" IS 'Aggregated LLM usage statistics per recording session';



CREATE OR REPLACE VIEW "public"."v_template_configurations" WITH ("security_invoker"='true') AS
 SELECT "t"."id" AS "template_id",
    "t"."template_code",
    "t"."template_name",
    "t"."description" AS "template_description",
    "t"."consultation_type_id",
    "t"."specialization",
    "t"."hospital_id",
    "t"."is_active",
    "tsc"."id" AS "config_id",
    "tsc"."segment_code",
    "tsc"."display_order",
    "tsc"."category",
    "tsc"."brevity_level",
    "tsc"."terminology_style",
    "sd"."segment_name",
    "sd"."description" AS "segment_description",
    "sd"."default_category",
    "sd"."default_brevity_level",
    "sd"."default_terminology_style"
   FROM (("public"."templates" "t"
     LEFT JOIN "public"."template_segments" "tsc" ON (("t"."id" = "tsc"."template_id")))
     LEFT JOIN "public"."segment_definitions" "sd" ON ((("tsc"."segment_code")::"text" = ("sd"."segment_code")::"text")))
  WHERE ("t"."is_active" = true)
  ORDER BY "t"."template_code", "tsc"."display_order";


ALTER VIEW "public"."v_template_configurations" OWNER TO "postgres";


COMMENT ON VIEW "public"."v_template_configurations" IS 'Complete template configurations with segment details';



ALTER TABLE ONLY "public"."admin_action_log"
    ADD CONSTRAINT "admin_action_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."admin_users"
    ADD CONSTRAINT "admin_users_auth_user_id_key" UNIQUE ("auth_user_id");



ALTER TABLE ONLY "public"."admin_users"
    ADD CONSTRAINT "admin_users_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."allied_health_needs"
    ADD CONSTRAINT "allied_health_needs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."api_client_usage"
    ADD CONSTRAINT "api_client_usage_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."api_clients"
    ADD CONSTRAINT "api_clients_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."app_settings"
    ADD CONSTRAINT "app_settings_pkey" PRIMARY KEY ("key");



ALTER TABLE ONLY "public"."audio_chunks"
    ADD CONSTRAINT "audio_chunks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."audio_chunks"
    ADD CONSTRAINT "audio_chunks_session_id_chunk_index_key" UNIQUE ("session_id", "chunk_index");



ALTER TABLE ONLY "public"."audio_validation_warnings"
    ADD CONSTRAINT "audio_validation_warnings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bill_line_items"
    ADD CONSTRAINT "bill_line_items_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bills"
    ADD CONSTRAINT "bills_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."care_quality_risk"
    ADD CONSTRAINT "care_quality_risk_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."clinical_chunk_embeddings"
    ADD CONSTRAINT "clinical_chunk_embeddings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."clinical_chunks"
    ADD CONSTRAINT "clinical_chunks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."clinical_condition_ingestion_jobs"
    ADD CONSTRAINT "clinical_condition_ingestion_jobs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."clinical_conditions"
    ADD CONSTRAINT "clinical_conditions_condition_id_key" UNIQUE ("condition_id");



ALTER TABLE ONLY "public"."clinical_conditions"
    ADD CONSTRAINT "clinical_conditions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."clinical_guideline_embeddings"
    ADD CONSTRAINT "clinical_guideline_embeddings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."clinical_guidelines"
    ADD CONSTRAINT "clinical_guidelines_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."clinical_severity_assessments"
    ADD CONSTRAINT "clinical_severity_assessments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."consultation_insights"
    ADD CONSTRAINT "consultation_insights_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."consultation_type_segments"
    ADD CONSTRAINT "consultation_type_segments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."consultation_type_segments"
    ADD CONSTRAINT "consultation_type_segments_unique" UNIQUE ("consultation_type_id", "segment_id");



ALTER TABLE ONLY "public"."consultation_type_system_prompts"
    ADD CONSTRAINT "consultation_type_system_prompts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."consultation_types"
    ADD CONSTRAINT "consultation_types_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."consultation_types"
    ADD CONSTRAINT "consultation_types_type_code_key" UNIQUE ("type_code");



ALTER TABLE ONLY "public"."doctor_doctor_patients"
    ADD CONSTRAINT "doctor_doctor_patients_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."doctor_investigations"
    ADD CONSTRAINT "doctor_investigations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."doctor_layer_preferences"
    ADD CONSTRAINT "doctor_layer_preferences_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."doctor_medicines"
    ADD CONSTRAINT "doctor_medicines_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."doctor_practice_styles"
    ADD CONSTRAINT "doctor_practice_styles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."doctor_templates"
    ADD CONSTRAINT "doctor_templates_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."doctor_templates"
    ADD CONSTRAINT "doctor_templates_unique" UNIQUE ("doctor_id", "template_id");



ALTER TABLE ONLY "public"."doctors"
    ADD CONSTRAINT "doctors_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."doctors"
    ADD CONSTRAINT "doctors_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ehr_types"
    ADD CONSTRAINT "ehr_types_ehr_code_key" UNIQUE ("ehr_code");



ALTER TABLE ONLY "public"."ehr_types"
    ADD CONSTRAINT "ehr_types_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."embedding_models"
    ADD CONSTRAINT "embedding_models_model_code_key" UNIQUE ("model_code");



ALTER TABLE ONLY "public"."embedding_models"
    ADD CONSTRAINT "embedding_models_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."extraction_accuracy_metrics"
    ADD CONSTRAINT "extraction_accuracy_metrics_extraction_id_key" UNIQUE ("extraction_id");



ALTER TABLE ONLY "public"."extraction_accuracy_metrics"
    ADD CONSTRAINT "extraction_accuracy_metrics_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."extraction_edit_history"
    ADD CONSTRAINT "extraction_edit_history_extraction_id_version_number_key" UNIQUE ("extraction_id", "version_number");



ALTER TABLE ONLY "public"."extraction_edit_history"
    ADD CONSTRAINT "extraction_edit_history_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."extraction_embeddings"
    ADD CONSTRAINT "extraction_embeddings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."extraction_photos"
    ADD CONSTRAINT "extraction_photos_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."extraction_relationships"
    ADD CONSTRAINT "extraction_relationships_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."extraction_segments"
    ADD CONSTRAINT "extraction_segments_extraction_segment_version_unique" UNIQUE ("extraction_id", "segment_code", "version_type");



ALTER TABLE ONLY "public"."extraction_segments"
    ADD CONSTRAINT "extraction_segments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."extraction_translations"
    ADD CONSTRAINT "extraction_translations_extraction_id_target_language_key" UNIQUE ("extraction_id", "target_language");



ALTER TABLE ONLY "public"."extraction_translations"
    ADD CONSTRAINT "extraction_translations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."followup_tracking"
    ADD CONSTRAINT "followup_tracking_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."guideline_ingestion_jobs"
    ADD CONSTRAINT "guideline_ingestion_jobs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hospital_ehr"
    ADD CONSTRAINT "hospital_ehr_hospital_id_ehr_integration_type_key" UNIQUE ("hospital_id", "ehr_integration_type");



ALTER TABLE ONLY "public"."hospital_ehr"
    ADD CONSTRAINT "hospital_ehr_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hospital_intervention_pricing"
    ADD CONSTRAINT "hospital_intervention_pricing_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hospital_investigation_lists"
    ADD CONSTRAINT "hospital_investigation_lists_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hospital_medicine_lists"
    ADD CONSTRAINT "hospital_medicine_lists_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hospital_specialty_patterns"
    ADD CONSTRAINT "hospital_specialty_patterns_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hospitals"
    ADD CONSTRAINT "hospitals_hospital_code_key" UNIQUE ("hospital_code");



ALTER TABLE ONLY "public"."hospitals"
    ADD CONSTRAINT "hospitals_hospital_name_key" UNIQUE ("hospital_name");



ALTER TABLE ONLY "public"."hospitals"
    ADD CONSTRAINT "hospitals_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."intervention_definitions"
    ADD CONSTRAINT "intervention_definitions_code_unique" UNIQUE ("intervention_code");



ALTER TABLE ONLY "public"."intervention_definitions"
    ADD CONSTRAINT "intervention_definitions_intervention_code_key" UNIQUE ("intervention_code");



ALTER TABLE ONLY "public"."intervention_definitions"
    ADD CONSTRAINT "intervention_definitions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."intervention_outcomes"
    ADD CONSTRAINT "intervention_outcomes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."investigation_list_uploads"
    ADD CONSTRAINT "investigation_list_uploads_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."investigation_match_log"
    ADD CONSTRAINT "investigation_match_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."llm_usage_log"
    ADD CONSTRAINT "llm_usage_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."medical_extractions"
    ADD CONSTRAINT "medical_extractions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."medicine_list_uploads"
    ADD CONSTRAINT "medicine_list_uploads_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."medicine_match_log"
    ADD CONSTRAINT "medicine_match_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."models_master"
    ADD CONSTRAINT "models_master_model_id_key" UNIQUE ("model_id");



ALTER TABLE ONLY "public"."models_master"
    ADD CONSTRAINT "models_master_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."nurse_doctors"
    ADD CONSTRAINT "nurse_doctors_nurse_id_doctor_id_key" UNIQUE ("nurse_id", "doctor_id");



ALTER TABLE ONLY "public"."nurse_doctors"
    ADD CONSTRAINT "nurse_doctors_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."nurse_templates"
    ADD CONSTRAINT "nurse_templates_nurse_id_template_id_key" UNIQUE ("nurse_id", "template_id");



ALTER TABLE ONLY "public"."nurse_templates"
    ADD CONSTRAINT "nurse_templates_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."nurses"
    ADD CONSTRAINT "nurses_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."nurses"
    ADD CONSTRAINT "nurses_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."other_clinical_needs"
    ADD CONSTRAINT "other_clinical_needs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."patient_dropoff_risk"
    ADD CONSTRAINT "patient_dropoff_risk_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."patient_interventions"
    ADD CONSTRAINT "patient_interventions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."patient_sharing"
    ADD CONSTRAINT "patient_sharing_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."patients"
    ADD CONSTRAINT "patients_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."phi_audit_log"
    ADD CONSTRAINT "phi_audit_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."procedure_fee_master"
    ADD CONSTRAINT "procedure_fee_master_hospital_id_procedure_name_key" UNIQUE ("hospital_id", "procedure_name");



ALTER TABLE ONLY "public"."procedure_fee_master"
    ADD CONSTRAINT "procedure_fee_master_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."processing_jobs"
    ADD CONSTRAINT "processing_jobs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."processing_jobs"
    ADD CONSTRAINT "processing_jobs_submission_id_key" UNIQUE ("submission_id");



ALTER TABLE ONLY "public"."processing_modes"
    ADD CONSTRAINT "processing_modes_mode_code_key" UNIQUE ("mode_code");



ALTER TABLE ONLY "public"."processing_modes"
    ADD CONSTRAINT "processing_modes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."qa_engine_settings"
    ADD CONSTRAINT "qa_engine_settings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."qa_query_history"
    ADD CONSTRAINT "qa_query_history_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."radiology_plan_library"
    ADD CONSTRAINT "radiology_plan_library_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."radiology_plan_library"
    ADD CONSTRAINT "radiology_plan_library_template_id_plan_code_key" UNIQUE ("template_id", "plan_code");



ALTER TABLE ONLY "public"."radiology_toxicity_library"
    ADD CONSTRAINT "radiology_toxicity_library_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."radiology_toxicity_library"
    ADD CONSTRAINT "radiology_toxicity_library_template_id_toxicity_code_key" UNIQUE ("template_id", "toxicity_code");



ALTER TABLE ONLY "public"."realtime_extraction_responses"
    ADD CONSTRAINT "realtime_extraction_responses_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."realtime_extraction_responses"
    ADD CONSTRAINT "realtime_extraction_responses_submission_id_key" UNIQUE ("submission_id");



ALTER TABLE ONLY "public"."recording_sessions"
    ADD CONSTRAINT "recording_sessions_correlation_id_key" UNIQUE ("correlation_id");



ALTER TABLE ONLY "public"."recording_sessions"
    ADD CONSTRAINT "recording_sessions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."refresh_tokens"
    ADD CONSTRAINT "refresh_tokens_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."room_rate_master"
    ADD CONSTRAINT "room_rate_master_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."segment_definitions"
    ADD CONSTRAINT "segment_definitions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."segment_embeddings"
    ADD CONSTRAINT "segment_embeddings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."templates"
    ADD CONSTRAINT "segment_presets_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."templates"
    ADD CONSTRAINT "segment_presets_preset_code_key" UNIQUE ("template_code");



ALTER TABLE ONLY "public"."session_audit_log"
    ADD CONSTRAINT "session_audit_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."specialty_benchmarks"
    ADD CONSTRAINT "specialty_benchmarks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."specialty_benchmarks"
    ADD CONSTRAINT "specialty_benchmarks_specialty_key" UNIQUE ("specialty");



ALTER TABLE ONLY "public"."system_prompt_components"
    ADD CONSTRAINT "system_prompt_components_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."system_prompt_config_components"
    ADD CONSTRAINT "system_prompt_config_components_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."system_prompt_configurations"
    ADD CONSTRAINT "system_prompt_configurations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."temp_audio_files"
    ADD CONSTRAINT "temp_audio_files_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."template_ehr"
    ADD CONSTRAINT "template_ehr_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."template_ehr"
    ADD CONSTRAINT "template_ehr_template_id_ehr_type_id_key" UNIQUE ("template_id", "ehr_type_id");



ALTER TABLE ONLY "public"."template_segments"
    ADD CONSTRAINT "template_segments_unique" UNIQUE ("template_id", "segment_id");



ALTER TABLE ONLY "public"."template_standard_texts"
    ADD CONSTRAINT "template_standard_texts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."template_standard_texts"
    ADD CONSTRAINT "template_standard_texts_template_id_key_key" UNIQUE ("template_id", "key");



ALTER TABLE ONLY "public"."triage_conflict_log"
    ADD CONSTRAINT "triage_conflict_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."triage_feedback"
    ADD CONSTRAINT "triage_feedback_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."triage_layer_config"
    ADD CONSTRAINT "triage_layer_config_layer_code_key" UNIQUE ("layer_code");



ALTER TABLE ONLY "public"."triage_layer_config"
    ADD CONSTRAINT "triage_layer_config_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."triage_suggestion_log"
    ADD CONSTRAINT "triage_suggestion_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."allied_health_needs"
    ADD CONSTRAINT "unique_allied_needs_extraction" UNIQUE ("extraction_id");



ALTER TABLE ONLY "public"."care_quality_risk"
    ADD CONSTRAINT "unique_care_quality_extraction" UNIQUE ("extraction_id");



ALTER TABLE ONLY "public"."clinical_chunk_embeddings"
    ADD CONSTRAINT "unique_chunk_embedding" UNIQUE ("chunk_id", "embedding_model");



ALTER TABLE ONLY "public"."system_prompt_components"
    ADD CONSTRAINT "unique_component_code_version" UNIQUE ("component_code", "content_version");



ALTER TABLE ONLY "public"."system_prompt_configurations"
    ADD CONSTRAINT "unique_config_code_version" UNIQUE ("config_code", "config_version");



ALTER TABLE ONLY "public"."system_prompt_config_components"
    ADD CONSTRAINT "unique_config_component" UNIQUE ("config_id", "component_id");



ALTER TABLE ONLY "public"."system_prompt_config_components"
    ADD CONSTRAINT "unique_config_order" UNIQUE ("config_id", "display_order");



ALTER TABLE ONLY "public"."consultation_type_system_prompts"
    ADD CONSTRAINT "unique_consultation_config" UNIQUE ("consultation_type_id", "system_prompt_config_id");



ALTER TABLE ONLY "public"."doctor_layer_preferences"
    ADD CONSTRAINT "unique_doctor_layer_prefs" UNIQUE ("doctor_id");



ALTER TABLE ONLY "public"."doctor_practice_styles"
    ADD CONSTRAINT "unique_doctor_practice_style" UNIQUE ("doctor_id");



ALTER TABLE ONLY "public"."patient_dropoff_risk"
    ADD CONSTRAINT "unique_dropoff_extraction" UNIQUE ("extraction_id");



ALTER TABLE ONLY "public"."followup_tracking"
    ADD CONSTRAINT "unique_extraction_followup" UNIQUE ("extraction_id");



ALTER TABLE ONLY "public"."consultation_insights"
    ADD CONSTRAINT "unique_extraction_insights" UNIQUE ("extraction_id");



ALTER TABLE ONLY "public"."clinical_guideline_embeddings"
    ADD CONSTRAINT "unique_guideline_embedding" UNIQUE ("guideline_id", "embedding_model");



ALTER TABLE ONLY "public"."hospital_intervention_pricing"
    ADD CONSTRAINT "unique_hospital_intervention" UNIQUE ("hospital_id", "intervention_type");



ALTER TABLE ONLY "public"."hospital_specialty_patterns"
    ADD CONSTRAINT "unique_hospital_specialty" UNIQUE ("hospital_id", "specialty");



ALTER TABLE ONLY "public"."intervention_outcomes"
    ADD CONSTRAINT "unique_intervention_outcome" UNIQUE ("intervention_id");



ALTER TABLE ONLY "public"."extraction_relationships"
    ADD CONSTRAINT "unique_merged_source_pair" UNIQUE ("merged_extraction_id", "source_extraction_id");



ALTER TABLE ONLY "public"."other_clinical_needs"
    ADD CONSTRAINT "unique_needs_extraction" UNIQUE ("extraction_id");



ALTER TABLE ONLY "public"."clinical_severity_assessments"
    ADD CONSTRAINT "unique_severity_extraction" UNIQUE ("extraction_id");



ALTER TABLE ONLY "public"."doctor_investigations"
    ADD CONSTRAINT "uq_doctor_investigation" UNIQUE ("doctor_id", "normalized_name");



ALTER TABLE ONLY "public"."doctor_medicines"
    ADD CONSTRAINT "uq_doctor_medicine" UNIQUE ("doctor_id", "normalized_name");



ALTER TABLE ONLY "public"."hospital_investigation_lists"
    ADD CONSTRAINT "uq_hospital_investigation" UNIQUE ("hospital_id", "normalized_name");



ALTER TABLE ONLY "public"."hospital_medicine_lists"
    ADD CONSTRAINT "uq_hospital_medicine" UNIQUE ("hospital_id", "normalized_name");



CREATE UNIQUE INDEX "consultation_type_segment_def_consultation_type_id_segment__key" ON "public"."consultation_type_segments" USING "btree" ("consultation_type_id", "segment_code");



CREATE INDEX "idx_accuracy_computed_at" ON "public"."extraction_accuracy_metrics" USING "btree" ("computed_at");



CREATE INDEX "idx_accuracy_doctor" ON "public"."extraction_accuracy_metrics" USING "btree" ("doctor_id");



CREATE INDEX "idx_accuracy_extraction" ON "public"."extraction_accuracy_metrics" USING "btree" ("extraction_id");



CREATE INDEX "idx_admin_action_action" ON "public"."admin_action_log" USING "btree" ("action", "created_at" DESC);



CREATE INDEX "idx_admin_action_admin" ON "public"."admin_action_log" USING "btree" ("admin_id", "created_at" DESC);



CREATE INDEX "idx_admin_action_email" ON "public"."admin_action_log" USING "btree" ("admin_email", "created_at" DESC);



CREATE INDEX "idx_admin_action_resource" ON "public"."admin_action_log" USING "btree" ("resource_type", "resource_id", "created_at" DESC);



CREATE INDEX "idx_admin_action_time" ON "public"."admin_action_log" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_admin_users_active" ON "public"."admin_users" USING "btree" ("is_active") WHERE ("is_active" = true);



CREATE INDEX "idx_admin_users_auth_user" ON "public"."admin_users" USING "btree" ("auth_user_id");



CREATE INDEX "idx_admin_users_email" ON "public"."admin_users" USING "btree" ("email");



CREATE INDEX "idx_admin_users_hospital_id" ON "public"."admin_users" USING "btree" ("hospital_id") WHERE ("hospital_id" IS NOT NULL);



CREATE INDEX "idx_allied_created" ON "public"."allied_health_needs" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_allied_doctor" ON "public"."allied_health_needs" USING "btree" ("doctor_id");



CREATE INDEX "idx_allied_education" ON "public"."allied_health_needs" USING "btree" ("is_treatment_education") WHERE ("is_treatment_education" = true);



CREATE INDEX "idx_allied_extraction" ON "public"."allied_health_needs" USING "btree" ("extraction_id");



CREATE INDEX "idx_allied_health_consultation_insights" ON "public"."allied_health_needs" USING "btree" ("consultation_insights_id");



CREATE INDEX "idx_allied_homecare" ON "public"."allied_health_needs" USING "btree" ("is_homecare") WHERE ("is_homecare" = true);



CREATE INDEX "idx_allied_mental" ON "public"."allied_health_needs" USING "btree" ("is_mental_health") WHERE ("is_mental_health" = true);



CREATE INDEX "idx_allied_nutrition" ON "public"."allied_health_needs" USING "btree" ("is_nutritional_health") WHERE ("is_nutritional_health" = true);



CREATE INDEX "idx_allied_patient" ON "public"."allied_health_needs" USING "btree" ("patient_id");



CREATE INDEX "idx_allied_physio" ON "public"."allied_health_needs" USING "btree" ("is_physiotherapy") WHERE ("is_physiotherapy" = true);



CREATE INDEX "idx_allied_priority" ON "public"."allied_health_needs" USING "btree" ("priority_level") WHERE ("priority_level" <> 'NONE'::"text");



CREATE INDEX "idx_allied_rehab_cardiac" ON "public"."allied_health_needs" USING "btree" ("is_rehab_cardiac") WHERE ("is_rehab_cardiac" = true);



CREATE INDEX "idx_allied_rehab_common" ON "public"."allied_health_needs" USING "btree" ("is_rehab_common") WHERE ("is_rehab_common" = true);



CREATE INDEX "idx_allied_sleep" ON "public"."allied_health_needs" USING "btree" ("is_sleep_therapy") WHERE ("is_sleep_therapy" = true);



CREATE INDEX "idx_allied_wellness" ON "public"."allied_health_needs" USING "btree" ("is_wellness") WHERE ("is_wellness" = true);



CREATE INDEX "idx_api_clients_active" ON "public"."api_clients" USING "btree" ("is_active") WHERE ("is_active" = true);



CREATE INDEX "idx_api_clients_api_key_prefix" ON "public"."api_clients" USING "btree" ("api_key_prefix");



CREATE INDEX "idx_api_clients_hospital" ON "public"."api_clients" USING "btree" ("hospital_id");



CREATE INDEX "idx_api_clients_type" ON "public"."api_clients" USING "btree" ("client_type");



CREATE INDEX "idx_api_usage_client_time" ON "public"."api_client_usage" USING "btree" ("client_id", "created_at" DESC);



CREATE INDEX "idx_api_usage_created" ON "public"."api_client_usage" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_audio_chunks_session_chunk" ON "public"."audio_chunks" USING "btree" ("session_id", "chunk_index");



CREATE INDEX "idx_audio_chunks_session_id" ON "public"."audio_chunks" USING "btree" ("session_id");



CREATE INDEX "idx_bill_line_items_bill" ON "public"."bill_line_items" USING "btree" ("bill_id");



CREATE INDEX "idx_bill_line_items_category" ON "public"."bill_line_items" USING "btree" ("category");



CREATE INDEX "idx_bills_extraction" ON "public"."bills" USING "btree" ("extraction_id");



CREATE UNIQUE INDEX "idx_bills_extraction_unique" ON "public"."bills" USING "btree" ("extraction_id") WHERE (("extraction_id" IS NOT NULL) AND (("bill_status")::"text" <> 'superseded'::"text"));



CREATE INDEX "idx_bills_hospital" ON "public"."bills" USING "btree" ("hospital_id");



CREATE INDEX "idx_bills_patient" ON "public"."bills" USING "btree" ("patient_id");



CREATE INDEX "idx_bills_status" ON "public"."bills" USING "btree" ("bill_status");



CREATE INDEX "idx_bills_visit_id" ON "public"."bills" USING "btree" ("visit_id") WHERE ("visit_id" IS NOT NULL);



CREATE INDEX "idx_care_quality_created" ON "public"."care_quality_risk" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_care_quality_critical" ON "public"."care_quality_risk" USING "btree" ("risk_level") WHERE ("risk_level" = ANY (ARRAY['HIGH'::"text", 'CRITICAL'::"text"]));



CREATE INDEX "idx_care_quality_doctor" ON "public"."care_quality_risk" USING "btree" ("doctor_id");



CREATE INDEX "idx_care_quality_extraction" ON "public"."care_quality_risk" USING "btree" ("extraction_id");



CREATE INDEX "idx_care_quality_patient" ON "public"."care_quality_risk" USING "btree" ("patient_id");



CREATE INDEX "idx_care_quality_risk_level" ON "public"."care_quality_risk" USING "btree" ("risk_level");



CREATE INDEX "idx_care_quality_score" ON "public"."care_quality_risk" USING "btree" ("care_quality_score" DESC);



CREATE INDEX "idx_chunk_embeddings_hnsw" ON "public"."clinical_chunk_embeddings" USING "hnsw" ("embedding" "extensions"."vector_cosine_ops") WITH ("m"='16', "ef_construction"='64');



CREATE INDEX "idx_chunk_embeddings_model" ON "public"."clinical_chunk_embeddings" USING "btree" ("embedding_model");



CREATE INDEX "idx_chunks_care_levels" ON "public"."clinical_chunks" USING "gin" ("care_levels");



CREATE INDEX "idx_chunks_comorbidity" ON "public"."clinical_chunks" USING "btree" ("comorbidity") WHERE ("comorbidity" IS NOT NULL);



CREATE INDEX "idx_chunks_condition" ON "public"."clinical_chunks" USING "btree" ("condition_id");



CREATE INDEX "idx_chunks_contraindications" ON "public"."clinical_chunks" USING "gin" ("contraindications");



CREATE INDEX "idx_chunks_drug_classes" ON "public"."clinical_chunks" USING "gin" ("drug_classes");



CREATE INDEX "idx_chunks_drug_names" ON "public"."clinical_chunks" USING "gin" ("drug_names");



CREATE INDEX "idx_chunks_emergency" ON "public"."clinical_chunks" USING "btree" ("has_emergency_triggers") WHERE ("has_emergency_triggers" = true);



CREATE INDEX "idx_chunks_fts" ON "public"."clinical_chunks" USING "gin" ("to_tsvector"('"english"'::"regconfig", "content_text"));



CREATE INDEX "idx_chunks_red_flags" ON "public"."clinical_chunks" USING "btree" ("has_red_flags") WHERE ("has_red_flags" = true);



CREATE INDEX "idx_chunks_type" ON "public"."clinical_chunks" USING "btree" ("chunk_type");



CREATE INDEX "idx_chunks_urgency" ON "public"."clinical_chunks" USING "btree" ("urgency_default") WHERE ("urgency_default" IS NOT NULL);



CREATE INDEX "idx_clinical_guidelines_fts" ON "public"."clinical_guidelines" USING "gin" ("to_tsvector"('"english"'::"regconfig", "chunk_text"));



CREATE INDEX "idx_clinical_guidelines_presentations" ON "public"."clinical_guidelines" USING "gin" ("presentations") WHERE ("is_active" = true);



CREATE INDEX "idx_clinical_guidelines_source" ON "public"."clinical_guidelines" USING "btree" ("source_name", "source_organization");



CREATE INDEX "idx_clinical_guidelines_specialty" ON "public"."clinical_guidelines" USING "btree" ("specialty") WHERE ("is_active" = true);



CREATE INDEX "idx_clinical_guidelines_topics" ON "public"."clinical_guidelines" USING "gin" ("topics") WHERE ("is_active" = true);



CREATE INDEX "idx_clinical_needs_consultation_insights" ON "public"."other_clinical_needs" USING "btree" ("consultation_insights_id");



CREATE INDEX "idx_condition_ingestion_status" ON "public"."clinical_condition_ingestion_jobs" USING "btree" ("status", "created_at" DESC);



CREATE INDEX "idx_conditions_aliases" ON "public"."clinical_conditions" USING "gin" ("aliases");



CREATE INDEX "idx_conditions_document_type" ON "public"."clinical_conditions" USING "btree" ("document_type");



CREATE INDEX "idx_conditions_icd" ON "public"."clinical_conditions" USING "gin" ("icd_codes");



CREATE INDEX "idx_conditions_name_search" ON "public"."clinical_conditions" USING "gin" ("to_tsvector"('"english"'::"regconfig", "name"));



CREATE INDEX "idx_conditions_specialty" ON "public"."clinical_conditions" USING "btree" ("specialty") WHERE ("is_active" = true);



CREATE INDEX "idx_consultation_insights_created" ON "public"."consultation_insights" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_consultation_insights_doctor" ON "public"."consultation_insights" USING "btree" ("doctor_id");



CREATE INDEX "idx_consultation_insights_extraction" ON "public"."consultation_insights" USING "btree" ("extraction_id");



CREATE INDEX "idx_consultation_insights_patient" ON "public"."consultation_insights" USING "btree" ("patient_id");



CREATE INDEX "idx_consultation_type_segments_name" ON "public"."consultation_type_segments" USING "btree" ("consultation_type_name");



CREATE INDEX "idx_consultation_type_segments_segment_id" ON "public"."consultation_type_segments" USING "btree" ("segment_id");



CREATE INDEX "idx_consultation_types_active" ON "public"."consultation_types" USING "btree" ("is_active");



CREATE INDEX "idx_consultation_types_code" ON "public"."consultation_types" USING "btree" ("type_code");



CREATE INDEX "idx_consultation_types_visible_doctors" ON "public"."consultation_types" USING "gin" ("visible_to_doctors");



CREATE INDEX "idx_consultation_types_visible_hospitals" ON "public"."consultation_types" USING "gin" ("visible_to_hospitals");



CREATE INDEX "idx_consultation_types_visible_specializations" ON "public"."consultation_types" USING "gin" ("visible_to_specializations");



CREATE INDEX "idx_ctsp_active" ON "public"."consultation_type_system_prompts" USING "btree" ("is_active") WHERE ("is_active" = true);



CREATE INDEX "idx_ctsp_codes" ON "public"."consultation_type_system_prompts" USING "btree" ("consultation_type_code", "config_code");



CREATE INDEX "idx_ctsp_config" ON "public"."consultation_type_system_prompts" USING "btree" ("system_prompt_config_id");



CREATE INDEX "idx_ctsp_consultation_type" ON "public"."consultation_type_system_prompts" USING "btree" ("consultation_type_id");



CREATE UNIQUE INDEX "idx_ctsp_single_active" ON "public"."consultation_type_system_prompts" USING "btree" ("consultation_type_id") WHERE ("is_active" = true);



CREATE INDEX "idx_ddp_doctor_id" ON "public"."doctor_doctor_patients" USING "btree" ("doctor_id") WHERE ("is_active" = true);



CREATE UNIQUE INDEX "idx_ddp_unique_pair" ON "public"."doctor_doctor_patients" USING "btree" ("doctor_id", "linked_doctor_id");



CREATE INDEX "idx_doctor_investigations_category" ON "public"."doctor_investigations" USING "btree" ("doctor_id", "category");



CREATE INDEX "idx_doctor_investigations_doctor_id" ON "public"."doctor_investigations" USING "btree" ("doctor_id") WHERE ("is_active" = true);



CREATE INDEX "idx_doctor_investigations_external_id" ON "public"."doctor_investigations" USING "btree" ("doctor_id", "external_id") WHERE ("external_id" IS NOT NULL);



CREATE INDEX "idx_doctor_investigations_normalized" ON "public"."doctor_investigations" USING "btree" ("doctor_id", "normalized_name");



CREATE INDEX "idx_doctor_investigations_search" ON "public"."doctor_investigations" USING "gin" ("search_tokens");



CREATE INDEX "idx_doctor_investigations_type" ON "public"."doctor_investigations" USING "btree" ("doctor_id", "investigation_type");



CREATE INDEX "idx_doctor_layer_preferences_doctor" ON "public"."doctor_layer_preferences" USING "btree" ("doctor_id");



CREATE INDEX "idx_doctor_medicines_category" ON "public"."doctor_medicines" USING "btree" ("doctor_id", "category");



CREATE INDEX "idx_doctor_medicines_doctor_id" ON "public"."doctor_medicines" USING "btree" ("doctor_id") WHERE ("is_active" = true);



CREATE INDEX "idx_doctor_medicines_external_id" ON "public"."doctor_medicines" USING "btree" ("doctor_id", "external_id") WHERE ("external_id" IS NOT NULL);



CREATE INDEX "idx_doctor_medicines_normalized" ON "public"."doctor_medicines" USING "btree" ("doctor_id", "normalized_name");



CREATE INDEX "idx_doctor_medicines_search" ON "public"."doctor_medicines" USING "gin" ("search_tokens");



CREATE INDEX "idx_doctor_medicines_snomed" ON "public"."doctor_medicines" USING "btree" ("snomed_code") WHERE ("snomed_code" IS NOT NULL);



CREATE INDEX "idx_doctor_practice_styles_intensity" ON "public"."doctor_practice_styles" USING "btree" ("practice_intensity");



CREATE INDEX "idx_doctor_practice_styles_specialty" ON "public"."doctor_practice_styles" USING "btree" ("specialty");



CREATE INDEX "idx_doctor_templates_active" ON "public"."doctor_templates" USING "btree" ("doctor_id", "is_active") WHERE ("is_active" = true);



CREATE INDEX "idx_doctor_templates_doctor_id" ON "public"."doctor_templates" USING "btree" ("doctor_id");



CREATE INDEX "idx_doctor_templates_template_id" ON "public"."doctor_templates" USING "btree" ("template_id");



CREATE INDEX "idx_doctors_auth_user_id" ON "public"."doctors" USING "btree" ("auth_user_id");



CREATE INDEX "idx_doctors_default_template" ON "public"."doctors" USING "btree" ("default_template_id");



CREATE INDEX "idx_doctors_ehr_type" ON "public"."doctors" USING "btree" ("ehr_type_id");



CREATE INDEX "idx_doctors_email" ON "public"."doctors" USING "btree" ("email");



CREATE INDEX "idx_doctors_hospital" ON "public"."doctors" USING "btree" ("hospital_id");



CREATE INDEX "idx_doctors_is_active" ON "public"."doctors" USING "btree" ("is_active");



CREATE INDEX "idx_dropoff_consultation_insights" ON "public"."patient_dropoff_risk" USING "btree" ("consultation_insights_id");



CREATE INDEX "idx_dropoff_created_at" ON "public"."patient_dropoff_risk" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_dropoff_doctor" ON "public"."patient_dropoff_risk" USING "btree" ("doctor_id");



CREATE INDEX "idx_dropoff_extraction" ON "public"."patient_dropoff_risk" USING "btree" ("extraction_id");



CREATE INDEX "idx_dropoff_high_critical" ON "public"."patient_dropoff_risk" USING "btree" ("risk_level", "created_at" DESC) WHERE ("risk_level" = ANY (ARRAY['HIGH'::"text", 'CRITICAL'::"text"]));



CREATE INDEX "idx_dropoff_patient" ON "public"."patient_dropoff_risk" USING "btree" ("patient_id");



CREATE INDEX "idx_dropoff_probability" ON "public"."patient_dropoff_risk" USING "btree" ("dropoff_probability" DESC);



CREATE INDEX "idx_dropoff_risk_level" ON "public"."patient_dropoff_risk" USING "btree" ("risk_level");



CREATE INDEX "idx_edit_history_edited_at" ON "public"."extraction_edit_history" USING "btree" ("edited_at");



CREATE INDEX "idx_edit_history_extraction" ON "public"."extraction_edit_history" USING "btree" ("extraction_id");



CREATE INDEX "idx_ehr_types_active" ON "public"."ehr_types" USING "btree" ("is_active") WHERE ("is_active" = true);



CREATE INDEX "idx_ehr_types_code" ON "public"."ehr_types" USING "btree" ("ehr_code");



CREATE INDEX "idx_embedding_models_active" ON "public"."embedding_models" USING "btree" ("is_active", "provider");



CREATE UNIQUE INDEX "idx_embedding_models_default" ON "public"."embedding_models" USING "btree" ("is_default") WHERE ("is_default" = true);



CREATE INDEX "idx_extraction_embeddings_doctor" ON "public"."extraction_embeddings" USING "btree" ("doctor_id", "model_id");



CREATE INDEX "idx_extraction_embeddings_hospital" ON "public"."extraction_embeddings" USING "btree" ("hospital_id", "model_id");



CREATE UNIQUE INDEX "idx_extraction_embeddings_unique" ON "public"."extraction_embeddings" USING "btree" ("extraction_id", "model_id");



CREATE INDEX "idx_extraction_embeddings_vector_hnsw" ON "public"."extraction_embeddings" USING "hnsw" ("embedding" "extensions"."vector_cosine_ops") WITH ("m"='16', "ef_construction"='64');



CREATE INDEX "idx_extraction_photos_extraction_id" ON "public"."extraction_photos" USING "btree" ("extraction_id");



CREATE INDEX "idx_extraction_relationships_created_at" ON "public"."extraction_relationships" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_extraction_relationships_merged" ON "public"."extraction_relationships" USING "btree" ("merged_extraction_id");



CREATE INDEX "idx_extraction_relationships_merged_order" ON "public"."extraction_relationships" USING "btree" ("merged_extraction_id", "merge_order");



CREATE INDEX "idx_extraction_relationships_source" ON "public"."extraction_relationships" USING "btree" ("source_extraction_id");



CREATE INDEX "idx_extraction_segments_extraction_version" ON "public"."extraction_segments" USING "btree" ("extraction_id", "version_type");



CREATE INDEX "idx_extraction_segments_version_type" ON "public"."extraction_segments" USING "btree" ("version_type");



CREATE INDEX "idx_extraction_translations_extraction_id" ON "public"."extraction_translations" USING "btree" ("extraction_id");



CREATE INDEX "idx_extractions_consultation_type" ON "public"."medical_extractions" USING "btree" ("consultation_type_id");



CREATE INDEX "idx_extractions_created_at" ON "public"."medical_extractions" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_extractions_patient" ON "public"."medical_extractions" USING "btree" ("patient_id", "created_at" DESC);



CREATE INDEX "idx_extractions_session" ON "public"."medical_extractions" USING "btree" ("session_id");



CREATE INDEX "idx_extractions_user" ON "public"."medical_extractions" USING "btree" ("doctor_id", "created_at" DESC);



CREATE INDEX "idx_followup_doctor" ON "public"."followup_tracking" USING "btree" ("doctor_id", "status");



CREATE INDEX "idx_followup_expected_date" ON "public"."followup_tracking" USING "btree" ("expected_followup_date") WHERE ((("status")::"text" = 'PENDING'::"text") AND ("expected_followup_date" IS NOT NULL));



CREATE INDEX "idx_followup_hospital" ON "public"."followup_tracking" USING "btree" ("hospital_id", "status");



CREATE INDEX "idx_followup_missed" ON "public"."followup_tracking" USING "btree" ("status", "expected_followup_date") WHERE (("status")::"text" = 'MISSED'::"text");



CREATE INDEX "idx_followup_patient" ON "public"."followup_tracking" USING "btree" ("patient_id");



CREATE INDEX "idx_followup_status" ON "public"."followup_tracking" USING "btree" ("status");



CREATE INDEX "idx_guideline_embeddings_hnsw" ON "public"."clinical_guideline_embeddings" USING "hnsw" ("embedding" "extensions"."vector_cosine_ops") WITH ("m"='16', "ef_construction"='64');



CREATE INDEX "idx_guideline_embeddings_model" ON "public"."clinical_guideline_embeddings" USING "btree" ("embedding_model");



CREATE INDEX "idx_guideline_ingestion_status" ON "public"."guideline_ingestion_jobs" USING "btree" ("status", "created_at" DESC);



CREATE INDEX "idx_hospital_ehr_ehr_type_id" ON "public"."hospital_ehr" USING "btree" ("ehr_type_id");



CREATE INDEX "idx_hospital_ehr_enabled" ON "public"."hospital_ehr" USING "btree" ("hospital_id", "ehr_integration_type") WHERE ("is_enabled" = true);



CREATE INDEX "idx_hospital_ehr_hospital" ON "public"."hospital_ehr" USING "btree" ("hospital_id");



CREATE UNIQUE INDEX "idx_hospital_ehr_one_default" ON "public"."hospital_ehr" USING "btree" ("hospital_id") WHERE ("is_default" = true);



CREATE INDEX "idx_hospital_ehr_type" ON "public"."hospital_ehr" USING "btree" ("ehr_integration_type");



CREATE INDEX "idx_hospital_intervention_pricing_active" ON "public"."hospital_intervention_pricing" USING "btree" ("hospital_id", "is_active") WHERE ("is_active" = true);



CREATE INDEX "idx_hospital_intervention_pricing_hospital_id" ON "public"."hospital_intervention_pricing" USING "btree" ("hospital_id");



CREATE INDEX "idx_hospital_intervention_pricing_type" ON "public"."hospital_intervention_pricing" USING "btree" ("intervention_type");



CREATE INDEX "idx_hospital_investigation_lists_external_id" ON "public"."hospital_investigation_lists" USING "btree" ("hospital_id", "external_id") WHERE ("external_id" IS NOT NULL);



CREATE INDEX "idx_hospital_investigations_category" ON "public"."hospital_investigation_lists" USING "btree" ("hospital_id", "category");



CREATE INDEX "idx_hospital_investigations_hospital_id" ON "public"."hospital_investigation_lists" USING "btree" ("hospital_id") WHERE ("is_active" = true);



CREATE INDEX "idx_hospital_investigations_normalized" ON "public"."hospital_investigation_lists" USING "btree" ("hospital_id", "normalized_name");



CREATE INDEX "idx_hospital_investigations_search" ON "public"."hospital_investigation_lists" USING "gin" ("search_tokens");



CREATE INDEX "idx_hospital_investigations_type" ON "public"."hospital_investigation_lists" USING "btree" ("hospital_id", "investigation_type");



CREATE INDEX "idx_hospital_medicine_lists_external_id" ON "public"."hospital_medicine_lists" USING "btree" ("hospital_id", "external_id") WHERE ("external_id" IS NOT NULL);



CREATE INDEX "idx_hospital_medicines_category" ON "public"."hospital_medicine_lists" USING "btree" ("hospital_id", "category");



CREATE INDEX "idx_hospital_medicines_hospital_id" ON "public"."hospital_medicine_lists" USING "btree" ("hospital_id") WHERE ("is_active" = true);



CREATE INDEX "idx_hospital_medicines_normalized" ON "public"."hospital_medicine_lists" USING "btree" ("hospital_id", "normalized_name");



CREATE INDEX "idx_hospital_medicines_search" ON "public"."hospital_medicine_lists" USING "gin" ("search_tokens");



CREATE INDEX "idx_hospital_specialty_patterns_hospital" ON "public"."hospital_specialty_patterns" USING "btree" ("hospital_id");



CREATE INDEX "idx_hospital_specialty_patterns_specialty" ON "public"."hospital_specialty_patterns" USING "btree" ("specialty");



CREATE INDEX "idx_hospitals_active" ON "public"."hospitals" USING "btree" ("is_active");



CREATE INDEX "idx_hospitals_code" ON "public"."hospitals" USING "btree" ("hospital_code");



CREATE INDEX "idx_hospitals_default_template" ON "public"."hospitals" USING "btree" ("default_template_id");



CREATE INDEX "idx_insights_access_signals" ON "public"."consultation_insights" USING "gin" ("access_logistics_signals");



CREATE INDEX "idx_insights_competitor_signals" ON "public"."consultation_insights" USING "gin" ("competitor_signals");



CREATE INDEX "idx_insights_medication_signals" ON "public"."consultation_insights" USING "gin" ("medication_signals");



CREATE INDEX "idx_insights_severity_signals" ON "public"."consultation_insights" USING "gin" ("clinical_severity_signals");



CREATE INDEX "idx_intervention_definitions_category" ON "public"."intervention_definitions" USING "btree" ("category");



CREATE INDEX "idx_investigation_match_log_confidence" ON "public"."investigation_match_log" USING "btree" ("match_confidence");



CREATE INDEX "idx_investigation_match_log_created" ON "public"."investigation_match_log" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_investigation_match_log_doctor" ON "public"."investigation_match_log" USING "btree" ("doctor_id");



CREATE INDEX "idx_investigation_match_log_extraction" ON "public"."investigation_match_log" USING "btree" ("extraction_id");



CREATE INDEX "idx_investigation_match_log_feedback" ON "public"."investigation_match_log" USING "btree" ("doctor_id", "original_investigation_name", "feedback_status");



CREATE INDEX "idx_investigation_match_log_pending" ON "public"."investigation_match_log" USING "btree" ("doctor_id", "feedback_status") WHERE ("feedback_status" IS NULL);



CREATE INDEX "idx_investigation_match_log_submission" ON "public"."investigation_match_log" USING "btree" ("submission_id");



CREATE INDEX "idx_investigation_uploads_doctor" ON "public"."investigation_list_uploads" USING "btree" ("doctor_id") WHERE ("doctor_id" IS NOT NULL);



CREATE INDEX "idx_investigation_uploads_hospital" ON "public"."investigation_list_uploads" USING "btree" ("hospital_id") WHERE ("hospital_id" IS NOT NULL);



CREATE INDEX "idx_investigation_uploads_status" ON "public"."investigation_list_uploads" USING "btree" ("status");



CREATE INDEX "idx_llm_usage_cache_analysis" ON "public"."llm_usage_log" USING "btree" ("call_type", "cache_hit", "model");



CREATE INDEX "idx_llm_usage_call_type" ON "public"."llm_usage_log" USING "btree" ("call_type");



CREATE INDEX "idx_llm_usage_consultation_type" ON "public"."llm_usage_log" USING "btree" ("consultation_type_code") WHERE ("consultation_type_code" IS NOT NULL);



CREATE INDEX "idx_llm_usage_created_at" ON "public"."llm_usage_log" USING "btree" ("created_at");



CREATE INDEX "idx_llm_usage_doctor_id" ON "public"."llm_usage_log" USING "btree" ("doctor_id") WHERE ("doctor_id" IS NOT NULL);



CREATE INDEX "idx_llm_usage_extraction_id" ON "public"."llm_usage_log" USING "btree" ("extraction_id") WHERE ("extraction_id" IS NOT NULL);



CREATE INDEX "idx_llm_usage_log_api_client_created" ON "public"."llm_usage_log" USING "btree" ("api_client_id", "created_at");



CREATE INDEX "idx_llm_usage_log_api_client_id" ON "public"."llm_usage_log" USING "btree" ("api_client_id");



CREATE INDEX "idx_llm_usage_log_doctor_created" ON "public"."llm_usage_log" USING "btree" ("doctor_id", "created_at");



CREATE INDEX "idx_llm_usage_model" ON "public"."llm_usage_log" USING "btree" ("model");



CREATE INDEX "idx_llm_usage_session_id" ON "public"."llm_usage_log" USING "btree" ("session_id") WHERE ("session_id" IS NOT NULL);



CREATE INDEX "idx_medical_extractions_edit_count" ON "public"."medical_extractions" USING "btree" ("edit_count");



CREATE INDEX "idx_medical_extractions_emotion_status" ON "public"."medical_extractions" USING "btree" ("emotion_extraction_started", "emotion_extraction_completed", "emotion_extraction_failed") WHERE ("emotion_extraction_started" = true);



COMMENT ON INDEX "public"."idx_medical_extractions_emotion_status" IS 'Optimize queries for emotion extraction status tracking';



CREATE INDEX "idx_medical_extractions_is_continuation" ON "public"."medical_extractions" USING "btree" ("is_continuation") WHERE ("is_continuation" = true);



CREATE INDEX "idx_medical_extractions_is_merged" ON "public"."medical_extractions" USING "btree" ("is_merged") WHERE ("is_merged" = true);



CREATE INDEX "idx_medical_extractions_last_edited_at" ON "public"."medical_extractions" USING "btree" ("last_edited_at" DESC);



CREATE INDEX "idx_medical_extractions_merge_metadata" ON "public"."medical_extractions" USING "gin" ("merge_metadata");



CREATE INDEX "idx_medical_extractions_merged_into" ON "public"."medical_extractions" USING "btree" ("merged_into_extraction_id") WHERE ("merged_into_extraction_id" IS NOT NULL);



CREATE INDEX "idx_medical_extractions_metadata" ON "public"."medical_extractions" USING "gin" ("recording_metadata_json");



CREATE INDEX "idx_medical_extractions_parent_ids" ON "public"."medical_extractions" USING "gin" ("parent_extraction_ids") WHERE ("parent_extraction_ids" <> '{}'::"uuid"[]);



CREATE INDEX "idx_medical_extractions_patient_timeline" ON "public"."medical_extractions" USING "btree" ("patient_id", "created_at" DESC);



CREATE INDEX "idx_medical_extractions_submission_id" ON "public"."medical_extractions" USING "btree" ("submission_id");



CREATE INDEX "idx_medical_extractions_transcript_text_gin" ON "public"."medical_extractions" USING "gin" ("to_tsvector"('"english"'::"regconfig", "transcript_text"));



CREATE INDEX "idx_medicine_match_log_confidence" ON "public"."medicine_match_log" USING "btree" ("match_confidence");



CREATE INDEX "idx_medicine_match_log_created" ON "public"."medicine_match_log" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_medicine_match_log_doctor" ON "public"."medicine_match_log" USING "btree" ("doctor_id");



CREATE INDEX "idx_medicine_match_log_extraction" ON "public"."medicine_match_log" USING "btree" ("extraction_id");



CREATE INDEX "idx_medicine_match_log_feedback" ON "public"."medicine_match_log" USING "btree" ("doctor_id", "original_medicine_name", "feedback_status");



CREATE INDEX "idx_medicine_match_log_pending" ON "public"."medicine_match_log" USING "btree" ("doctor_id", "feedback_status") WHERE ("feedback_status" IS NULL);



CREATE INDEX "idx_medicine_match_log_submission" ON "public"."medicine_match_log" USING "btree" ("submission_id");



CREATE INDEX "idx_medicine_uploads_doctor" ON "public"."medicine_list_uploads" USING "btree" ("doctor_id");



CREATE INDEX "idx_medicine_uploads_status" ON "public"."medicine_list_uploads" USING "btree" ("status");



CREATE INDEX "idx_needs_extraction" ON "public"."other_clinical_needs" USING "btree" ("extraction_id");



CREATE INDEX "idx_needs_followup_diag" ON "public"."other_clinical_needs" USING "btree" ("is_followup_diagnostics") WHERE ("is_followup_diagnostics" = true);



CREATE INDEX "idx_needs_patient" ON "public"."other_clinical_needs" USING "btree" ("patient_id");



CREATE INDEX "idx_needs_priority_level" ON "public"."other_clinical_needs" USING "btree" ("priority_level") WHERE ("priority_level" <> 'NONE'::"text");



CREATE INDEX "idx_needs_recurring_diag" ON "public"."other_clinical_needs" USING "btree" ("is_recurring_diagnostics") WHERE ("is_recurring_diagnostics" = true);



CREATE INDEX "idx_needs_rx_refill" ON "public"."other_clinical_needs" USING "btree" ("is_rx_refill") WHERE ("is_rx_refill" = true);



CREATE INDEX "idx_nurse_doctors_doctor_id" ON "public"."nurse_doctors" USING "btree" ("doctor_id");



CREATE INDEX "idx_nurse_doctors_nurse_id" ON "public"."nurse_doctors" USING "btree" ("nurse_id");



CREATE INDEX "idx_nurse_templates_nurse_id" ON "public"."nurse_templates" USING "btree" ("nurse_id");



CREATE INDEX "idx_nurse_templates_template_id" ON "public"."nurse_templates" USING "btree" ("template_id");



CREATE INDEX "idx_nurses_default_template" ON "public"."nurses" USING "btree" ("default_template_id");



CREATE INDEX "idx_nurses_email" ON "public"."nurses" USING "btree" ("email");



CREATE INDEX "idx_nurses_hospital_id" ON "public"."nurses" USING "btree" ("hospital_id");



CREATE INDEX "idx_outcomes_completed" ON "public"."intervention_outcomes" USING "btree" ("status", "completed_at") WHERE (("status")::"text" = 'COMPLETED'::"text");



CREATE INDEX "idx_outcomes_generated" ON "public"."intervention_outcomes" USING "btree" ("generated_at" DESC);



CREATE INDEX "idx_outcomes_pending" ON "public"."intervention_outcomes" USING "btree" ("status") WHERE (("status")::"text" = 'PENDING'::"text");



CREATE INDEX "idx_outcomes_status" ON "public"."intervention_outcomes" USING "btree" ("status");



CREATE INDEX "idx_outcomes_status_updated" ON "public"."intervention_outcomes" USING "btree" ("status", "status_updated_at" DESC);



CREATE INDEX "idx_patient_interventions_analytics" ON "public"."patient_interventions" USING "btree" ("intervention_code", "status", "created_at");



CREATE INDEX "idx_patient_interventions_assessment" ON "public"."patient_interventions" USING "btree" ("linked_assessment_type", "linked_assessment_id");



CREATE INDEX "idx_patient_interventions_category" ON "public"."patient_interventions" USING "btree" ("intervention_category");



CREATE INDEX "idx_patient_interventions_category_take_up" ON "public"."patient_interventions" USING "btree" ("intervention_category", "take_up_likelihood" DESC) WHERE ("take_up_likelihood" IS NOT NULL);



CREATE INDEX "idx_patient_interventions_code" ON "public"."patient_interventions" USING "btree" ("intervention_code");



CREATE INDEX "idx_patient_interventions_extraction_id" ON "public"."patient_interventions" USING "btree" ("extraction_id");



CREATE INDEX "idx_patient_interventions_extraction_take_up" ON "public"."patient_interventions" USING "btree" ("extraction_id", "take_up_likelihood" DESC) WHERE ("take_up_likelihood" IS NOT NULL);



CREATE INDEX "idx_patient_interventions_insights_id" ON "public"."patient_interventions" USING "btree" ("consultation_insights_id");



CREATE INDEX "idx_patient_interventions_outcome" ON "public"."patient_interventions" USING "btree" ("outcome") WHERE ("outcome" IS NOT NULL);



CREATE INDEX "idx_patient_interventions_priority" ON "public"."patient_interventions" USING "btree" ("priority_level");



CREATE INDEX "idx_patient_interventions_status" ON "public"."patient_interventions" USING "btree" ("status");



CREATE INDEX "idx_patient_interventions_sub_type" ON "public"."patient_interventions" USING "btree" ("intervention_sub_type");



CREATE INDEX "idx_patient_interventions_take_up" ON "public"."patient_interventions" USING "btree" ("take_up_likelihood" DESC) WHERE ("take_up_likelihood" IS NOT NULL);



CREATE INDEX "idx_patient_interventions_top_recs" ON "public"."patient_interventions" USING "btree" ("extraction_id", "recommendation_rank") WHERE ("is_top_recommendation" = true);



CREATE INDEX "idx_patient_sharing_source" ON "public"."patient_sharing" USING "btree" ("source_doctor_id", "revoked_at") WHERE ("revoked_at" IS NULL);



CREATE INDEX "idx_patient_sharing_target" ON "public"."patient_sharing" USING "btree" ("target_doctor_id", "revoked_at") WHERE ("revoked_at" IS NULL);



CREATE UNIQUE INDEX "idx_patient_sharing_unique_active" ON "public"."patient_sharing" USING "btree" ("source_doctor_id", "target_doctor_id", "patient_id") WHERE ("revoked_at" IS NULL);



CREATE INDEX "idx_patients_doctor_ids" ON "public"."patients" USING "gin" ("doctor_ids");



CREATE INDEX "idx_patients_hospital_id" ON "public"."patients" USING "btree" ("hospital_id") WHERE ("hospital_id" IS NOT NULL);



CREATE INDEX "idx_patients_ip_id" ON "public"."patients" USING "btree" ("ip_id") WHERE ("ip_id" IS NOT NULL);



CREATE INDEX "idx_patients_op_id" ON "public"."patients" USING "btree" ("op_id") WHERE ("op_id" IS NOT NULL);



CREATE INDEX "idx_patients_patient_id" ON "public"."patients" USING "btree" ("patient_id");



CREATE UNIQUE INDEX "idx_patients_patient_id_hospital" ON "public"."patients" USING "btree" ("patient_id", COALESCE("hospital_id", '00000000-0000-0000-0000-000000000000'::"uuid"));



CREATE INDEX "idx_phi_audit_action" ON "public"."phi_audit_log" USING "btree" ("action", "created_at" DESC);



CREATE INDEX "idx_phi_audit_client" ON "public"."phi_audit_log" USING "btree" ("client_id", "created_at" DESC);



CREATE INDEX "idx_phi_audit_doctor" ON "public"."phi_audit_log" USING "btree" ("doctor_id", "created_at" DESC);



CREATE INDEX "idx_phi_audit_patient" ON "public"."phi_audit_log" USING "btree" ("patient_id", "created_at" DESC);



CREATE INDEX "idx_phi_audit_resource" ON "public"."phi_audit_log" USING "btree" ("resource_type", "resource_id");



CREATE INDEX "idx_phi_audit_time" ON "public"."phi_audit_log" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_phi_audit_user" ON "public"."phi_audit_log" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "idx_procedure_fee_master_cpt" ON "public"."procedure_fee_master" USING "btree" ("cpt_code") WHERE ("cpt_code" IS NOT NULL);



CREATE INDEX "idx_procedure_fee_master_hospital" ON "public"."procedure_fee_master" USING "btree" ("hospital_id");



CREATE INDEX "idx_processing_jobs_session_id" ON "public"."processing_jobs" USING "btree" ("session_id");



CREATE INDEX "idx_processing_jobs_status" ON "public"."processing_jobs" USING "btree" ("status");



CREATE INDEX "idx_processing_jobs_submission_id" ON "public"."processing_jobs" USING "btree" ("submission_id");



CREATE INDEX "idx_processing_jobs_submission_status" ON "public"."processing_jobs" USING "btree" ("submission_id", "status");



CREATE INDEX "idx_processing_modes_active" ON "public"."processing_modes" USING "btree" ("is_active");



CREATE INDEX "idx_processing_modes_code" ON "public"."processing_modes" USING "btree" ("mode_code");



CREATE INDEX "idx_processing_modes_default" ON "public"."processing_modes" USING "btree" ("is_default");



CREATE INDEX "idx_processing_modes_display_order" ON "public"."processing_modes" USING "btree" ("display_order");



CREATE UNIQUE INDEX "idx_qa_engine_settings_hospital" ON "public"."qa_engine_settings" USING "btree" ("hospital_id");



CREATE INDEX "idx_qa_query_history_doctor" ON "public"."qa_query_history" USING "btree" ("doctor_id", "created_at" DESC);



CREATE INDEX "idx_qa_query_history_hospital" ON "public"."qa_query_history" USING "btree" ("hospital_id", "created_at" DESC);



CREATE INDEX "idx_qa_query_history_intent" ON "public"."qa_query_history" USING "btree" ("query_intent", "created_at" DESC);



CREATE INDEX "idx_qa_query_history_reframed" ON "public"."qa_query_history" USING "btree" ("hospital_id", "created_at" DESC) WHERE ("reframed_query" IS NOT NULL);



CREATE INDEX "idx_radiology_plan_library_template" ON "public"."radiology_plan_library" USING "btree" ("template_id") WHERE "is_active";



CREATE INDEX "idx_radiology_toxicity_library_template" ON "public"."radiology_toxicity_library" USING "btree" ("template_id", "phase") WHERE "is_active";



CREATE INDEX "idx_realtime_responses_hospital" ON "public"."realtime_extraction_responses" USING "btree" ("hospital_id", "created_at" DESC);



CREATE INDEX "idx_realtime_responses_hospital_code" ON "public"."realtime_extraction_responses" USING "btree" ("hospital_code", "created_at" DESC);



CREATE INDEX "idx_realtime_responses_submission" ON "public"."realtime_extraction_responses" USING "btree" ("submission_id");



CREATE INDEX "idx_recording_sessions_api_client_id" ON "public"."recording_sessions" USING "btree" ("api_client_id");



CREATE INDEX "idx_recording_sessions_audio_quality" ON "public"."recording_sessions" USING "btree" ((("audio_quality_json" ->> 'overall_quality'::"text"))) WHERE ("audio_quality_json" IS NOT NULL);



CREATE INDEX "idx_recording_sessions_consultation_type" ON "public"."recording_sessions" USING "btree" ("consultation_type_id");



CREATE INDEX "idx_recording_sessions_context_template_id" ON "public"."recording_sessions" USING "btree" ((("session_context_json" ->> 'template_id'::"text"))) WHERE (("session_context_json" ->> 'template_id'::"text") IS NOT NULL);



CREATE INDEX "idx_recording_sessions_correlation_id" ON "public"."recording_sessions" USING "btree" ("correlation_id");



CREATE INDEX "idx_recording_sessions_created_at" ON "public"."recording_sessions" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_recording_sessions_doctor_id" ON "public"."recording_sessions" USING "btree" ("doctor_id");



CREATE INDEX "idx_recording_sessions_metadata" ON "public"."recording_sessions" USING "gin" ("recording_metadata_json");



CREATE INDEX "idx_recording_sessions_nurse_id" ON "public"."recording_sessions" USING "btree" ("nurse_id");



CREATE INDEX "idx_recording_sessions_patient_id" ON "public"."recording_sessions" USING "btree" ("patient_id");



CREATE INDEX "idx_recording_sessions_processing_mode" ON "public"."recording_sessions" USING "btree" ("processing_mode");



CREATE INDEX "idx_recording_sessions_status" ON "public"."recording_sessions" USING "btree" ("status");



CREATE INDEX "idx_recording_sessions_template_code" ON "public"."recording_sessions" USING "btree" ("template_code");



CREATE INDEX "idx_recording_sessions_template_name" ON "public"."recording_sessions" USING "btree" ("template_name");



CREATE INDEX "idx_recording_sessions_transcript_null" ON "public"."recording_sessions" USING "btree" ("transcript_text") WHERE ("transcript_text" IS NULL);



CREATE INDEX "idx_recording_sessions_transcript_search" ON "public"."recording_sessions" USING "gin" ("to_tsvector"('"english"'::"regconfig", "transcript_text"));



CREATE INDEX "idx_refresh_tokens_client_id" ON "public"."refresh_tokens" USING "btree" ("client_id");



CREATE INDEX "idx_refresh_tokens_lookup" ON "public"."refresh_tokens" USING "btree" ("token_hash") WHERE ("is_revoked" = false);



CREATE INDEX "idx_room_rate_master_hospital" ON "public"."room_rate_master" USING "btree" ("hospital_id");



CREATE UNIQUE INDEX "idx_room_rate_master_unique" ON "public"."room_rate_master" USING "btree" ("hospital_id", "room_category", COALESCE("room_sub_category", ''::character varying));



CREATE INDEX "idx_segment_definitions_active" ON "public"."segment_definitions" USING "btree" ("is_active");



CREATE INDEX "idx_segment_definitions_category" ON "public"."segment_definitions" USING "btree" ("default_category");



CREATE INDEX "idx_segment_definitions_code" ON "public"."segment_definitions" USING "btree" ("segment_code");



CREATE INDEX "idx_segment_definitions_doctor_id" ON "public"."segment_definitions" USING "btree" ("doctor_id") WHERE ("doctor_id" IS NOT NULL);



CREATE INDEX "idx_segment_definitions_is_active" ON "public"."segment_definitions" USING "btree" ("is_active");



CREATE INDEX "idx_segment_definitions_order" ON "public"."segment_definitions" USING "btree" ("display_order");



CREATE INDEX "idx_segment_definitions_parent_segment_code" ON "public"."segment_definitions" USING "btree" ("parent_segment_code");



CREATE INDEX "idx_segment_definitions_segment_code" ON "public"."segment_definitions" USING "btree" ("segment_code");



CREATE INDEX "idx_segment_definitions_segment_type" ON "public"."segment_definitions" USING "btree" ("segment_type");



CREATE INDEX "idx_segment_definitions_status" ON "public"."segment_definitions" USING "btree" ("status");



CREATE INDEX "idx_segment_embeddings_segment_code" ON "public"."segment_embeddings" USING "btree" ("segment_code", "hospital_id", "model_id");



CREATE UNIQUE INDEX "idx_segment_embeddings_unique" ON "public"."segment_embeddings" USING "btree" ("extraction_id", "segment_code", "model_id");



CREATE INDEX "idx_segment_embeddings_vector_hnsw" ON "public"."segment_embeddings" USING "hnsw" ("embedding" "extensions"."vector_cosine_ops") WITH ("m"='16', "ef_construction"='64');



CREATE INDEX "idx_segments_code" ON "public"."extraction_segments" USING "btree" ("segment_code");



CREATE INDEX "idx_segments_code_extraction" ON "public"."extraction_segments" USING "btree" ("segment_code", "extraction_id");



CREATE INDEX "idx_segments_extraction" ON "public"."extraction_segments" USING "btree" ("extraction_id");



CREATE INDEX "idx_segments_value_gin" ON "public"."extraction_segments" USING "gin" ("segment_value");



CREATE INDEX "idx_segments_value_text_fts" ON "public"."extraction_segments" USING "gin" ("to_tsvector"('"english"'::"regconfig", "segment_value_text"));



CREATE INDEX "idx_session_audit_action" ON "public"."session_audit_log" USING "btree" ("action");



CREATE INDEX "idx_session_audit_changed_at" ON "public"."session_audit_log" USING "btree" ("changed_at" DESC);



CREATE INDEX "idx_session_audit_session_id" ON "public"."session_audit_log" USING "btree" ("session_id");



CREATE INDEX "idx_severity_consultation_insights" ON "public"."clinical_severity_assessments" USING "btree" ("consultation_insights_id");



CREATE INDEX "idx_severity_created_at" ON "public"."clinical_severity_assessments" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_severity_doctor" ON "public"."clinical_severity_assessments" USING "btree" ("doctor_id");



CREATE INDEX "idx_severity_extraction" ON "public"."clinical_severity_assessments" USING "btree" ("extraction_id");



CREATE INDEX "idx_severity_is_alternate_procedure" ON "public"."clinical_severity_assessments" USING "btree" ("is_alternate_procedure") WHERE ("is_alternate_procedure" = true);



CREATE INDEX "idx_severity_is_chronic" ON "public"."clinical_severity_assessments" USING "btree" ("is_chronic") WHERE ("is_chronic" = true);



CREATE INDEX "idx_severity_is_second_opinion" ON "public"."clinical_severity_assessments" USING "btree" ("is_second_opinion") WHERE ("is_second_opinion" = true);



CREATE INDEX "idx_severity_is_surgical" ON "public"."clinical_severity_assessments" USING "btree" ("is_surgical") WHERE ("is_surgical" = true);



CREATE INDEX "idx_severity_level" ON "public"."clinical_severity_assessments" USING "btree" ("severity_level");



CREATE INDEX "idx_severity_patient" ON "public"."clinical_severity_assessments" USING "btree" ("patient_id");



CREATE INDEX "idx_spc_component_code" ON "public"."system_prompt_components" USING "btree" ("component_code");



CREATE INDEX "idx_spc_component_type" ON "public"."system_prompt_components" USING "btree" ("component_type");



CREATE INDEX "idx_spc_config_active" ON "public"."system_prompt_configurations" USING "btree" ("is_active") WHERE ("is_active" = true);



CREATE INDEX "idx_spc_config_code" ON "public"."system_prompt_configurations" USING "btree" ("config_code");



CREATE INDEX "idx_spc_config_draft" ON "public"."system_prompt_configurations" USING "btree" ("is_draft") WHERE ("is_draft" = false);



CREATE INDEX "idx_spc_is_active" ON "public"."system_prompt_components" USING "btree" ("is_active") WHERE ("is_active" = true);



CREATE INDEX "idx_spc_is_base" ON "public"."system_prompt_components" USING "btree" ("is_base_component") WHERE ("is_base_component" = true);



CREATE INDEX "idx_spcc_codes" ON "public"."system_prompt_config_components" USING "btree" ("config_code", "component_code");



CREATE INDEX "idx_spcc_component" ON "public"."system_prompt_config_components" USING "btree" ("component_id");



CREATE INDEX "idx_spcc_config" ON "public"."system_prompt_config_components" USING "btree" ("config_id");



CREATE INDEX "idx_spcc_config_order" ON "public"."system_prompt_config_components" USING "btree" ("config_id", "display_order");



CREATE INDEX "idx_temp_audio_expires" ON "public"."temp_audio_files" USING "btree" ("expires_at");



CREATE INDEX "idx_temp_audio_session" ON "public"."temp_audio_files" USING "btree" ("session_id");



CREATE INDEX "idx_template_ehr_ehr_type" ON "public"."template_ehr" USING "btree" ("ehr_type_id");



CREATE INDEX "idx_template_ehr_template" ON "public"."template_ehr" USING "btree" ("template_id");



CREATE INDEX "idx_template_segment_category" ON "public"."template_segments" USING "btree" ("category");



CREATE INDEX "idx_template_segment_template_id" ON "public"."template_segments" USING "btree" ("template_id");



CREATE INDEX "idx_template_segments_name" ON "public"."template_segments" USING "btree" ("template_name");



CREATE INDEX "idx_template_segments_segment_id" ON "public"."template_segments" USING "btree" ("segment_id");



CREATE INDEX "idx_template_standard_texts_template" ON "public"."template_standard_texts" USING "btree" ("template_id") WHERE "is_active";



CREATE INDEX "idx_templates_active" ON "public"."templates" USING "btree" ("is_active");



CREATE INDEX "idx_templates_code" ON "public"."templates" USING "btree" ("template_code");



CREATE INDEX "idx_templates_consultation_type" ON "public"."templates" USING "btree" ("consultation_type_id");



CREATE INDEX "idx_templates_doctor_id" ON "public"."templates" USING "btree" ("doctor_id");



CREATE INDEX "idx_templates_excluded_segment_codes" ON "public"."templates" USING "gin" ("excluded_segment_codes");



CREATE INDEX "idx_templates_formatter_code" ON "public"."templates" USING "btree" ("formatter_code") WHERE ("formatter_code" IS NOT NULL);



CREATE INDEX "idx_templates_hospital" ON "public"."templates" USING "btree" ("hospital_id");



CREATE INDEX "idx_templates_is_active" ON "public"."templates" USING "btree" ("is_active");



CREATE INDEX "idx_templates_prompt_assembly_hash" ON "public"."templates" USING "btree" ("prompt_assembly_hash");



CREATE INDEX "idx_templates_schema_assembly_hash" ON "public"."templates" USING "btree" ("schema_assembly_hash");



CREATE INDEX "idx_templates_specialization" ON "public"."templates" USING "btree" ("specialization");



CREATE INDEX "idx_templates_system_prompt_config_id" ON "public"."templates" USING "btree" ("system_prompt_config_id");



CREATE INDEX "idx_triage_conflict_log_extraction" ON "public"."triage_conflict_log" USING "btree" ("extraction_id");



CREATE INDEX "idx_triage_conflict_log_type" ON "public"."triage_conflict_log" USING "btree" ("conflict_type", "created_at" DESC);



CREATE INDEX "idx_triage_feedback_analytics" ON "public"."triage_feedback" USING "btree" ("doctor_id", "feedback_type", "feedback_at" DESC);



CREATE INDEX "idx_triage_feedback_doctor" ON "public"."triage_feedback" USING "btree" ("doctor_id");



CREATE INDEX "idx_triage_feedback_suggestion" ON "public"."triage_feedback" USING "btree" ("suggestion_id");



CREATE INDEX "idx_triage_feedback_type" ON "public"."triage_feedback" USING "btree" ("feedback_type");



CREATE INDEX "idx_triage_layer_config_enabled" ON "public"."triage_layer_config" USING "btree" ("is_enabled") WHERE ("is_enabled" = true);



CREATE INDEX "idx_triage_suggestion_category" ON "public"."triage_suggestion_log" USING "btree" ("suggestion_category");



CREATE INDEX "idx_triage_suggestion_created" ON "public"."triage_suggestion_log" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_triage_suggestion_doctor" ON "public"."triage_suggestion_log" USING "btree" ("doctor_id");



CREATE INDEX "idx_triage_suggestion_extraction" ON "public"."triage_suggestion_log" USING "btree" ("extraction_id");



CREATE INDEX "idx_triage_suggestion_source" ON "public"."triage_suggestion_log" USING "btree" ("source_layer");



CREATE INDEX "idx_type_segment_defaults_segment" ON "public"."consultation_type_segments" USING "btree" ("segment_code");



CREATE INDEX "idx_type_segment_defaults_type" ON "public"."consultation_type_segments" USING "btree" ("consultation_type_id");



CREATE INDEX "idx_validation_warnings_created" ON "public"."audio_validation_warnings" USING "btree" ("created_at");



CREATE INDEX "idx_validation_warnings_session" ON "public"."audio_validation_warnings" USING "btree" ("session_id");



CREATE UNIQUE INDEX "preset_segment_configurations_pkey" ON "public"."template_segments" USING "btree" ("id");



CREATE UNIQUE INDEX "template_segment_configurations_template_id_segment_code_key" ON "public"."template_segments" USING "btree" ("template_id", "segment_code");



CREATE UNIQUE INDEX "templates_doctor_code_unique" ON "public"."templates" USING "btree" ("doctor_id", "template_code");



CREATE UNIQUE INDEX "ux_extraction_photos_storage_path" ON "public"."extraction_photos" USING "btree" ("storage_path");



CREATE OR REPLACE TRIGGER "clinical_chunk_embeddings_updated_at" BEFORE UPDATE ON "public"."clinical_chunk_embeddings" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "clinical_conditions_updated_at" BEFORE UPDATE ON "public"."clinical_conditions" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "clinical_guideline_embeddings_updated_at" BEFORE UPDATE ON "public"."clinical_guideline_embeddings" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "clinical_guidelines_updated_at" BEFORE UPDATE ON "public"."clinical_guidelines" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "doctor_layer_preferences_updated_at" BEFORE UPDATE ON "public"."doctor_layer_preferences" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "doctor_practice_styles_updated_at" BEFORE UPDATE ON "public"."doctor_practice_styles" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "embedding_models_updated_at" BEFORE UPDATE ON "public"."embedding_models" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "extraction_embeddings_updated_at" BEFORE UPDATE ON "public"."extraction_embeddings" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "hospital_ehr_updated_at" BEFORE UPDATE ON "public"."hospital_ehr" FOR EACH ROW EXECUTE FUNCTION "public"."update_hospital_ehr_updated_at"();



CREATE OR REPLACE TRIGGER "hospital_specialty_patterns_updated_at" BEFORE UPDATE ON "public"."hospital_specialty_patterns" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "patient_sharing_updated_at" BEFORE UPDATE ON "public"."patient_sharing" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "prevent_admin_action_log_deletion" BEFORE DELETE ON "public"."admin_action_log" FOR EACH ROW EXECUTE FUNCTION "public"."prevent_audit_log_deletion"();



CREATE OR REPLACE TRIGGER "prevent_phi_audit_log_deletion" BEFORE DELETE ON "public"."phi_audit_log" FOR EACH ROW EXECUTE FUNCTION "public"."prevent_audit_log_deletion"();



CREATE OR REPLACE TRIGGER "qa_engine_settings_updated_at" BEFORE UPDATE ON "public"."qa_engine_settings" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "segment_embeddings_updated_at" BEFORE UPDATE ON "public"."segment_embeddings" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "specialty_benchmarks_updated_at" BEFORE UPDATE ON "public"."specialty_benchmarks" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "trg_emotion_prompt_changed" AFTER INSERT OR DELETE OR UPDATE ON "public"."segment_definitions" FOR EACH ROW EXECUTE FUNCTION "public"."notify_emotion_prompt_change"();



CREATE OR REPLACE TRIGGER "triage_layer_config_updated_at" BEFORE UPDATE ON "public"."triage_layer_config" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "trigger_intervention_definitions_updated_at" BEFORE UPDATE ON "public"."intervention_definitions" FOR EACH ROW EXECUTE FUNCTION "public"."update_intervention_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_patient_interventions_updated_at" BEFORE UPDATE ON "public"."patient_interventions" FOR EACH ROW EXECUTE FUNCTION "public"."update_intervention_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_doctor_templates_timestamp" BEFORE UPDATE ON "public"."doctor_templates" FOR EACH ROW EXECUTE FUNCTION "public"."update_doctor_templates_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_followup_tracking_updated_at" BEFORE UPDATE ON "public"."followup_tracking" FOR EACH ROW EXECUTE FUNCTION "public"."update_followup_tracking_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_intervention_outcomes_updated_at" BEFORE UPDATE ON "public"."intervention_outcomes" FOR EACH ROW EXECUTE FUNCTION "public"."update_intervention_outcomes_updated_at"();



CREATE OR REPLACE TRIGGER "update_admin_users_updated_at" BEFORE UPDATE ON "public"."admin_users" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_api_client_last_used" AFTER INSERT ON "public"."api_client_usage" FOR EACH ROW EXECUTE FUNCTION "public"."update_client_last_used"();



CREATE OR REPLACE TRIGGER "update_api_clients_updated_at" BEFORE UPDATE ON "public"."api_clients" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_consultation_type_system_prompts_updated_at" BEFORE UPDATE ON "public"."consultation_type_system_prompts" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_consultation_types_updated_at" BEFORE UPDATE ON "public"."consultation_types" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_doctor_investigations_updated_at" BEFORE UPDATE ON "public"."doctor_investigations" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_doctor_medicines_updated_at" BEFORE UPDATE ON "public"."doctor_medicines" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_doctors_updated_at" BEFORE UPDATE ON "public"."doctors" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_extraction_segments_updated_at" BEFORE UPDATE ON "public"."extraction_segments" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_hospital_investigation_lists_updated_at" BEFORE UPDATE ON "public"."hospital_investigation_lists" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_hospital_medicine_lists_updated_at" BEFORE UPDATE ON "public"."hospital_medicine_lists" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_medical_extractions_updated_at" BEFORE UPDATE ON "public"."medical_extractions" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_patients_updated_at" BEFORE UPDATE ON "public"."patients" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_processing_modes_updated_at" BEFORE UPDATE ON "public"."processing_modes" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_recording_sessions_updated_at" BEFORE UPDATE ON "public"."recording_sessions" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_segment_definitions_updated_at" BEFORE UPDATE ON "public"."segment_definitions" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_system_prompt_components_updated_at" BEFORE UPDATE ON "public"."system_prompt_components" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_system_prompt_configurations_updated_at" BEFORE UPDATE ON "public"."system_prompt_configurations" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_templates_updated_at" BEFORE UPDATE ON "public"."templates" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



ALTER TABLE ONLY "public"."admin_users"
    ADD CONSTRAINT "admin_users_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."allied_health_needs"
    ADD CONSTRAINT "allied_health_needs_clinical_severity_id_fkey" FOREIGN KEY ("clinical_severity_id") REFERENCES "public"."clinical_severity_assessments"("id");



ALTER TABLE ONLY "public"."allied_health_needs"
    ADD CONSTRAINT "allied_health_needs_consultation_insights_id_fkey" FOREIGN KEY ("consultation_insights_id") REFERENCES "public"."consultation_insights"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."allied_health_needs"
    ADD CONSTRAINT "allied_health_needs_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."allied_health_needs"
    ADD CONSTRAINT "allied_health_needs_other_clinical_needs_id_fkey" FOREIGN KEY ("other_clinical_needs_id") REFERENCES "public"."other_clinical_needs"("id");



ALTER TABLE ONLY "public"."api_client_usage"
    ADD CONSTRAINT "api_client_usage_client_id_fkey" FOREIGN KEY ("client_id") REFERENCES "public"."api_clients"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."api_clients"
    ADD CONSTRAINT "api_clients_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id");



ALTER TABLE ONLY "public"."audio_chunks"
    ADD CONSTRAINT "audio_chunks_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."recording_sessions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."audio_validation_warnings"
    ADD CONSTRAINT "audio_validation_warnings_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."recording_sessions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bill_line_items"
    ADD CONSTRAINT "bill_line_items_bill_id_fkey" FOREIGN KEY ("bill_id") REFERENCES "public"."bills"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bills"
    ADD CONSTRAINT "bills_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bills"
    ADD CONSTRAINT "bills_superseded_by_bill_id_fkey" FOREIGN KEY ("superseded_by_bill_id") REFERENCES "public"."bills"("id");



ALTER TABLE ONLY "public"."care_quality_risk"
    ADD CONSTRAINT "care_quality_risk_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."clinical_chunk_embeddings"
    ADD CONSTRAINT "clinical_chunk_embeddings_chunk_id_fkey" FOREIGN KEY ("chunk_id") REFERENCES "public"."clinical_chunks"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."clinical_chunk_embeddings"
    ADD CONSTRAINT "clinical_chunk_embeddings_embedding_model_id_fkey" FOREIGN KEY ("embedding_model_id") REFERENCES "public"."embedding_models"("id");



ALTER TABLE ONLY "public"."clinical_chunks"
    ADD CONSTRAINT "clinical_chunks_condition_id_fkey" FOREIGN KEY ("condition_id") REFERENCES "public"."clinical_conditions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."clinical_guideline_embeddings"
    ADD CONSTRAINT "clinical_guideline_embeddings_embedding_model_id_fkey" FOREIGN KEY ("embedding_model_id") REFERENCES "public"."embedding_models"("id");



ALTER TABLE ONLY "public"."clinical_guideline_embeddings"
    ADD CONSTRAINT "clinical_guideline_embeddings_guideline_id_fkey" FOREIGN KEY ("guideline_id") REFERENCES "public"."clinical_guidelines"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."clinical_severity_assessments"
    ADD CONSTRAINT "clinical_severity_assessments_consultation_insights_id_fkey" FOREIGN KEY ("consultation_insights_id") REFERENCES "public"."consultation_insights"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."clinical_severity_assessments"
    ADD CONSTRAINT "clinical_severity_assessments_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."consultation_insights"
    ADD CONSTRAINT "consultation_insights_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."consultation_type_segments"
    ADD CONSTRAINT "consultation_type_segment_defaults_consultation_type_id_fkey" FOREIGN KEY ("consultation_type_id") REFERENCES "public"."consultation_types"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."consultation_type_system_prompts"
    ADD CONSTRAINT "consultation_type_system_prompts_consultation_type_id_fkey" FOREIGN KEY ("consultation_type_id") REFERENCES "public"."consultation_types"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."consultation_type_system_prompts"
    ADD CONSTRAINT "consultation_type_system_prompts_system_prompt_config_id_fkey" FOREIGN KEY ("system_prompt_config_id") REFERENCES "public"."system_prompt_configurations"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."doctor_doctor_patients"
    ADD CONSTRAINT "doctor_doctor_patients_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."doctor_doctor_patients"
    ADD CONSTRAINT "doctor_doctor_patients_linked_doctor_id_fkey" FOREIGN KEY ("linked_doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."doctor_investigations"
    ADD CONSTRAINT "doctor_investigations_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."doctor_layer_preferences"
    ADD CONSTRAINT "doctor_layer_preferences_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."doctor_medicines"
    ADD CONSTRAINT "doctor_medicines_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."doctor_practice_styles"
    ADD CONSTRAINT "doctor_practice_styles_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."doctors"
    ADD CONSTRAINT "doctors_default_template_id_fkey" FOREIGN KEY ("default_template_id") REFERENCES "public"."templates"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."doctors"
    ADD CONSTRAINT "doctors_ehr_type_id_fkey" FOREIGN KEY ("ehr_type_id") REFERENCES "public"."ehr_types"("id");



ALTER TABLE ONLY "public"."doctors"
    ADD CONSTRAINT "doctors_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."extraction_accuracy_metrics"
    ADD CONSTRAINT "extraction_accuracy_metrics_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."extraction_accuracy_metrics"
    ADD CONSTRAINT "extraction_accuracy_metrics_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."extraction_edit_history"
    ADD CONSTRAINT "extraction_edit_history_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."extraction_embeddings"
    ADD CONSTRAINT "extraction_embeddings_consultation_type_id_fkey" FOREIGN KEY ("consultation_type_id") REFERENCES "public"."consultation_types"("id");



ALTER TABLE ONLY "public"."extraction_embeddings"
    ADD CONSTRAINT "extraction_embeddings_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."extraction_embeddings"
    ADD CONSTRAINT "extraction_embeddings_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."extraction_embeddings"
    ADD CONSTRAINT "extraction_embeddings_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id");



ALTER TABLE ONLY "public"."extraction_embeddings"
    ADD CONSTRAINT "extraction_embeddings_model_id_fkey" FOREIGN KEY ("model_id") REFERENCES "public"."embedding_models"("id");



ALTER TABLE ONLY "public"."extraction_embeddings"
    ADD CONSTRAINT "extraction_embeddings_patient_id_fkey" FOREIGN KEY ("patient_id") REFERENCES "public"."patients"("id");



ALTER TABLE ONLY "public"."extraction_photos"
    ADD CONSTRAINT "extraction_photos_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."extraction_relationships"
    ADD CONSTRAINT "extraction_relationships_merged_extraction_id_fkey" FOREIGN KEY ("merged_extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."extraction_relationships"
    ADD CONSTRAINT "extraction_relationships_source_extraction_id_fkey" FOREIGN KEY ("source_extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."extraction_segments"
    ADD CONSTRAINT "extraction_segments_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."extraction_translations"
    ADD CONSTRAINT "extraction_translations_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."consultation_type_segments"
    ADD CONSTRAINT "fk_consultation_type_segments_segment_id" FOREIGN KEY ("segment_id") REFERENCES "public"."segment_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."doctor_templates"
    ADD CONSTRAINT "fk_doctor_templates_doctor" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."doctor_templates"
    ADD CONSTRAINT "fk_doctor_templates_template" FOREIGN KEY ("template_id") REFERENCES "public"."templates"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."template_segments"
    ADD CONSTRAINT "fk_template_segments_segment_id" FOREIGN KEY ("segment_id") REFERENCES "public"."segment_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."followup_tracking"
    ADD CONSTRAINT "followup_tracking_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."hospital_ehr"
    ADD CONSTRAINT "hospital_ehr_ehr_type_id_fkey" FOREIGN KEY ("ehr_type_id") REFERENCES "public"."ehr_types"("id");



ALTER TABLE ONLY "public"."hospital_ehr"
    ADD CONSTRAINT "hospital_ehr_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."hospital_intervention_pricing"
    ADD CONSTRAINT "hospital_intervention_pricing_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."hospital_investigation_lists"
    ADD CONSTRAINT "hospital_investigation_lists_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."hospital_investigation_lists"
    ADD CONSTRAINT "hospital_investigation_lists_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."hospital_medicine_lists"
    ADD CONSTRAINT "hospital_medicine_lists_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."hospital_medicine_lists"
    ADD CONSTRAINT "hospital_medicine_lists_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."hospital_specialty_patterns"
    ADD CONSTRAINT "hospital_specialty_patterns_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."hospitals"
    ADD CONSTRAINT "hospitals_default_template_id_fkey" FOREIGN KEY ("default_template_id") REFERENCES "public"."templates"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."intervention_outcomes"
    ADD CONSTRAINT "intervention_outcomes_intervention_id_fkey" FOREIGN KEY ("intervention_id") REFERENCES "public"."patient_interventions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."investigation_list_uploads"
    ADD CONSTRAINT "investigation_list_uploads_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."investigation_list_uploads"
    ADD CONSTRAINT "investigation_list_uploads_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."investigation_match_log"
    ADD CONSTRAINT "investigation_match_log_correct_investigation_id_fkey" FOREIGN KEY ("correct_investigation_id") REFERENCES "public"."doctor_investigations"("id");



ALTER TABLE ONLY "public"."investigation_match_log"
    ADD CONSTRAINT "investigation_match_log_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."investigation_match_log"
    ADD CONSTRAINT "investigation_match_log_matched_hospital_investigation_id_fkey" FOREIGN KEY ("matched_hospital_investigation_id") REFERENCES "public"."hospital_investigation_lists"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."investigation_match_log"
    ADD CONSTRAINT "investigation_match_log_matched_investigation_id_fkey" FOREIGN KEY ("matched_investigation_id") REFERENCES "public"."doctor_investigations"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."llm_usage_log"
    ADD CONSTRAINT "llm_usage_log_api_client_id_fkey" FOREIGN KEY ("api_client_id") REFERENCES "public"."api_clients"("id");



ALTER TABLE ONLY "public"."llm_usage_log"
    ADD CONSTRAINT "llm_usage_log_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."llm_usage_log"
    ADD CONSTRAINT "llm_usage_log_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."llm_usage_log"
    ADD CONSTRAINT "llm_usage_log_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."recording_sessions"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."medical_extractions"
    ADD CONSTRAINT "medical_extractions_consultation_type_id_fkey" FOREIGN KEY ("consultation_type_id") REFERENCES "public"."consultation_types"("id");



ALTER TABLE ONLY "public"."medical_extractions"
    ADD CONSTRAINT "medical_extractions_merged_into_extraction_id_fkey" FOREIGN KEY ("merged_into_extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."medical_extractions"
    ADD CONSTRAINT "medical_extractions_patient_id_fkey" FOREIGN KEY ("patient_id") REFERENCES "public"."patients"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."medical_extractions"
    ADD CONSTRAINT "medical_extractions_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."recording_sessions"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."medical_extractions"
    ADD CONSTRAINT "medical_extractions_submission_id_fkey" FOREIGN KEY ("submission_id") REFERENCES "public"."processing_jobs"("submission_id");



ALTER TABLE ONLY "public"."medical_extractions"
    ADD CONSTRAINT "medical_extractions_user_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."medicine_list_uploads"
    ADD CONSTRAINT "medicine_list_uploads_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."medicine_match_log"
    ADD CONSTRAINT "medicine_match_log_correct_medicine_id_fkey" FOREIGN KEY ("correct_medicine_id") REFERENCES "public"."doctor_medicines"("id");



ALTER TABLE ONLY "public"."medicine_match_log"
    ADD CONSTRAINT "medicine_match_log_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."medicine_match_log"
    ADD CONSTRAINT "medicine_match_log_matched_hospital_medicine_id_fkey" FOREIGN KEY ("matched_hospital_medicine_id") REFERENCES "public"."hospital_medicine_lists"("id");



ALTER TABLE ONLY "public"."medicine_match_log"
    ADD CONSTRAINT "medicine_match_log_matched_medicine_id_fkey" FOREIGN KEY ("matched_medicine_id") REFERENCES "public"."doctor_medicines"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."nurse_doctors"
    ADD CONSTRAINT "nurse_doctors_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."nurse_doctors"
    ADD CONSTRAINT "nurse_doctors_nurse_id_fkey" FOREIGN KEY ("nurse_id") REFERENCES "public"."nurses"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."nurse_templates"
    ADD CONSTRAINT "nurse_templates_nurse_id_fkey" FOREIGN KEY ("nurse_id") REFERENCES "public"."nurses"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."nurse_templates"
    ADD CONSTRAINT "nurse_templates_template_id_fkey" FOREIGN KEY ("template_id") REFERENCES "public"."templates"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."nurses"
    ADD CONSTRAINT "nurses_default_template_id_fkey" FOREIGN KEY ("default_template_id") REFERENCES "public"."templates"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."nurses"
    ADD CONSTRAINT "nurses_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id");



ALTER TABLE ONLY "public"."other_clinical_needs"
    ADD CONSTRAINT "other_clinical_needs_clinical_severity_id_fkey" FOREIGN KEY ("clinical_severity_id") REFERENCES "public"."clinical_severity_assessments"("id");



ALTER TABLE ONLY "public"."other_clinical_needs"
    ADD CONSTRAINT "other_clinical_needs_consultation_insights_id_fkey" FOREIGN KEY ("consultation_insights_id") REFERENCES "public"."consultation_insights"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."other_clinical_needs"
    ADD CONSTRAINT "other_clinical_needs_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."patient_dropoff_risk"
    ADD CONSTRAINT "patient_dropoff_risk_consultation_insights_id_fkey" FOREIGN KEY ("consultation_insights_id") REFERENCES "public"."consultation_insights"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."patient_dropoff_risk"
    ADD CONSTRAINT "patient_dropoff_risk_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."patient_interventions"
    ADD CONSTRAINT "patient_interventions_consultation_insights_id_fkey" FOREIGN KEY ("consultation_insights_id") REFERENCES "public"."consultation_insights"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."patient_interventions"
    ADD CONSTRAINT "patient_interventions_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."patient_interventions"
    ADD CONSTRAINT "patient_interventions_intervention_id_fkey" FOREIGN KEY ("intervention_id") REFERENCES "public"."intervention_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."patient_sharing"
    ADD CONSTRAINT "patient_sharing_patient_id_fkey" FOREIGN KEY ("patient_id") REFERENCES "public"."patients"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."patient_sharing"
    ADD CONSTRAINT "patient_sharing_source_doctor_id_fkey" FOREIGN KEY ("source_doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."patient_sharing"
    ADD CONSTRAINT "patient_sharing_target_doctor_id_fkey" FOREIGN KEY ("target_doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."patients"
    ADD CONSTRAINT "patients_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id");



ALTER TABLE ONLY "public"."processing_jobs"
    ADD CONSTRAINT "processing_jobs_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."recording_sessions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."qa_engine_settings"
    ADD CONSTRAINT "qa_engine_settings_embedding_model_id_fkey" FOREIGN KEY ("embedding_model_id") REFERENCES "public"."embedding_models"("id");



ALTER TABLE ONLY "public"."qa_engine_settings"
    ADD CONSTRAINT "qa_engine_settings_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."qa_query_history"
    ADD CONSTRAINT "qa_query_history_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."qa_query_history"
    ADD CONSTRAINT "qa_query_history_embedding_model_id_fkey" FOREIGN KEY ("embedding_model_id") REFERENCES "public"."embedding_models"("id");



ALTER TABLE ONLY "public"."qa_query_history"
    ADD CONSTRAINT "qa_query_history_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id");



ALTER TABLE ONLY "public"."radiology_plan_library"
    ADD CONSTRAINT "radiology_plan_library_template_id_fkey" FOREIGN KEY ("template_id") REFERENCES "public"."templates"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."radiology_toxicity_library"
    ADD CONSTRAINT "radiology_toxicity_library_template_id_fkey" FOREIGN KEY ("template_id") REFERENCES "public"."templates"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."realtime_extraction_responses"
    ADD CONSTRAINT "realtime_extraction_responses_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."realtime_extraction_responses"
    ADD CONSTRAINT "realtime_extraction_responses_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."realtime_extraction_responses"
    ADD CONSTRAINT "realtime_extraction_responses_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recording_sessions"
    ADD CONSTRAINT "recording_sessions_api_client_id_fkey" FOREIGN KEY ("api_client_id") REFERENCES "public"."api_clients"("id");



ALTER TABLE ONLY "public"."recording_sessions"
    ADD CONSTRAINT "recording_sessions_default_consultation_type_id_fkey" FOREIGN KEY ("consultation_type_id") REFERENCES "public"."consultation_types"("id");



ALTER TABLE ONLY "public"."recording_sessions"
    ADD CONSTRAINT "recording_sessions_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."recording_sessions"
    ADD CONSTRAINT "recording_sessions_nurse_id_fkey" FOREIGN KEY ("nurse_id") REFERENCES "public"."nurses"("id");



ALTER TABLE ONLY "public"."recording_sessions"
    ADD CONSTRAINT "recording_sessions_patient_id_fkey" FOREIGN KEY ("patient_id") REFERENCES "public"."patients"("id");



ALTER TABLE ONLY "public"."refresh_tokens"
    ADD CONSTRAINT "refresh_tokens_client_id_fkey" FOREIGN KEY ("client_id") REFERENCES "public"."api_clients"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."segment_definitions"
    ADD CONSTRAINT "segment_definitions_approved_by_admin_id_fkey" FOREIGN KEY ("approved_by_admin_id") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."segment_definitions"
    ADD CONSTRAINT "segment_definitions_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."segment_embeddings"
    ADD CONSTRAINT "segment_embeddings_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."segment_embeddings"
    ADD CONSTRAINT "segment_embeddings_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."segment_embeddings"
    ADD CONSTRAINT "segment_embeddings_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id");



ALTER TABLE ONLY "public"."segment_embeddings"
    ADD CONSTRAINT "segment_embeddings_model_id_fkey" FOREIGN KEY ("model_id") REFERENCES "public"."embedding_models"("id");



ALTER TABLE ONLY "public"."segment_embeddings"
    ADD CONSTRAINT "segment_embeddings_patient_id_fkey" FOREIGN KEY ("patient_id") REFERENCES "public"."patients"("id");



ALTER TABLE ONLY "public"."segment_embeddings"
    ADD CONSTRAINT "segment_embeddings_segment_id_fkey" FOREIGN KEY ("segment_id") REFERENCES "public"."extraction_segments"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."templates"
    ADD CONSTRAINT "segment_presets_consultation_type_id_fkey" FOREIGN KEY ("consultation_type_id") REFERENCES "public"."consultation_types"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."templates"
    ADD CONSTRAINT "segment_presets_created_by_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id");



ALTER TABLE ONLY "public"."templates"
    ADD CONSTRAINT "segment_presets_hospital_id_fkey" FOREIGN KEY ("hospital_id") REFERENCES "public"."hospitals"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."session_audit_log"
    ADD CONSTRAINT "session_audit_log_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."recording_sessions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."system_prompt_config_components"
    ADD CONSTRAINT "system_prompt_config_components_component_id_fkey" FOREIGN KEY ("component_id") REFERENCES "public"."system_prompt_components"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."system_prompt_config_components"
    ADD CONSTRAINT "system_prompt_config_components_config_id_fkey" FOREIGN KEY ("config_id") REFERENCES "public"."system_prompt_configurations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."system_prompt_configurations"
    ADD CONSTRAINT "system_prompt_configurations_inherits_from_id_fkey" FOREIGN KEY ("inherits_from_id") REFERENCES "public"."system_prompt_configurations"("id");



ALTER TABLE ONLY "public"."temp_audio_files"
    ADD CONSTRAINT "temp_audio_files_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."recording_sessions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."template_ehr"
    ADD CONSTRAINT "template_ehr_ehr_type_id_fkey" FOREIGN KEY ("ehr_type_id") REFERENCES "public"."ehr_types"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."template_ehr"
    ADD CONSTRAINT "template_ehr_template_id_fkey" FOREIGN KEY ("template_id") REFERENCES "public"."templates"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."template_segments"
    ADD CONSTRAINT "template_segment_configurations_template_id_fkey" FOREIGN KEY ("template_id") REFERENCES "public"."templates"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."template_standard_texts"
    ADD CONSTRAINT "template_standard_texts_template_id_fkey" FOREIGN KEY ("template_id") REFERENCES "public"."templates"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."templates"
    ADD CONSTRAINT "templates_system_prompt_config_id_fkey" FOREIGN KEY ("system_prompt_config_id") REFERENCES "public"."system_prompt_configurations"("id");



ALTER TABLE ONLY "public"."triage_conflict_log"
    ADD CONSTRAINT "triage_conflict_log_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."triage_feedback"
    ADD CONSTRAINT "triage_feedback_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."triage_feedback"
    ADD CONSTRAINT "triage_feedback_suggestion_id_fkey" FOREIGN KEY ("suggestion_id") REFERENCES "public"."triage_suggestion_log"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."triage_suggestion_log"
    ADD CONSTRAINT "triage_suggestion_log_doctor_id_fkey" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."triage_suggestion_log"
    ADD CONSTRAINT "triage_suggestion_log_extraction_id_fkey" FOREIGN KEY ("extraction_id") REFERENCES "public"."medical_extractions"("id") ON DELETE CASCADE;



CREATE POLICY "Anon read for Realtime progress updates" ON "public"."processing_jobs" FOR SELECT TO "anon" USING (true);



CREATE POLICY "Anon read for Realtime subscriptions" ON "public"."realtime_extraction_responses" FOR SELECT TO "anon" USING (true);



CREATE POLICY "Authenticated users can read own admin record" ON "public"."admin_users" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "auth_user_id"));



CREATE POLICY "Authenticated users can read processing jobs" ON "public"."processing_jobs" FOR SELECT TO "authenticated" USING (true);



CREATE POLICY "Authenticated users can read realtime extraction responses" ON "public"."realtime_extraction_responses" FOR SELECT TO "authenticated" USING (true);



CREATE POLICY "Service role full access" ON "public"."admin_action_log" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."admin_users" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."allied_health_needs" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."api_client_usage" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."api_clients" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."app_settings" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."audio_chunks" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."audio_validation_warnings" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."bill_line_items" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."bills" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."care_quality_risk" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."clinical_chunk_embeddings" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."clinical_chunks" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."clinical_condition_ingestion_jobs" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."clinical_conditions" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."clinical_guideline_embeddings" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."clinical_guidelines" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."clinical_severity_assessments" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."consultation_insights" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."consultation_type_segments" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."consultation_type_system_prompts" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."consultation_types" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."doctor_doctor_patients" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."doctor_investigations" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."doctor_layer_preferences" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."doctor_medicines" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."doctor_practice_styles" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."doctor_segment_configurations_backup_014" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."doctor_templates" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."doctors" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."ehr_types" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."embedding_models" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."extraction_accuracy_metrics" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."extraction_edit_history" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."extraction_embeddings" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."extraction_relationships" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."extraction_segments" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."followup_tracking" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."guideline_ingestion_jobs" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."hospital_ehr" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."hospital_intervention_pricing" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."hospital_investigation_lists" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."hospital_medicine_lists" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."hospital_specialty_patterns" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."hospitals" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."intervention_definitions" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."intervention_outcomes" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."investigation_list_uploads" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."investigation_match_log" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."llm_usage_log" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."medical_extractions" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."medicine_list_uploads" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."medicine_match_log" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."models_master" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."nurse_doctors" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."nurse_templates" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."nurses" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."other_clinical_needs" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."patient_dropoff_risk" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."patient_interventions" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."patient_sharing" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."patients" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."procedure_fee_master" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."processing_jobs" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."processing_modes" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."qa_engine_settings" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."qa_query_history" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."radiology_plan_library" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."radiology_toxicity_library" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."realtime_extraction_responses" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."recording_sessions" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."refresh_tokens" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."room_rate_master" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."segment_definitions" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."segment_embeddings" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."session_audit_log" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."specialty_benchmarks" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."system_prompt_components" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."system_prompt_config_components" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."system_prompt_configurations" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."temp_audio_files" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."template_ehr" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."template_segments" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."template_standard_texts" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."templates" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."triage_conflict_log" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."triage_feedback" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."triage_layer_config" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."triage_suggestion_log" TO "service_role" USING (true) WITH CHECK (true);



ALTER TABLE "public"."admin_action_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."admin_users" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."allied_health_needs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."api_client_usage" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."api_clients" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."app_settings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."audio_chunks" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."audio_validation_warnings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."bill_line_items" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."bills" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."care_quality_risk" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."clinical_chunk_embeddings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."clinical_chunks" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."clinical_condition_ingestion_jobs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."clinical_conditions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."clinical_guideline_embeddings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."clinical_guidelines" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."clinical_severity_assessments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."consultation_insights" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."consultation_type_segments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."consultation_type_system_prompts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."consultation_types" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctor_doctor_patients" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctor_investigations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctor_layer_preferences" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctor_medicines" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctor_practice_styles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctor_segment_configurations_backup_014" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctor_templates" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctors" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."ehr_types" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."embedding_models" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."extraction_accuracy_metrics" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."extraction_edit_history" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."extraction_embeddings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."extraction_photos" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."extraction_relationships" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."extraction_segments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."extraction_translations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."followup_tracking" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."guideline_ingestion_jobs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."hospital_ehr" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."hospital_intervention_pricing" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."hospital_investigation_lists" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."hospital_medicine_lists" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."hospital_specialty_patterns" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."hospitals" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."intervention_definitions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."intervention_outcomes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."investigation_list_uploads" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."investigation_match_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."llm_usage_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."medical_extractions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."medicine_list_uploads" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."medicine_match_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."models_master" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."nurse_doctors" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."nurse_templates" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."nurses" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."other_clinical_needs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."patient_dropoff_risk" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."patient_interventions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."patient_sharing" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."patients" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."phi_audit_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."procedure_fee_master" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."processing_jobs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."processing_modes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."qa_engine_settings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."qa_query_history" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."radiology_plan_library" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."radiology_toxicity_library" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."realtime_extraction_responses" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."recording_sessions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."refresh_tokens" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."room_rate_master" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."segment_definitions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."segment_embeddings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."session_audit_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."specialty_benchmarks" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."system_prompt_components" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."system_prompt_config_components" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."system_prompt_configurations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."temp_audio_files" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."template_ehr" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."template_segments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."template_standard_texts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."templates" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."triage_conflict_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."triage_feedback" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."triage_layer_config" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."triage_suggestion_log" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";






ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."processing_jobs";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."realtime_extraction_responses";









GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";

































































































































































































































































































































































































































































































































GRANT ALL ON FUNCTION "public"."activate_config_for_consultation_type_rpc"("p_consultation_type_code" character varying, "p_config_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."activate_config_for_consultation_type_rpc"("p_consultation_type_code" character varying, "p_config_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."activate_config_for_consultation_type_rpc"("p_consultation_type_code" character varying, "p_config_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."assemble_combined_emotion_prompt"("p_template_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."assemble_combined_emotion_prompt"("p_template_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."assemble_combined_emotion_prompt"("p_template_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."assemble_system_prompt_rpc"("p_config_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."assemble_system_prompt_rpc"("p_config_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."assemble_system_prompt_rpc"("p_config_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."can_doctor_access_template"("p_doctor_id" "uuid", "p_template_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."can_doctor_access_template"("p_doctor_id" "uuid", "p_template_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."can_doctor_access_template"("p_doctor_id" "uuid", "p_template_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."check_rate_limit"("p_client_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."check_rate_limit"("p_client_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."check_rate_limit"("p_client_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."cleanup_chunks_after_processing"("p_session_id" "uuid", "p_full_audio_data" "text", "p_full_audio_mime_type" "text", "p_full_audio_size_bytes" bigint, "p_processed_audio_data" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."cleanup_chunks_after_processing"("p_session_id" "uuid", "p_full_audio_data" "text", "p_full_audio_mime_type" "text", "p_full_audio_size_bytes" bigint, "p_processed_audio_data" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."cleanup_chunks_after_processing"("p_session_id" "uuid", "p_full_audio_data" "text", "p_full_audio_mime_type" "text", "p_full_audio_size_bytes" bigint, "p_processed_audio_data" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."cleanup_old_realtime_responses"() TO "anon";
GRANT ALL ON FUNCTION "public"."cleanup_old_realtime_responses"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."cleanup_old_realtime_responses"() TO "service_role";



GRANT ALL ON FUNCTION "public"."cleanup_old_sessions"("days_old" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."cleanup_old_sessions"("days_old" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."cleanup_old_sessions"("days_old" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."compute_all_hospital_patterns"() TO "anon";
GRANT ALL ON FUNCTION "public"."compute_all_hospital_patterns"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."compute_all_hospital_patterns"() TO "service_role";



GRANT ALL ON TABLE "public"."doctor_practice_styles" TO "anon";
GRANT ALL ON TABLE "public"."doctor_practice_styles" TO "authenticated";
GRANT ALL ON TABLE "public"."doctor_practice_styles" TO "service_role";



GRANT ALL ON FUNCTION "public"."compute_doctor_practice_style"("p_doctor_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."compute_doctor_practice_style"("p_doctor_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."compute_doctor_practice_style"("p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON TABLE "public"."hospital_specialty_patterns" TO "anon";
GRANT ALL ON TABLE "public"."hospital_specialty_patterns" TO "authenticated";
GRANT ALL ON TABLE "public"."hospital_specialty_patterns" TO "service_role";



GRANT ALL ON FUNCTION "public"."compute_hospital_specialty_patterns"("p_hospital_id" "uuid", "p_specialty" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."compute_hospital_specialty_patterns"("p_hospital_id" "uuid", "p_specialty" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."compute_hospital_specialty_patterns"("p_hospital_id" "uuid", "p_specialty" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."copy_hospital_investigation_to_doctor_rpc"("p_hospital_investigation_id" "uuid", "p_doctor_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."copy_hospital_investigation_to_doctor_rpc"("p_hospital_investigation_id" "uuid", "p_doctor_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."copy_hospital_investigation_to_doctor_rpc"("p_hospital_investigation_id" "uuid", "p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."copy_hospital_medicine_to_doctor_rpc"("p_hospital_medicine_id" "uuid", "p_doctor_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."copy_hospital_medicine_to_doctor_rpc"("p_hospital_medicine_id" "uuid", "p_doctor_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."copy_hospital_medicine_to_doctor_rpc"("p_hospital_medicine_id" "uuid", "p_doctor_id" "uuid") TO "service_role";



REVOKE ALL ON FUNCTION "public"."exec_sql"("sql_query" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."exec_sql"("sql_query" "text") TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_accuracy_metrics"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_group_by" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_accuracy_metrics"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_group_by" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_active_system_prompt_rpc"("p_consultation_type_code" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."get_active_system_prompt_rpc"("p_consultation_type_code" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_active_system_prompt_rpc"("p_consultation_type_code" character varying) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_active_template_for_doctor"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_active_template_for_doctor"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_active_template_for_doctor"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid") TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_ai_acceptance_metrics"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_group_by" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_ai_acceptance_metrics"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_group_by" "text") TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_avg_pipeline_timing"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_avg_pipeline_timing"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_client_request_count_last_hour"("p_client_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_client_request_count_last_hour"("p_client_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_client_request_count_last_hour"("p_client_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_comorbidity_pathway"("p_condition_code" "text", "p_comorbidity" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."get_comorbidity_pathway"("p_condition_code" "text", "p_comorbidity" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_comorbidity_pathway"("p_condition_code" "text", "p_comorbidity" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_condition_chunks"("p_condition_id" "uuid", "p_condition_code" "text", "p_chunk_types" "text"[]) TO "anon";
GRANT ALL ON FUNCTION "public"."get_condition_chunks"("p_condition_id" "uuid", "p_condition_code" "text", "p_chunk_types" "text"[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_condition_chunks"("p_condition_id" "uuid", "p_condition_code" "text", "p_chunk_types" "text"[]) TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_dashboard_summary"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_start_date" "date", "p_end_date" "date", "p_min_priority_score" integer) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_dashboard_summary"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_start_date" "date", "p_end_date" "date", "p_min_priority_score" integer) TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_dashboard_summary_v2"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_start_date" "date", "p_end_date" "date", "p_min_priority_score" integer) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_dashboard_summary_v2"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_start_date" "date", "p_end_date" "date", "p_min_priority_score" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_doctor_ehr_config"("p_doctor_id" "uuid", "p_template_code" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."get_doctor_ehr_config"("p_doctor_id" "uuid", "p_template_code" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_doctor_ehr_config"("p_doctor_id" "uuid", "p_template_code" character varying) TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_doctor_feedback_patterns"("p_doctor_id" "uuid") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_doctor_feedback_patterns"("p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_doctor_practice_style"("p_doctor_id" "uuid", "p_max_age_hours" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_doctor_practice_style"("p_doctor_id" "uuid", "p_max_age_hours" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_doctor_practice_style"("p_doctor_id" "uuid", "p_max_age_hours" integer) TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_doctor_preference_patterns"("p_doctor_id" "uuid") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_doctor_preference_patterns"("p_doctor_id" "uuid") TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_doctor_rejection_patterns"("p_doctor_id" "uuid") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_doctor_rejection_patterns"("p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_doctor_segment_configuration"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid", "p_template_id" "uuid", "p_mode" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."get_doctor_segment_configuration"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid", "p_template_id" "uuid", "p_mode" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_doctor_segment_configuration"("p_doctor_id" "uuid", "p_consultation_type_id" "uuid", "p_template_id" "uuid", "p_mode" character varying) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_enabled_triage_layers"("p_doctor_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_enabled_triage_layers"("p_doctor_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_enabled_triage_layers"("p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_hospital_default_ehr_type_id"("p_hospital_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_hospital_default_ehr_type_id"("p_hospital_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_hospital_default_ehr_type_id"("p_hospital_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_intervention_stats_by_doctor"("p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) TO "anon";
GRANT ALL ON FUNCTION "public"."get_intervention_stats_by_doctor"("p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_intervention_stats_by_doctor"("p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_investigation_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."get_investigation_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_investigation_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_medicine_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."get_medicine_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_medicine_feedback_history_rpc"("p_doctor_id" "uuid", "p_original_name" character varying) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_merge_lineage"("p_merged_extraction_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_merge_lineage"("p_merged_extraction_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_merge_lineage"("p_merged_extraction_id" "uuid") TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_notes_per_doctor_per_day"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_notes_per_doctor_per_day"("p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_patient_extraction_timeline"("p_patient_identifier" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."get_patient_extraction_timeline"("p_patient_identifier" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_patient_extraction_timeline"("p_patient_identifier" character varying) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_patient_triage_context"("p_patient_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_patient_triage_context"("p_patient_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_patient_triage_context"("p_patient_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_peer_comparison"("p_doctor_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_peer_comparison"("p_doctor_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_peer_comparison"("p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_pending_feedback_count_rpc"("p_doctor_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_pending_feedback_count_rpc"("p_doctor_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_pending_feedback_count_rpc"("p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_pending_investigation_feedback_count_rpc"("p_doctor_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_pending_investigation_feedback_count_rpc"("p_doctor_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_pending_investigation_feedback_count_rpc"("p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_processing_mode_config"("p_mode_code" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."get_processing_mode_config"("p_mode_code" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_processing_mode_config"("p_mode_code" character varying) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_red_flags_by_specialty"("p_specialty" "text", "p_include_emergency_triggers" boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."get_red_flags_by_specialty"("p_specialty" "text", "p_include_emergency_triggers" boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_red_flags_by_specialty"("p_specialty" "text", "p_include_emergency_triggers" boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_session_with_job"("p_correlation_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_session_with_job"("p_correlation_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_session_with_job"("p_correlation_id" "uuid") TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_template_by_code_unified"("p_doctor_id" "uuid", "p_template_code" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_template_by_code_unified"("p_doctor_id" "uuid", "p_template_code" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_template_performance_stats"("p_template_code" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."get_template_performance_stats"("p_template_code" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_template_performance_stats"("p_template_code" character varying) TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_usage_summary"("p_group_by" "text", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_api_client_id" "uuid", "p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_limit" integer, "p_offset" integer) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_usage_summary"("p_group_by" "text", "p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_api_client_id" "uuid", "p_hospital_id" "uuid", "p_doctor_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



REVOKE ALL ON FUNCTION "public"."get_usage_totals"("p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_api_client_id" "uuid", "p_hospital_id" "uuid", "p_doctor_id" "uuid") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."get_usage_totals"("p_date_from" timestamp with time zone, "p_date_to" timestamp with time zone, "p_api_client_id" "uuid", "p_hospital_id" "uuid", "p_doctor_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."mark_missed_followups"() TO "anon";
GRANT ALL ON FUNCTION "public"."mark_missed_followups"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."mark_missed_followups"() TO "service_role";






GRANT ALL ON FUNCTION "public"."notify_emotion_prompt_change"() TO "anon";
GRANT ALL ON FUNCTION "public"."notify_emotion_prompt_change"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."notify_emotion_prompt_change"() TO "service_role";



GRANT ALL ON FUNCTION "public"."prevent_audit_log_deletion"() TO "anon";
GRANT ALL ON FUNCTION "public"."prevent_audit_log_deletion"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."prevent_audit_log_deletion"() TO "service_role";



GRANT ALL ON FUNCTION "public"."record_template_performance"("p_template_id" "uuid", "p_session_id" "uuid", "p_transcription_model" character varying, "p_audio_duration" numeric, "p_processing_time" numeric, "p_extraction_time" numeric, "p_total_time" numeric, "p_transcript_length" integer, "p_insights_extracted" boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."record_template_performance"("p_template_id" "uuid", "p_session_id" "uuid", "p_transcription_model" character varying, "p_audio_duration" numeric, "p_processing_time" numeric, "p_extraction_time" numeric, "p_total_time" numeric, "p_transcript_length" integer, "p_insights_extracted" boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."record_template_performance"("p_template_id" "uuid", "p_session_id" "uuid", "p_transcription_model" character varying, "p_audio_duration" numeric, "p_processing_time" numeric, "p_extraction_time" numeric, "p_total_time" numeric, "p_transcript_length" integer, "p_insights_extracted" boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."save_patient_interventions"("p_extraction_id" "uuid", "p_interventions" "jsonb") TO "anon";
GRANT ALL ON FUNCTION "public"."save_patient_interventions"("p_extraction_id" "uuid", "p_interventions" "jsonb") TO "authenticated";
GRANT ALL ON FUNCTION "public"."save_patient_interventions"("p_extraction_id" "uuid", "p_interventions" "jsonb") TO "service_role";



GRANT ALL ON FUNCTION "public"."save_triage_suggestions"("p_extraction_id" "uuid", "p_doctor_id" "uuid", "p_suggestions" "jsonb", "p_patient_context" "jsonb") TO "anon";
GRANT ALL ON FUNCTION "public"."save_triage_suggestions"("p_extraction_id" "uuid", "p_doctor_id" "uuid", "p_suggestions" "jsonb", "p_patient_context" "jsonb") TO "authenticated";
GRANT ALL ON FUNCTION "public"."save_triage_suggestions"("p_extraction_id" "uuid", "p_doctor_id" "uuid", "p_suggestions" "jsonb", "p_patient_context" "jsonb") TO "service_role";



GRANT ALL ON FUNCTION "public"."search_by_icd_code"("p_icd_code" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."search_by_icd_code"("p_icd_code" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_by_icd_code"("p_icd_code" "text") TO "service_role";






GRANT ALL ON FUNCTION "public"."search_guidelines_by_keywords"("search_query" "text", "match_specialty" "text", "match_count" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."search_guidelines_by_keywords"("search_query" "text", "match_specialty" "text", "match_count" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_guidelines_by_keywords"("search_query" "text", "match_specialty" "text", "match_count" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."search_investigations_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_investigation_type" character varying, "p_limit" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."search_investigations_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_investigation_type" character varying, "p_limit" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_investigations_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_investigation_type" character varying, "p_limit" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."search_medicines_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_limit" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."search_medicines_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_limit" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_medicines_rpc"("p_doctor_id" "uuid", "p_search_term" character varying, "p_limit" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."update_client_last_used"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_client_last_used"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_client_last_used"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_doctor_templates_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_doctor_templates_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_doctor_templates_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_extraction_metrics_rpc"("p_consultation_type_code" character varying, "p_extraction_time_seconds" numeric) TO "anon";
GRANT ALL ON FUNCTION "public"."update_extraction_metrics_rpc"("p_consultation_type_code" character varying, "p_extraction_time_seconds" numeric) TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_extraction_metrics_rpc"("p_consultation_type_code" character varying, "p_extraction_time_seconds" numeric) TO "service_role";



GRANT ALL ON FUNCTION "public"."update_followup_tracking_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_followup_tracking_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_followup_tracking_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_hospital_ehr_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_hospital_ehr_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_hospital_ehr_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_intervention_outcomes_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_intervention_outcomes_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_intervention_outcomes_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_intervention_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_intervention_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_intervention_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_job_progress"("p_submission_id" "uuid", "p_status" character varying, "p_progress" integer, "p_message" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."update_job_progress"("p_submission_id" "uuid", "p_status" character varying, "p_progress" integer, "p_message" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_job_progress"("p_submission_id" "uuid", "p_status" character varying, "p_progress" integer, "p_message" "text") TO "service_role";



GRANT ALL ON TABLE "public"."triage_layer_config" TO "anon";
GRANT ALL ON TABLE "public"."triage_layer_config" TO "authenticated";
GRANT ALL ON TABLE "public"."triage_layer_config" TO "service_role";



GRANT ALL ON FUNCTION "public"."update_triage_layer_config"("p_layer_code" "text", "p_is_enabled" boolean, "p_weight" numeric) TO "anon";
GRANT ALL ON FUNCTION "public"."update_triage_layer_config"("p_layer_code" "text", "p_is_enabled" boolean, "p_weight" numeric) TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_triage_layer_config"("p_layer_code" "text", "p_is_enabled" boolean, "p_weight" numeric) TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";



GRANT ALL ON FUNCTION "public"."validate_merge_sources"("p_source_extraction_ids" "uuid"[]) TO "anon";
GRANT ALL ON FUNCTION "public"."validate_merge_sources"("p_source_extraction_ids" "uuid"[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."validate_merge_sources"("p_source_extraction_ids" "uuid"[]) TO "service_role";



GRANT ALL ON FUNCTION "public"."validate_segment_configuration"("p_doctor_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."validate_segment_configuration"("p_doctor_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."validate_segment_configuration"("p_doctor_id" "uuid") TO "service_role";




































GRANT ALL ON TABLE "public"."admin_action_log" TO "anon";
GRANT ALL ON TABLE "public"."admin_action_log" TO "authenticated";
GRANT ALL ON TABLE "public"."admin_action_log" TO "service_role";



GRANT ALL ON TABLE "public"."admin_users" TO "anon";
GRANT ALL ON TABLE "public"."admin_users" TO "authenticated";
GRANT ALL ON TABLE "public"."admin_users" TO "service_role";



GRANT ALL ON TABLE "public"."allied_health_needs" TO "anon";
GRANT ALL ON TABLE "public"."allied_health_needs" TO "authenticated";
GRANT ALL ON TABLE "public"."allied_health_needs" TO "service_role";



GRANT ALL ON TABLE "public"."api_client_usage" TO "anon";
GRANT ALL ON TABLE "public"."api_client_usage" TO "authenticated";
GRANT ALL ON TABLE "public"."api_client_usage" TO "service_role";



GRANT ALL ON TABLE "public"."api_clients" TO "anon";
GRANT ALL ON TABLE "public"."api_clients" TO "authenticated";
GRANT ALL ON TABLE "public"."api_clients" TO "service_role";



GRANT ALL ON TABLE "public"."app_settings" TO "anon";
GRANT ALL ON TABLE "public"."app_settings" TO "authenticated";
GRANT ALL ON TABLE "public"."app_settings" TO "service_role";



GRANT ALL ON TABLE "public"."audio_chunks" TO "anon";
GRANT ALL ON TABLE "public"."audio_chunks" TO "authenticated";
GRANT ALL ON TABLE "public"."audio_chunks" TO "service_role";



GRANT ALL ON TABLE "public"."audio_validation_warnings" TO "anon";
GRANT ALL ON TABLE "public"."audio_validation_warnings" TO "authenticated";
GRANT ALL ON TABLE "public"."audio_validation_warnings" TO "service_role";



GRANT ALL ON TABLE "public"."bill_line_items" TO "anon";
GRANT ALL ON TABLE "public"."bill_line_items" TO "authenticated";
GRANT ALL ON TABLE "public"."bill_line_items" TO "service_role";



GRANT ALL ON TABLE "public"."bills" TO "anon";
GRANT ALL ON TABLE "public"."bills" TO "authenticated";
GRANT ALL ON TABLE "public"."bills" TO "service_role";



GRANT ALL ON TABLE "public"."care_quality_risk" TO "anon";
GRANT ALL ON TABLE "public"."care_quality_risk" TO "authenticated";
GRANT ALL ON TABLE "public"."care_quality_risk" TO "service_role";



GRANT ALL ON TABLE "public"."clinical_chunk_embeddings" TO "anon";
GRANT ALL ON TABLE "public"."clinical_chunk_embeddings" TO "authenticated";
GRANT ALL ON TABLE "public"."clinical_chunk_embeddings" TO "service_role";



GRANT ALL ON TABLE "public"."clinical_chunks" TO "anon";
GRANT ALL ON TABLE "public"."clinical_chunks" TO "authenticated";
GRANT ALL ON TABLE "public"."clinical_chunks" TO "service_role";



GRANT ALL ON TABLE "public"."clinical_condition_ingestion_jobs" TO "anon";
GRANT ALL ON TABLE "public"."clinical_condition_ingestion_jobs" TO "authenticated";
GRANT ALL ON TABLE "public"."clinical_condition_ingestion_jobs" TO "service_role";



GRANT ALL ON TABLE "public"."clinical_conditions" TO "anon";
GRANT ALL ON TABLE "public"."clinical_conditions" TO "authenticated";
GRANT ALL ON TABLE "public"."clinical_conditions" TO "service_role";



GRANT ALL ON TABLE "public"."clinical_guideline_embeddings" TO "anon";
GRANT ALL ON TABLE "public"."clinical_guideline_embeddings" TO "authenticated";
GRANT ALL ON TABLE "public"."clinical_guideline_embeddings" TO "service_role";



GRANT ALL ON TABLE "public"."clinical_guidelines" TO "anon";
GRANT ALL ON TABLE "public"."clinical_guidelines" TO "authenticated";
GRANT ALL ON TABLE "public"."clinical_guidelines" TO "service_role";



GRANT ALL ON TABLE "public"."clinical_severity_assessments" TO "anon";
GRANT ALL ON TABLE "public"."clinical_severity_assessments" TO "authenticated";
GRANT ALL ON TABLE "public"."clinical_severity_assessments" TO "service_role";



GRANT ALL ON TABLE "public"."consultation_insights" TO "anon";
GRANT ALL ON TABLE "public"."consultation_insights" TO "authenticated";
GRANT ALL ON TABLE "public"."consultation_insights" TO "service_role";



GRANT ALL ON TABLE "public"."consultation_type_segments" TO "anon";
GRANT ALL ON TABLE "public"."consultation_type_segments" TO "authenticated";
GRANT ALL ON TABLE "public"."consultation_type_segments" TO "service_role";



GRANT ALL ON TABLE "public"."consultation_type_system_prompts" TO "anon";
GRANT ALL ON TABLE "public"."consultation_type_system_prompts" TO "authenticated";
GRANT ALL ON TABLE "public"."consultation_type_system_prompts" TO "service_role";



GRANT ALL ON TABLE "public"."consultation_types" TO "anon";
GRANT ALL ON TABLE "public"."consultation_types" TO "authenticated";
GRANT ALL ON TABLE "public"."consultation_types" TO "service_role";



GRANT ALL ON TABLE "public"."extraction_segments" TO "anon";
GRANT ALL ON TABLE "public"."extraction_segments" TO "authenticated";
GRANT ALL ON TABLE "public"."extraction_segments" TO "service_role";



GRANT ALL ON TABLE "public"."current_extraction_state" TO "anon";
GRANT ALL ON TABLE "public"."current_extraction_state" TO "authenticated";
GRANT ALL ON TABLE "public"."current_extraction_state" TO "service_role";



GRANT ALL ON TABLE "public"."doctor_doctor_patients" TO "anon";
GRANT ALL ON TABLE "public"."doctor_doctor_patients" TO "authenticated";
GRANT ALL ON TABLE "public"."doctor_doctor_patients" TO "service_role";



GRANT ALL ON TABLE "public"."doctor_investigations" TO "anon";
GRANT ALL ON TABLE "public"."doctor_investigations" TO "authenticated";
GRANT ALL ON TABLE "public"."doctor_investigations" TO "service_role";



GRANT ALL ON TABLE "public"."doctor_layer_preferences" TO "anon";
GRANT ALL ON TABLE "public"."doctor_layer_preferences" TO "authenticated";
GRANT ALL ON TABLE "public"."doctor_layer_preferences" TO "service_role";



GRANT ALL ON TABLE "public"."doctor_medicines" TO "anon";
GRANT ALL ON TABLE "public"."doctor_medicines" TO "authenticated";
GRANT ALL ON TABLE "public"."doctor_medicines" TO "service_role";



GRANT ALL ON TABLE "public"."doctor_segment_configurations_backup_014" TO "anon";
GRANT ALL ON TABLE "public"."doctor_segment_configurations_backup_014" TO "authenticated";
GRANT ALL ON TABLE "public"."doctor_segment_configurations_backup_014" TO "service_role";



GRANT ALL ON TABLE "public"."doctor_templates" TO "anon";
GRANT ALL ON TABLE "public"."doctor_templates" TO "authenticated";
GRANT ALL ON TABLE "public"."doctor_templates" TO "service_role";



GRANT ALL ON TABLE "public"."doctors" TO "anon";
GRANT ALL ON TABLE "public"."doctors" TO "authenticated";
GRANT ALL ON TABLE "public"."doctors" TO "service_role";



GRANT ALL ON TABLE "public"."ehr_types" TO "anon";
GRANT ALL ON TABLE "public"."ehr_types" TO "authenticated";
GRANT ALL ON TABLE "public"."ehr_types" TO "service_role";



GRANT ALL ON TABLE "public"."embedding_models" TO "anon";
GRANT ALL ON TABLE "public"."embedding_models" TO "authenticated";
GRANT ALL ON TABLE "public"."embedding_models" TO "service_role";



GRANT ALL ON TABLE "public"."extraction_accuracy_metrics" TO "anon";
GRANT ALL ON TABLE "public"."extraction_accuracy_metrics" TO "authenticated";
GRANT ALL ON TABLE "public"."extraction_accuracy_metrics" TO "service_role";



GRANT ALL ON TABLE "public"."extraction_edit_history" TO "anon";
GRANT ALL ON TABLE "public"."extraction_edit_history" TO "authenticated";
GRANT ALL ON TABLE "public"."extraction_edit_history" TO "service_role";



GRANT ALL ON TABLE "public"."extraction_embeddings" TO "anon";
GRANT ALL ON TABLE "public"."extraction_embeddings" TO "authenticated";
GRANT ALL ON TABLE "public"."extraction_embeddings" TO "service_role";



GRANT ALL ON TABLE "public"."extraction_photos" TO "anon";
GRANT ALL ON TABLE "public"."extraction_photos" TO "authenticated";
GRANT ALL ON TABLE "public"."extraction_photos" TO "service_role";



GRANT ALL ON TABLE "public"."extraction_relationships" TO "anon";
GRANT ALL ON TABLE "public"."extraction_relationships" TO "authenticated";
GRANT ALL ON TABLE "public"."extraction_relationships" TO "service_role";



GRANT ALL ON TABLE "public"."extraction_segment_comparison" TO "anon";
GRANT ALL ON TABLE "public"."extraction_segment_comparison" TO "authenticated";
GRANT ALL ON TABLE "public"."extraction_segment_comparison" TO "service_role";



GRANT ALL ON TABLE "public"."extraction_translations" TO "anon";
GRANT ALL ON TABLE "public"."extraction_translations" TO "authenticated";
GRANT ALL ON TABLE "public"."extraction_translations" TO "service_role";



GRANT ALL ON TABLE "public"."followup_tracking" TO "anon";
GRANT ALL ON TABLE "public"."followup_tracking" TO "authenticated";
GRANT ALL ON TABLE "public"."followup_tracking" TO "service_role";



GRANT ALL ON TABLE "public"."guideline_ingestion_jobs" TO "anon";
GRANT ALL ON TABLE "public"."guideline_ingestion_jobs" TO "authenticated";
GRANT ALL ON TABLE "public"."guideline_ingestion_jobs" TO "service_role";



GRANT ALL ON TABLE "public"."hospital_ehr" TO "anon";
GRANT ALL ON TABLE "public"."hospital_ehr" TO "authenticated";
GRANT ALL ON TABLE "public"."hospital_ehr" TO "service_role";



GRANT ALL ON TABLE "public"."hospital_intervention_pricing" TO "anon";
GRANT ALL ON TABLE "public"."hospital_intervention_pricing" TO "authenticated";
GRANT ALL ON TABLE "public"."hospital_intervention_pricing" TO "service_role";



GRANT ALL ON TABLE "public"."hospital_investigation_lists" TO "anon";
GRANT ALL ON TABLE "public"."hospital_investigation_lists" TO "authenticated";
GRANT ALL ON TABLE "public"."hospital_investigation_lists" TO "service_role";



GRANT ALL ON TABLE "public"."hospital_medicine_lists" TO "anon";
GRANT ALL ON TABLE "public"."hospital_medicine_lists" TO "authenticated";
GRANT ALL ON TABLE "public"."hospital_medicine_lists" TO "service_role";



GRANT ALL ON TABLE "public"."hospitals" TO "anon";
GRANT ALL ON TABLE "public"."hospitals" TO "authenticated";
GRANT ALL ON TABLE "public"."hospitals" TO "service_role";



GRANT ALL ON TABLE "public"."intervention_definitions" TO "anon";
GRANT ALL ON TABLE "public"."intervention_definitions" TO "authenticated";
GRANT ALL ON TABLE "public"."intervention_definitions" TO "service_role";



GRANT ALL ON TABLE "public"."medical_extractions" TO "anon";
GRANT ALL ON TABLE "public"."medical_extractions" TO "authenticated";
GRANT ALL ON TABLE "public"."medical_extractions" TO "service_role";



GRANT ALL ON TABLE "public"."patient_interventions" TO "anon";
GRANT ALL ON TABLE "public"."patient_interventions" TO "authenticated";
GRANT ALL ON TABLE "public"."patient_interventions" TO "service_role";



GRANT ALL ON TABLE "public"."recording_sessions" TO "anon";
GRANT ALL ON TABLE "public"."recording_sessions" TO "authenticated";
GRANT ALL ON TABLE "public"."recording_sessions" TO "service_role";



GRANT ALL ON TABLE "public"."intervention_analytics" TO "anon";
GRANT ALL ON TABLE "public"."intervention_analytics" TO "authenticated";
GRANT ALL ON TABLE "public"."intervention_analytics" TO "service_role";



GRANT ALL ON TABLE "public"."intervention_outcomes" TO "anon";
GRANT ALL ON TABLE "public"."intervention_outcomes" TO "authenticated";
GRANT ALL ON TABLE "public"."intervention_outcomes" TO "service_role";



GRANT ALL ON TABLE "public"."intervention_summary_stats" TO "anon";
GRANT ALL ON TABLE "public"."intervention_summary_stats" TO "authenticated";
GRANT ALL ON TABLE "public"."intervention_summary_stats" TO "service_role";



GRANT ALL ON TABLE "public"."investigation_list_uploads" TO "anon";
GRANT ALL ON TABLE "public"."investigation_list_uploads" TO "authenticated";
GRANT ALL ON TABLE "public"."investigation_list_uploads" TO "service_role";



GRANT ALL ON TABLE "public"."investigation_match_log" TO "anon";
GRANT ALL ON TABLE "public"."investigation_match_log" TO "authenticated";
GRANT ALL ON TABLE "public"."investigation_match_log" TO "service_role";



GRANT ALL ON TABLE "public"."llm_usage_log" TO "anon";
GRANT ALL ON TABLE "public"."llm_usage_log" TO "authenticated";
GRANT ALL ON TABLE "public"."llm_usage_log" TO "service_role";



GRANT ALL ON TABLE "public"."medicine_list_uploads" TO "anon";
GRANT ALL ON TABLE "public"."medicine_list_uploads" TO "authenticated";
GRANT ALL ON TABLE "public"."medicine_list_uploads" TO "service_role";



GRANT ALL ON TABLE "public"."medicine_match_log" TO "anon";
GRANT ALL ON TABLE "public"."medicine_match_log" TO "authenticated";
GRANT ALL ON TABLE "public"."medicine_match_log" TO "service_role";



GRANT ALL ON TABLE "public"."models_master" TO "anon";
GRANT ALL ON TABLE "public"."models_master" TO "authenticated";
GRANT ALL ON TABLE "public"."models_master" TO "service_role";



GRANT ALL ON TABLE "public"."nurse_doctors" TO "anon";
GRANT ALL ON TABLE "public"."nurse_doctors" TO "authenticated";
GRANT ALL ON TABLE "public"."nurse_doctors" TO "service_role";



GRANT ALL ON TABLE "public"."nurse_templates" TO "anon";
GRANT ALL ON TABLE "public"."nurse_templates" TO "authenticated";
GRANT ALL ON TABLE "public"."nurse_templates" TO "service_role";



GRANT ALL ON TABLE "public"."nurses" TO "anon";
GRANT ALL ON TABLE "public"."nurses" TO "authenticated";
GRANT ALL ON TABLE "public"."nurses" TO "service_role";



GRANT ALL ON TABLE "public"."other_clinical_needs" TO "anon";
GRANT ALL ON TABLE "public"."other_clinical_needs" TO "authenticated";
GRANT ALL ON TABLE "public"."other_clinical_needs" TO "service_role";



GRANT ALL ON TABLE "public"."patient_dropoff_risk" TO "anon";
GRANT ALL ON TABLE "public"."patient_dropoff_risk" TO "authenticated";
GRANT ALL ON TABLE "public"."patient_dropoff_risk" TO "service_role";



GRANT ALL ON TABLE "public"."patient_sharing" TO "anon";
GRANT ALL ON TABLE "public"."patient_sharing" TO "authenticated";
GRANT ALL ON TABLE "public"."patient_sharing" TO "service_role";



GRANT ALL ON TABLE "public"."patients" TO "anon";
GRANT ALL ON TABLE "public"."patients" TO "authenticated";
GRANT ALL ON TABLE "public"."patients" TO "service_role";



GRANT ALL ON TABLE "public"."phi_audit_log" TO "anon";
GRANT ALL ON TABLE "public"."phi_audit_log" TO "authenticated";
GRANT ALL ON TABLE "public"."phi_audit_log" TO "service_role";



GRANT ALL ON TABLE "public"."procedure_fee_master" TO "anon";
GRANT ALL ON TABLE "public"."procedure_fee_master" TO "authenticated";
GRANT ALL ON TABLE "public"."procedure_fee_master" TO "service_role";



GRANT ALL ON TABLE "public"."processing_jobs" TO "anon";
GRANT ALL ON TABLE "public"."processing_jobs" TO "authenticated";
GRANT ALL ON TABLE "public"."processing_jobs" TO "service_role";



GRANT ALL ON TABLE "public"."processing_modes" TO "anon";
GRANT ALL ON TABLE "public"."processing_modes" TO "authenticated";
GRANT ALL ON TABLE "public"."processing_modes" TO "service_role";



GRANT ALL ON TABLE "public"."qa_engine_settings" TO "anon";
GRANT ALL ON TABLE "public"."qa_engine_settings" TO "authenticated";
GRANT ALL ON TABLE "public"."qa_engine_settings" TO "service_role";



GRANT ALL ON TABLE "public"."qa_query_history" TO "anon";
GRANT ALL ON TABLE "public"."qa_query_history" TO "authenticated";
GRANT ALL ON TABLE "public"."qa_query_history" TO "service_role";



GRANT ALL ON TABLE "public"."radiology_plan_library" TO "anon";
GRANT ALL ON TABLE "public"."radiology_plan_library" TO "authenticated";
GRANT ALL ON TABLE "public"."radiology_plan_library" TO "service_role";



GRANT ALL ON TABLE "public"."radiology_toxicity_library" TO "anon";
GRANT ALL ON TABLE "public"."radiology_toxicity_library" TO "authenticated";
GRANT ALL ON TABLE "public"."radiology_toxicity_library" TO "service_role";



GRANT ALL ON TABLE "public"."realtime_extraction_responses" TO "anon";
GRANT ALL ON TABLE "public"."realtime_extraction_responses" TO "authenticated";
GRANT ALL ON TABLE "public"."realtime_extraction_responses" TO "service_role";



GRANT ALL ON TABLE "public"."refresh_tokens" TO "anon";
GRANT ALL ON TABLE "public"."refresh_tokens" TO "authenticated";
GRANT ALL ON TABLE "public"."refresh_tokens" TO "service_role";



GRANT ALL ON TABLE "public"."room_rate_master" TO "anon";
GRANT ALL ON TABLE "public"."room_rate_master" TO "authenticated";
GRANT ALL ON TABLE "public"."room_rate_master" TO "service_role";



GRANT ALL ON TABLE "public"."segment_definitions" TO "anon";
GRANT ALL ON TABLE "public"."segment_definitions" TO "authenticated";
GRANT ALL ON TABLE "public"."segment_definitions" TO "service_role";



GRANT ALL ON TABLE "public"."segment_embeddings" TO "anon";
GRANT ALL ON TABLE "public"."segment_embeddings" TO "authenticated";
GRANT ALL ON TABLE "public"."segment_embeddings" TO "service_role";



GRANT ALL ON TABLE "public"."session_audit_log" TO "anon";
GRANT ALL ON TABLE "public"."session_audit_log" TO "authenticated";
GRANT ALL ON TABLE "public"."session_audit_log" TO "service_role";



GRANT ALL ON TABLE "public"."specialty_benchmarks" TO "anon";
GRANT ALL ON TABLE "public"."specialty_benchmarks" TO "authenticated";
GRANT ALL ON TABLE "public"."specialty_benchmarks" TO "service_role";



GRANT ALL ON TABLE "public"."system_prompt_components" TO "anon";
GRANT ALL ON TABLE "public"."system_prompt_components" TO "authenticated";
GRANT ALL ON TABLE "public"."system_prompt_components" TO "service_role";



GRANT ALL ON TABLE "public"."system_prompt_config_components" TO "anon";
GRANT ALL ON TABLE "public"."system_prompt_config_components" TO "authenticated";
GRANT ALL ON TABLE "public"."system_prompt_config_components" TO "service_role";



GRANT ALL ON TABLE "public"."system_prompt_configurations" TO "anon";
GRANT ALL ON TABLE "public"."system_prompt_configurations" TO "authenticated";
GRANT ALL ON TABLE "public"."system_prompt_configurations" TO "service_role";



GRANT ALL ON TABLE "public"."temp_audio_files" TO "anon";
GRANT ALL ON TABLE "public"."temp_audio_files" TO "authenticated";
GRANT ALL ON TABLE "public"."temp_audio_files" TO "service_role";



GRANT ALL ON TABLE "public"."template_ehr" TO "anon";
GRANT ALL ON TABLE "public"."template_ehr" TO "authenticated";
GRANT ALL ON TABLE "public"."template_ehr" TO "service_role";



GRANT ALL ON TABLE "public"."template_segments" TO "anon";
GRANT ALL ON TABLE "public"."template_segments" TO "authenticated";
GRANT ALL ON TABLE "public"."template_segments" TO "service_role";



GRANT ALL ON TABLE "public"."template_standard_texts" TO "anon";
GRANT ALL ON TABLE "public"."template_standard_texts" TO "authenticated";
GRANT ALL ON TABLE "public"."template_standard_texts" TO "service_role";



GRANT ALL ON TABLE "public"."templates" TO "anon";
GRANT ALL ON TABLE "public"."templates" TO "authenticated";
GRANT ALL ON TABLE "public"."templates" TO "service_role";



GRANT ALL ON TABLE "public"."triage_conflict_log" TO "anon";
GRANT ALL ON TABLE "public"."triage_conflict_log" TO "authenticated";
GRANT ALL ON TABLE "public"."triage_conflict_log" TO "service_role";



GRANT ALL ON TABLE "public"."triage_feedback" TO "anon";
GRANT ALL ON TABLE "public"."triage_feedback" TO "authenticated";
GRANT ALL ON TABLE "public"."triage_feedback" TO "service_role";



GRANT ALL ON TABLE "public"."triage_suggestion_log" TO "anon";
GRANT ALL ON TABLE "public"."triage_suggestion_log" TO "authenticated";
GRANT ALL ON TABLE "public"."triage_suggestion_log" TO "service_role";



GRANT ALL ON TABLE "public"."triage_doctor_stats" TO "anon";
GRANT ALL ON TABLE "public"."triage_doctor_stats" TO "authenticated";
GRANT ALL ON TABLE "public"."triage_doctor_stats" TO "service_role";



GRANT ALL ON TABLE "public"."triage_suggestion_analytics" TO "anon";
GRANT ALL ON TABLE "public"."triage_suggestion_analytics" TO "authenticated";
GRANT ALL ON TABLE "public"."triage_suggestion_analytics" TO "service_role";



GRANT ALL ON TABLE "public"."v_api_client_usage_summary" TO "anon";
GRANT ALL ON TABLE "public"."v_api_client_usage_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."v_api_client_usage_summary" TO "service_role";



GRANT ALL ON TABLE "public"."v_consultation_type_summary" TO "anon";
GRANT ALL ON TABLE "public"."v_consultation_type_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."v_consultation_type_summary" TO "service_role";



GRANT ALL ON TABLE "public"."v_daily_usage_summary" TO "anon";
GRANT ALL ON TABLE "public"."v_daily_usage_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."v_daily_usage_summary" TO "service_role";



GRANT ALL ON TABLE "public"."v_doctor_usage_summary" TO "anon";
GRANT ALL ON TABLE "public"."v_doctor_usage_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."v_doctor_usage_summary" TO "service_role";



GRANT ALL ON TABLE "public"."v_doctor_usage_summary_v2" TO "anon";
GRANT ALL ON TABLE "public"."v_doctor_usage_summary_v2" TO "authenticated";
GRANT ALL ON TABLE "public"."v_doctor_usage_summary_v2" TO "service_role";



GRANT ALL ON TABLE "public"."v_hospital_accuracy_metrics" TO "anon";
GRANT ALL ON TABLE "public"."v_hospital_accuracy_metrics" TO "authenticated";
GRANT ALL ON TABLE "public"."v_hospital_accuracy_metrics" TO "service_role";



GRANT ALL ON TABLE "public"."v_hospital_usage_summary" TO "anon";
GRANT ALL ON TABLE "public"."v_hospital_usage_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."v_hospital_usage_summary" TO "service_role";



GRANT ALL ON TABLE "public"."v_session_usage_summary" TO "anon";
GRANT ALL ON TABLE "public"."v_session_usage_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."v_session_usage_summary" TO "service_role";



GRANT ALL ON TABLE "public"."v_template_configurations" TO "anon";
GRANT ALL ON TABLE "public"."v_template_configurations" TO "authenticated";
GRANT ALL ON TABLE "public"."v_template_configurations" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";
































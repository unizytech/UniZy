-- =====================================================================================
-- Career Counselling template (CAREER_DISCUSSION) + its segment links
-- =====================================================================================
-- The CAREER_DISCUSSION template was originally created by hand in dev's UI and was never
-- captured in a migration, so it did not propagate to main. This migration recreates it
-- as tracked schema so dev and main stay in sync.
--
-- Idempotent: same fixed UUID as dev (af2cbe73-...) + ON CONFLICT.
--   - templates:         ON CONFLICT (id) -> only re-asserts is_active (won't clobber
--                        dev's assembled_full_prompt / assembled_schema_json).
--   - template_segments: ON CONFLICT (template_id, segment_id) -> the table's unique key.
-- Mirrors consultation_type_segments for CAREER_COUNSELLING (same 12 segments / order /
-- category / brevity / terminology). The app (re)assembles the template prompt+schema on
-- demand, so assembled_* columns are left NULL on a fresh insert.
-- =====================================================================================

-- 1. Template ---------------------------------------------------------------------------
INSERT INTO templates (id, template_code, template_name, description, use_case, is_active, is_default,
                       consultation_type_id, system_prompt_config_id)
VALUES (
  'af2cbe73-92f8-4985-92a0-acc866b17ce4',
  'CAREER_DISCUSSION',
  'Career Counselling discussion',
  'Career Counselling discussion',
  'detailed_review',
  true,
  false,
  'ca12e500-0000-4000-8000-000000000001',   -- consultation_type CAREER_COUNSELLING
  'ca12e500-0000-4000-8000-0000000000c0'    -- system prompt config CAREER_COUNSELLING_CORE
)
ON CONFLICT (id) DO UPDATE
SET is_active = true,
    consultation_type_id = EXCLUDED.consultation_type_id,
    system_prompt_config_id = EXCLUDED.system_prompt_config_id,
    updated_at = now();

-- 2. Template segments (12) -------------------------------------------------------------
INSERT INTO template_segments (template_id, segment_id, segment_code, category, display_order, brevity_level, terminology_style)
VALUES
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b0','PARTICIPANTS','core',0,'concise','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b1','KEY_FACTS','core',5,'concise','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b2','STUDENT_CONTEXT','core',10,'detailed','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b3','WORK_EXPERIENCE','additional',30,'balanced','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b4','ACADEMICS','core',40,'detailed','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b5','SUPERCURRICULAR_ACTIVITIES','core',50,'detailed','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b6','FUTURE_GOALS','core',60,'balanced','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b7','TASKS','core',65,'balanced','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b8','NEXT_STEPS','core',70,'balanced','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000b9','ASSESSMENT_METERS','additional',80,'balanced','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000ba','DIRECTIONAL_CHANGES','additional',90,'balanced','simple_terms'),
('af2cbe73-92f8-4985-92a0-acc866b17ce4','ca12e500-0000-4000-8000-0000000000bb','COUNSELLOR_REMARKS','additional',100,'balanced','simple_terms')
ON CONFLICT (template_id, segment_id) DO UPDATE
SET segment_code = EXCLUDED.segment_code,
    category = EXCLUDED.category,
    display_order = EXCLUDED.display_order,
    brevity_level = EXCLUDED.brevity_level,
    terminology_style = EXCLUDED.terminology_style;

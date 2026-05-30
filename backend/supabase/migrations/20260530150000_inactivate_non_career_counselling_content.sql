-- =====================================================================================
-- Soft-delete (inactivate) all non-career-counselling content
-- =====================================================================================
-- Narrows the active catalogue down to the Career Counselling flow only, by setting
-- is_active = false on every consultation type, template and segment definition that is
-- NOT required by the Career Counselling consultation type / template.
--
-- REVERSIBLE: this only flips is_active flags; no rows are deleted. To restore a row,
-- set is_active = true again. Nothing here touches the data itself.
--
-- KEEP-SET (stays active):
--   * consultation_type  CAREER_COUNSELLING   (id ca12e500-...001)
--   * template           CAREER_DISCUSSION    (any template whose consultation_type_id
--                                              is the career type)
--   * segment_definitions used by the career consultation type OR the career template
--     (the 12 PARTICIPANTS .. COUNSELLOR_REMARKS segments, ids ca12e500-...b0..bb)
--
-- NOTE: this intentionally retires the legacy healthcare catalogue earlier than the
-- Phase 5/6 default in the repurposing plan, per explicit request. doctor_templates
-- (per-doctor activations) are deliberately left untouched - they are moot once their
-- template is inactive and can be cleaned up separately if desired.
-- =====================================================================================

-- 1. Consultation types: keep only CAREER_COUNSELLING ---------------------------------
UPDATE consultation_types
SET is_active = false,
    updated_at = now()
WHERE is_active = true
  AND type_code <> 'CAREER_COUNSELLING';

-- 2. Templates: keep only template(s) tied to the career consultation type ------------
--    (covers templates with a NULL consultation_type_id too).
UPDATE templates
SET is_active = false,
    updated_at = now()
WHERE is_active = true
  AND consultation_type_id IS DISTINCT FROM 'ca12e500-0000-4000-8000-000000000001';

-- 3. Segment definitions: keep only segments referenced by the career type/template ---
--    NOT EXISTS is null-safe; any segment wired into the career flow (now or later)
--    is preserved automatically.
UPDATE segment_definitions sd
SET is_active = false,
    updated_at = now()
WHERE sd.is_active = true
  AND NOT EXISTS (
        SELECT 1
        FROM consultation_type_segments cts
        WHERE cts.segment_id = sd.id
          AND cts.consultation_type_id = 'ca12e500-0000-4000-8000-000000000001'
      )
  AND NOT EXISTS (
        SELECT 1
        FROM template_segments ts
        JOIN templates t ON t.id = ts.template_id
        WHERE ts.segment_id = sd.id
          AND t.consultation_type_id = 'ca12e500-0000-4000-8000-000000000001'
      );

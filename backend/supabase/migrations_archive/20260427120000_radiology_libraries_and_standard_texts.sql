-- Radiology plan + toxicity libraries and per-template standard texts
-- Per-template global (no hospital scoping). Library content is substituted into
-- segment_definitions.prompt_section_text placeholders {{LIBRARY_PLAN}} /
-- {{LIBRARY_TOXICITY}} during template assembly. Standard texts are merged into
-- the extraction JSON before EHR dispatch (consumed by the formatter layer).

CREATE TABLE IF NOT EXISTS radiology_plan_library (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    plan_code VARCHAR(64) NOT NULL,
    plan_name VARCHAR(255) NOT NULL,
    rt_intent VARCHAR(64),
    rt_indication TEXT,
    rt_dose_gy VARCHAR(32),
    rt_fractions VARCHAR(32),
    rt_dose_per_fraction_gy VARCHAR(32),
    rt_weeks VARCHAR(32),
    rt_technique VARCHAR(128),
    concurrent_systemic_therapy TEXT,
    display_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (template_id, plan_code)
);

CREATE INDEX IF NOT EXISTS idx_radiology_plan_library_template
    ON radiology_plan_library(template_id) WHERE is_active;

CREATE TABLE IF NOT EXISTS radiology_toxicity_library (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    toxicity_code VARCHAR(64) NOT NULL,
    phase VARCHAR(16) NOT NULL CHECK (phase IN ('early','late')),
    text TEXT NOT NULL,
    conditional_trigger VARCHAR(64),
    display_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (template_id, toxicity_code)
);

CREATE INDEX IF NOT EXISTS idx_radiology_toxicity_library_template
    ON radiology_toxicity_library(template_id, phase) WHERE is_active;

CREATE TABLE IF NOT EXISTS template_standard_texts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    key VARCHAR(64) NOT NULL,
    label VARCHAR(255),
    text TEXT NOT NULL,
    display_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (template_id, key)
);

CREATE INDEX IF NOT EXISTS idx_template_standard_texts_template
    ON template_standard_texts(template_id) WHERE is_active;

COMMENT ON TABLE radiology_plan_library IS 'Per-template plan templates substituted into PLAN segment {{LIBRARY_PLAN}} placeholder';
COMMENT ON TABLE radiology_toxicity_library IS 'Per-template early/late toxicity items substituted into TOXICITY segment {{LIBRARY_TOXICITY}} placeholder';
COMMENT ON COLUMN radiology_toxicity_library.conditional_trigger IS 'Optional trigger flag (e.g. BRACHYTHERAPY, SCF, LEFT_HEART) for items only included when trigger is met. Mirrors prompt id-prefix conventions GY_BR_*, BR_SCF_*, BR_LH_*.';
COMMENT ON TABLE template_standard_texts IS 'Per-template named text blocks merged into extraction JSON before EHR dispatch';

-- Create extraction_translations table for storing Indic language translations of extractions

CREATE TABLE IF NOT EXISTS extraction_translations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    target_language VARCHAR(20) NOT NULL,

    -- AI translation (immutable original)
    translated_extraction_json JSONB NOT NULL,

    -- Doctor-edited translation (NULL if unedited)
    edited_translated_json JSONB DEFAULT NULL,

    -- Edit tracking
    translation_edit_count INTEGER DEFAULT 0,
    last_translation_edited_at TIMESTAMPTZ,
    last_translation_edited_by UUID,
    translation_edited_by_type VARCHAR(10),

    -- Processing status
    translation_started BOOLEAN DEFAULT FALSE,
    translation_completed BOOLEAN DEFAULT FALSE,
    translation_failed BOOLEAN DEFAULT FALSE,
    translation_error TEXT,
    translation_time_seconds NUMERIC(10,2),
    model_used VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(extraction_id, target_language)
);

-- Index for fast lookups by extraction_id
CREATE INDEX IF NOT EXISTS idx_extraction_translations_extraction_id
ON extraction_translations(extraction_id);

-- RLS policies
ALTER TABLE extraction_translations ENABLE ROW LEVEL SECURITY;

-- Service role can do everything
CREATE POLICY "Service role full access on extraction_translations"
ON extraction_translations
FOR ALL
USING (true)
WITH CHECK (true);

COMMENT ON TABLE extraction_translations IS 'Stores Indic language translations of medical extractions with independent edit tracking';

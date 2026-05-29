-- Add formatter_code column to templates table
-- Indicates which EHR formatter (if any) should be applied to the extraction
-- before sending to the target EHR API. NULL = no formatter (raw extraction).

ALTER TABLE templates
ADD COLUMN IF NOT EXISTS formatter_code VARCHAR(50);

COMMENT ON COLUMN templates.formatter_code IS
'EHR formatter identifier (e.g., aosta, raster_op, raster_new_op, neopead, kg_initial, kg_reassess). NULL = no formatter.';

-- Partial index for fast lookup of templates with formatters
CREATE INDEX IF NOT EXISTS idx_templates_formatter_code
ON templates(formatter_code)
WHERE formatter_code IS NOT NULL;

-- Backfill known formatters
UPDATE templates SET formatter_code = 'aosta'          WHERE template_code = 'AOSTA_OP'        AND formatter_code IS NULL;
UPDATE templates SET formatter_code = 'raster_op'      WHERE template_code = 'RASTER_OP'       AND formatter_code IS NULL;
UPDATE templates SET formatter_code = 'raster_new_op'  WHERE template_code = 'RASTER_NEW_OP'   AND formatter_code IS NULL;
UPDATE templates SET formatter_code = 'kg_initial'     WHERE template_code = 'CARDIO_INITIAL'  AND formatter_code IS NULL;
UPDATE templates SET formatter_code = 'kg_reassess'    WHERE template_code = 'CARDIO_REASSESS' AND formatter_code IS NULL;
UPDATE templates SET formatter_code = 'neopead'        WHERE template_code LIKE 'NEO_%'        AND formatter_code IS NULL;

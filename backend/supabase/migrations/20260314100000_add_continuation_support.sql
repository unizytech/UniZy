-- Add continuation support columns to medical_extractions
-- is_continuation: marks whether this extraction continues a prior consultation in the same visit
-- parent_extraction_ids: full chain of prior extraction IDs in the same visit

ALTER TABLE public.medical_extractions
ADD COLUMN IF NOT EXISTS is_continuation BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN public.medical_extractions.is_continuation
IS 'Whether this extraction is a continuation of a prior consultation in the same visit';

CREATE INDEX IF NOT EXISTS idx_medical_extractions_is_continuation
ON public.medical_extractions(is_continuation) WHERE is_continuation = TRUE;

ALTER TABLE public.medical_extractions
ADD COLUMN IF NOT EXISTS parent_extraction_ids UUID[] DEFAULT '{}';

COMMENT ON COLUMN public.medical_extractions.parent_extraction_ids
IS 'Array of extraction IDs from prior recordings in the same visit chain';

CREATE INDEX IF NOT EXISTS idx_medical_extractions_parent_ids
ON public.medical_extractions USING GIN (parent_extraction_ids)
WHERE parent_extraction_ids != '{}';

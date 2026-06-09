-- Add reference_payload_json to extractions.
--
-- Stores the extraction conformed to the web app's reference media-object envelope
-- (references/updated_meeting_response_structure.json): a customBusinessInsights[]
-- array + media wrapper + array-form metadata + transcription.
--
-- This is stored ALONGSIDE original_extraction_json (the keyed-insights shape that
-- the frontend, EHR formatters, realtime publish, segment rebuild, edit-tracking and
-- merge all consume). It is NOT a replacement — internal consumers keep reading the
-- keyed columns; outward-facing consumers read this one.

ALTER TABLE public.extractions
  ADD COLUMN IF NOT EXISTS reference_payload_json jsonb;

COMMENT ON COLUMN public.extractions.reference_payload_json IS
  'Extraction conformed to the web app reference envelope (customBusinessInsights media object). Built by services/reference_envelope_builder.py. Stored alongside (not replacing) original_extraction_json.';

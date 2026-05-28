ALTER TABLE medical_extractions
ADD COLUMN IF NOT EXISTS ehr_payload_json JSONB DEFAULT NULL;

COMMENT ON COLUMN medical_extractions.ehr_payload_json IS
  'Formatted EHR payload (lookup-normalized for Neopaed, Aosta/Raster-formatted). Updated on creation, edit, and EHR send.';

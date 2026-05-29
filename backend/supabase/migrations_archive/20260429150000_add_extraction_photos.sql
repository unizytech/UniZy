-- Migration: Add extraction_photos table for attaching photos/images to medical extractions
-- Date: 2026-04-29

-- ============================================================================
-- Table: extraction_photos
-- Stores metadata for photos uploaded against a medical_extractions row.
-- Files themselves live in the 'extraction-photos' Supabase Storage bucket;
-- storage_path is the object path within that bucket.
-- ============================================================================

CREATE TABLE IF NOT EXISTS extraction_photos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  original_filename TEXT,
  storage_path TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size_bytes BIGINT NOT NULL,
  uploaded_by UUID,
  uploaded_by_type VARCHAR(20),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_extraction_photos_extraction_id
  ON extraction_photos(extraction_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_extraction_photos_storage_path
  ON extraction_photos(storage_path);

COMMENT ON TABLE extraction_photos IS
'Photos/images attached to a medical_extractions row. Cascades on extraction delete; storage objects must be cleaned up by the backend service.';

COMMENT ON COLUMN extraction_photos.label IS 'User-provided caption for the photo.';
COMMENT ON COLUMN extraction_photos.storage_path IS 'Object path within the extraction-photos bucket.';
COMMENT ON COLUMN extraction_photos.uploaded_by_type IS 'Client type that uploaded: admin | web_app | ehr.';

-- ============================================================================
-- Manual step required after migration:
-- ============================================================================
--
-- Create storage bucket via Supabase Dashboard:
--    - Bucket name: 'extraction-photos'
--    - Public: false
--    - File size limit: 10485760 (10MB)
--    - Allowed MIME types: image/jpeg, image/png, image/webp, image/heic, image/heif
--
-- Note: ON DELETE CASCADE removes the metadata row when the parent extraction is
-- deleted, but does not remove the storage object. The backend delete endpoint
-- handles storage cleanup; cascaded deletes leave orphaned files in the bucket.

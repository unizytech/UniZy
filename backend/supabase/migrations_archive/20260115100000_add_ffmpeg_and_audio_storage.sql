-- Migration: Add FFmpeg stitching config, temp audio storage, and validation warnings
-- Date: 2026-01-15

-- ============================================================================
-- Part 1: Add FFmpeg config to hospitals table
-- ============================================================================

ALTER TABLE hospitals
ADD COLUMN IF NOT EXISTS use_ffmpeg_stitching BOOLEAN DEFAULT false;

COMMENT ON COLUMN hospitals.use_ffmpeg_stitching IS
'When true, use FFmpeg for audio stitching instead of simple concatenation. Produces better quality but adds ~1-2s processing time.';

-- ============================================================================
-- Part 2: Create table to store audio validation warnings
-- ============================================================================

CREATE TABLE IF NOT EXISTS audio_validation_warnings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
  chunk_index INTEGER,
  warning_type TEXT NOT NULL,  -- 'mime_unsupported', 'mime_mismatch', 'format_detection_failed'
  declared_mime_type TEXT,
  detected_format TEXT,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_warnings_session ON audio_validation_warnings(session_id);
CREATE INDEX IF NOT EXISTS idx_validation_warnings_created ON audio_validation_warnings(created_at);

COMMENT ON TABLE audio_validation_warnings IS
'Stores audio validation warnings for debugging. Warnings are logged when MIME type mismatches or unsupported formats are detected.';

-- ============================================================================
-- Part 3: Create table to track temp audio files for cleanup
-- ============================================================================

CREATE TABLE IF NOT EXISTS temp_audio_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  storage_path TEXT NOT NULL,
  session_id UUID REFERENCES recording_sessions(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);

CREATE INDEX IF NOT EXISTS idx_temp_audio_expires ON temp_audio_files(expires_at);
CREATE INDEX IF NOT EXISTS idx_temp_audio_session ON temp_audio_files(session_id);

COMMENT ON TABLE temp_audio_files IS
'Tracks temporary audio files in Supabase Storage for 24-hour auto-cleanup via pg_cron.';

-- ============================================================================
-- Part 4: Enable pg_cron extension for scheduled cleanup jobs
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;

-- ============================================================================
-- Part 5: pg_cron job to delete expired audio files (runs every hour)
-- ============================================================================

-- Schedule cleanup job (runs at minute 0 of every hour)
-- Uses DO block to handle case where job already exists
DO $$
BEGIN
  -- Check if job already exists
  IF NOT EXISTS (
    SELECT 1 FROM cron.job WHERE jobname = 'cleanup-temp-audio'
  ) THEN
    PERFORM cron.schedule(
      'cleanup-temp-audio',
      '0 * * * *',
      'DELETE FROM temp_audio_files WHERE expires_at < NOW();'
    );
  END IF;
END;
$$;

-- ============================================================================
-- Manual step required after migration:
-- ============================================================================
--
-- Create storage bucket via Supabase Dashboard:
--    - Bucket name: 'temp-audio'
--    - Public: false
--    - File size limit: 52428800 (50MB)
--    - Allowed MIME types: audio/wav, audio/mp3, audio/mpeg, audio/aiff, audio/aac,
--                          audio/ogg, audio/flac, audio/webm, audio/mp4, audio/m4a
--
-- Note: The cleanup job only deletes tracking records from temp_audio_files table.
-- Storage file cleanup is handled by the backend service.

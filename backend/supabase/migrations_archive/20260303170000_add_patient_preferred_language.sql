-- Add preferred_language column to patients table
-- Stores the detected spoken language from audio transcription (e.g., Tamil, Hindi, English)
ALTER TABLE public.patients
ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(50) DEFAULT NULL;

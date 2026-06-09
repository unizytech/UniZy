-- Add per-school toggle for the early audio-quality hard-stop.
-- When enabled, the backend analyses the first ~30s of accumulated audio during
-- recording and, if the audio is clearly dead (silent / no speech / far below the
-- volume floor), returns abort=true on the next chunk upload so the client stops
-- recording immediately instead of waiting for full processing.
--
-- Default false: opt-in for dev + a pilot school before any wider rollout.
-- Reuses the existing min_rms_db / enable_audio_validation knobs for thresholds.

ALTER TABLE "public"."schools"
    ADD COLUMN IF NOT EXISTS "enable_early_quality_abort" boolean DEFAULT false;

COMMENT ON COLUMN "public"."schools"."enable_early_quality_abort" IS
    'When true, abort recording early (~30s) if accumulated audio is clearly unusable (dead/silent/no speech). Default false.';

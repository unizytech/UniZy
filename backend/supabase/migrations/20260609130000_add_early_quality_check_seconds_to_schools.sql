-- Configurable interval (seconds of accumulated audio) at which the early
-- audio-quality hard-stop check fires. Pairs with enable_early_quality_abort.
-- Default 30s. Only meaningful when enable_early_quality_abort = true.

ALTER TABLE "public"."schools"
    ADD COLUMN IF NOT EXISTS "early_quality_check_seconds" integer DEFAULT 30;

COMMENT ON COLUMN "public"."schools"."early_quality_check_seconds" IS
    'Seconds of accumulated audio after which the early quality check runs (when enable_early_quality_abort is true). Default 30.';

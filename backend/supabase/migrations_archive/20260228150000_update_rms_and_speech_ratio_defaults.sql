-- Update default values: min_rms_db from -40 to -57, min_speech_ratio from 0.10 to 0 (disabled)
ALTER TABLE hospitals ALTER COLUMN min_rms_db SET DEFAULT -57.0;
ALTER TABLE hospitals ALTER COLUMN min_speech_ratio SET DEFAULT 0.0;

-- Update existing rows that still have old defaults
UPDATE hospitals SET min_rms_db = -57.0 WHERE min_rms_db = -40.0;
UPDATE hospitals SET min_speech_ratio = 0.0 WHERE min_speech_ratio = 0.10;

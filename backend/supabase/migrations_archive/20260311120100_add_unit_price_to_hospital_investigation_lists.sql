-- Add unit_price column to hospital_investigation_lists for billing
ALTER TABLE hospital_investigation_lists ADD COLUMN IF NOT EXISTS unit_price NUMERIC(10,2) DEFAULT NULL;

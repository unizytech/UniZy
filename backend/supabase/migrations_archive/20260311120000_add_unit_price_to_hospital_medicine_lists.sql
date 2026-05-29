-- Add unit_price column to hospital_medicine_lists for billing
ALTER TABLE hospital_medicine_lists ADD COLUMN IF NOT EXISTS unit_price NUMERIC(10,2) DEFAULT NULL;

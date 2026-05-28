-- Add consultation fee columns to doctors table for billing
ALTER TABLE doctors
  ADD COLUMN IF NOT EXISTS op_consultation_fee NUMERIC(10,2) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS ip_primary_consultation_fee NUMERIC(10,2) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS ip_secondary_consultation_fee NUMERIC(10,2) DEFAULT NULL;

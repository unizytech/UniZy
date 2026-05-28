-- Add admin fee columns to hospitals table for billing
ALTER TABLE hospitals
  ADD COLUMN IF NOT EXISTS op_registration_fee NUMERIC(10,2) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS ip_admission_fee NUMERIC(10,2) DEFAULT NULL;

-- Add product_code column to doctor_medicines and hospital_medicine_lists
-- Used by Raster New OP formatter for the productCode field in medications payload

ALTER TABLE doctor_medicines
    ADD COLUMN IF NOT EXISTS product_code TEXT;

ALTER TABLE hospital_medicine_lists
    ADD COLUMN IF NOT EXISTS product_code TEXT;

COMMENT ON COLUMN doctor_medicines.product_code IS 'Product code from EHR system (e.g., Raster productCode). Populated from CSV upload.';
COMMENT ON COLUMN hospital_medicine_lists.product_code IS 'Product code from EHR system (e.g., Raster productCode). Populated from CSV upload.';

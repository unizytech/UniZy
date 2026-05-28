-- Add quantity column to hospital_medicine_lists table
ALTER TABLE hospital_medicine_lists
ADD COLUMN quantity INTEGER;

-- Add a comment for documentation
COMMENT ON COLUMN hospital_medicine_lists.quantity IS 'Available quantity/stock of the medicine';

-- Populate existing rows with random dummy quantity data (between 10 and 500)
UPDATE hospital_medicine_lists
SET quantity = floor(random() * 491 + 10)::INTEGER
WHERE quantity IS NULL;

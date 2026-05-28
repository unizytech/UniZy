-- Create procedure fee master for billing
CREATE TABLE procedure_fee_master (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id UUID NOT NULL,
  procedure_name VARCHAR(255) NOT NULL,
  cpt_code VARCHAR(20),
  icd_pcs_code VARCHAR(20),
  fee NUMERIC(10,2) NOT NULL,
  category VARCHAR(50) DEFAULT 'minor',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(hospital_id, procedure_name)
);

CREATE INDEX idx_procedure_fee_master_hospital ON procedure_fee_master(hospital_id);
CREATE INDEX idx_procedure_fee_master_cpt ON procedure_fee_master(cpt_code) WHERE cpt_code IS NOT NULL;

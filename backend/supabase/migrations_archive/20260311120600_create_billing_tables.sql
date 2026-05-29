-- Create bills and bill_line_items tables for automated billing
CREATE TABLE bills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
  hospital_id UUID NOT NULL,
  patient_id UUID,
  doctor_id UUID,
  bill_type VARCHAR(20) NOT NULL DEFAULT 'OP',
  bill_status VARCHAR(20) NOT NULL DEFAULT 'draft',
  consultation_type_code VARCHAR(50),
  is_merged_bill BOOLEAN DEFAULT FALSE,
  superseded_by_bill_id UUID REFERENCES bills(id),
  total_amount NUMERIC(12,2) DEFAULT 0,
  auto_billed_amount NUMERIC(12,2) DEFAULT 0,
  pending_review_amount NUMERIC(12,2) DEFAULT 0,
  flagged_amount NUMERIC(12,2) DEFAULT 0,
  generation_metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bills_extraction ON bills(extraction_id);
CREATE INDEX idx_bills_patient ON bills(patient_id);
CREATE INDEX idx_bills_hospital ON bills(hospital_id);
CREATE INDEX idx_bills_status ON bills(bill_status);

CREATE TABLE bill_line_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bill_id UUID NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
  category VARCHAR(50) NOT NULL,
  description TEXT NOT NULL,
  item_code VARCHAR(50),
  quantity NUMERIC(10,2) DEFAULT 1,
  unit_price NUMERIC(10,2),
  total_price NUMERIC(12,2),
  confidence VARCHAR(20) DEFAULT 'medium',
  billing_action VARCHAR(30) DEFAULT 'pending_review',
  source_segment VARCHAR(50),
  source_item_index INTEGER,
  matched_master_id UUID,
  matched_master_table VARCHAR(50),
  match_confidence NUMERIC(4,2),
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bill_line_items_bill ON bill_line_items(bill_id);
CREATE INDEX idx_bill_line_items_category ON bill_line_items(category);

-- Create room rate master for IP billing
CREATE TABLE room_rate_master (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id UUID NOT NULL,
  room_category VARCHAR(100) NOT NULL,
  room_sub_category VARCHAR(100),
  rate_per_day NUMERIC(10,2) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_room_rate_master_unique ON room_rate_master(hospital_id, room_category, COALESCE(room_sub_category, ''));
CREATE INDEX idx_room_rate_master_hospital ON room_rate_master(hospital_id);

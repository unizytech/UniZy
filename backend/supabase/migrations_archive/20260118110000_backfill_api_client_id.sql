-- Backfill api_client_id in llm_usage_log and recording_sessions tables
-- Links records via doctor_id -> doctors.hospital_id -> api_clients.hospital_id

-- Step 1: Backfill llm_usage_log
-- Only update where there's exactly one api_client for the hospital
UPDATE llm_usage_log lul
SET api_client_id = ac.id
FROM doctors d
JOIN api_clients ac ON ac.hospital_id = d.hospital_id AND ac.is_active = true
WHERE lul.doctor_id = d.id
  AND lul.api_client_id IS NULL
  AND NOT EXISTS (
    -- Ensure only one active api_client per hospital to avoid ambiguity
    SELECT 1 FROM api_clients ac2 
    WHERE ac2.hospital_id = d.hospital_id 
      AND ac2.is_active = true 
      AND ac2.id != ac.id
  );

-- Step 2: Backfill recording_sessions
UPDATE recording_sessions rs
SET api_client_id = ac.id
FROM doctors d
JOIN api_clients ac ON ac.hospital_id = d.hospital_id AND ac.is_active = true
WHERE rs.doctor_id = d.id
  AND rs.api_client_id IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM api_clients ac2 
    WHERE ac2.hospital_id = d.hospital_id 
      AND ac2.is_active = true 
      AND ac2.id != ac.id
  );

-- Log the backfill results (will show in migration output)
DO $$
DECLARE
  v_llm_count INTEGER;
  v_session_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_llm_count 
  FROM llm_usage_log WHERE api_client_id IS NOT NULL;
  
  SELECT COUNT(*) INTO v_session_count 
  FROM recording_sessions WHERE api_client_id IS NOT NULL;
  
  RAISE NOTICE 'Backfill complete: % llm_usage_log records, % recording_sessions now have api_client_id', 
    v_llm_count, v_session_count;
END $$;

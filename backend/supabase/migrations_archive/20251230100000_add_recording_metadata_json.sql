-- Add recording_metadata_json column to recording_sessions table
-- This stores metadata passed during /start API (patient info, doctor info, custom fields)
ALTER TABLE recording_sessions
ADD COLUMN recording_metadata_json JSONB DEFAULT '{}';

-- Add recording_metadata_json column to medical_extractions table
-- This copies the metadata for easy retrieval via /status API
ALTER TABLE medical_extractions
ADD COLUMN recording_metadata_json JSONB DEFAULT '{}';

-- Add comments for documentation
COMMENT ON COLUMN recording_sessions.recording_metadata_json IS 'Metadata passed during recording start (patient info, doctor info, custom fields)';
COMMENT ON COLUMN medical_extractions.recording_metadata_json IS 'Copy of recording metadata for easy retrieval via status API';

-- Create index for potential filtering by metadata
CREATE INDEX idx_recording_sessions_metadata ON recording_sessions USING GIN (recording_metadata_json);
CREATE INDEX idx_medical_extractions_metadata ON medical_extractions USING GIN (recording_metadata_json);

-- Add ip_id and op_id columns to patients table
-- These are optional identifiers for inpatient and outpatient visits
ALTER TABLE patients
ADD COLUMN ip_id VARCHAR(255),
ADD COLUMN op_id VARCHAR(255);

-- Add comments for documentation
COMMENT ON COLUMN patients.ip_id IS 'Inpatient visit/admission ID (optional, from EHR)';
COMMENT ON COLUMN patients.op_id IS 'Outpatient visit ID (optional, from EHR)';

-- Create indexes for lookup by ip_id and op_id
CREATE INDEX idx_patients_ip_id ON patients(ip_id) WHERE ip_id IS NOT NULL;
CREATE INDEX idx_patients_op_id ON patients(op_id) WHERE op_id IS NOT NULL;

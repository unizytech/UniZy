-- Add columns for processed (silence-removed) audio
ALTER TABLE recording_sessions
ADD COLUMN IF NOT EXISTS processed_audio_data TEXT,
ADD COLUMN IF NOT EXISTS has_processed_audio BOOLEAN DEFAULT FALSE;

-- Update the RPC to accept and store processed audio
CREATE OR REPLACE FUNCTION cleanup_chunks_after_processing(
    p_session_id UUID,
    p_full_audio_data TEXT,
    p_full_audio_mime_type TEXT,
    p_full_audio_size_bytes BIGINT,
    p_processed_audio_data TEXT DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM audio_chunks WHERE session_id = p_session_id;

    UPDATE recording_sessions
    SET full_audio_data = p_full_audio_data,
        full_audio_mime_type = p_full_audio_mime_type,
        full_audio_size_bytes = p_full_audio_size_bytes,
        processed_audio_data = p_processed_audio_data,
        has_processed_audio = (p_processed_audio_data IS NOT NULL)
    WHERE id = p_session_id;
END;
$$;

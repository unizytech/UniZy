-- ============================================================================
-- Migration: Add realtime_extraction_responses to Supabase Realtime publication
-- ============================================================================
-- The table was created but not added to the supabase_realtime publication.
-- Without this, INSERT events are not broadcast to WebSocket subscribers.
-- ============================================================================

-- Add table to Supabase Realtime publication
ALTER PUBLICATION supabase_realtime ADD TABLE realtime_extraction_responses;

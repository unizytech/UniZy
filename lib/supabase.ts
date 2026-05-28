/**
 * Supabase Client Configuration for Frontend
 *
 * This client is used for Realtime subscriptions to receive
 * processing progress updates via WebSocket (no polling!).
 *
 * Environment Variables Required (in .env or .env.local):
 * - NEXT_PUBLIC_SUPABASE_URL: Your Supabase project URL
 * - NEXT_PUBLIC_SUPABASE_ANON_KEY: Your Supabase anon/public key
 *
 * Next.js automatically loads from .env, .env.local, etc.
 * Variables with NEXT_PUBLIC_ prefix are exposed to the browser.
 *
 * IMPORTANT: Use the anon key for frontend (NOT the service_role key!)
 */

import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    "[Supabase] Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY. " +
      "Realtime subscriptions will not work. Add these to your .env file."
  );
}

// Create the client (may be null if env vars are missing)
export const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
          flowType: 'pkce',
          storage: typeof window !== 'undefined' ? window.localStorage : undefined,
        },
        realtime: {
          params: {
            eventsPerSecond: 10,
          },
          timeout: 30000, // Increase timeout to 30 seconds (default is 10s)
        },
      })
    : null;

/**
 * Check if Supabase Realtime is available
 */
export function isRealtimeAvailable(): boolean {
  return supabase !== null;
}

/**
 * Processing progress data structure from progress_json column
 */
export interface ProcessingProgress {
  status: string;
  progress: number;
  message: string;
  updated_at: string;
  transcript?: string;
  insights?: Record<string, unknown>;
  extraction_id?: string;  // UUID for fetching emotion segments
  audio_quality?: {
    overall_quality: 'good' | 'fair' | 'poor' | 'unknown';
    is_acceptable: boolean;
    issues: Array<{
      type: string;
      severity: 'warning' | 'critical';
      message: string;
    }>;
    metrics: {
      snr_db: number | null;
      rms_db: number | null;
      peak_db: number | null;
      clipping_ratio: number | null;
      silence_ratio: number | null;
      speech_detected: boolean | null;
      duration_seconds: number | null;
    };
    summary_message: string;
  };
  metrics?: {
    stitching_time?: number;
    transcription_time?: number;
    extraction_time?: number;
    total_processing_time?: number;
  };
  error?: string;
  error_details?: Record<string, unknown>;
}

/**
 * Processing job row from processing_jobs table
 */
export interface ProcessingJobRow {
  submission_id: string;
  session_id: string;
  status: string;
  progress_percentage: number;
  progress_message: string | null;
  progress_json: string | null; // JSON string that needs to be parsed
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  error_message: string | null;
}

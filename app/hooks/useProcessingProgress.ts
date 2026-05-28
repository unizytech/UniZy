/**
 * React Hook for Processing Progress via Supabase Realtime
 *
 * Replaces SSE polling with WebSocket subscriptions for real-time
 * processing progress updates.
 *
 * Benefits:
 * - Eliminates polling (~80% reduction in database requests)
 * - Lower latency for progress updates
 * - More scalable (WebSocket vs HTTP polling)
 *
 * Usage:
 * ```tsx
 * const { progress, isConnected, error } = useProcessingProgress(submissionId);
 *
 * if (progress?.status === 'COMPLETED') {
 *   console.log('Done!', progress.transcript, progress.insights);
 * }
 * ```
 */

import { useEffect, useState, useCallback, useRef } from "react";
import {
  supabase,
  isRealtimeAvailable,
  ProcessingProgress,
  ProcessingJobRow,
} from "@lib/supabase";
import type { RealtimeChannel, RealtimePostgresChangesPayload } from "@supabase/supabase-js";

interface UseProcessingProgressOptions {
  /** Auto-unsubscribe when status is COMPLETED or ERROR */
  autoUnsubscribe?: boolean;
  /** Callback when progress updates */
  onProgress?: (progress: ProcessingProgress) => void;
  /** Callback when completed */
  onComplete?: (progress: ProcessingProgress) => void;
  /** Callback when error occurs */
  onError?: (error: string, details?: Record<string, unknown>) => void;
}

interface UseProcessingProgressResult {
  /** Current processing progress */
  progress: ProcessingProgress | null;
  /** Whether the WebSocket is connected */
  isConnected: boolean;
  /** Error message if subscription failed */
  error: string | null;
  /** Whether Realtime is available (env vars configured) */
  isRealtimeAvailable: boolean;
  /** Manually unsubscribe */
  unsubscribe: () => void;
}

export function useProcessingProgress(
  submissionId: string | null,
  options: UseProcessingProgressOptions = {}
): UseProcessingProgressResult {
  const {
    autoUnsubscribe = true,
    onProgress,
    onComplete,
    onError,
  } = options;

  const [progress, setProgress] = useState<ProcessingProgress | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const channelRef = useRef<RealtimeChannel | null>(null);
  const hasUnsubscribedRef = useRef(false);

  const unsubscribe = useCallback(() => {
    if (channelRef.current && !hasUnsubscribedRef.current) {
      hasUnsubscribedRef.current = true;
      channelRef.current.unsubscribe();
      channelRef.current = null;
      setIsConnected(false);
      console.log("[Realtime] Unsubscribed from processing_jobs");
    }
  }, []);

  useEffect(() => {
    // Reset state when submissionId changes
    if (!submissionId) {
      setProgress(null);
      setError(null);
      setIsConnected(false);
      return;
    }

    // Check if Realtime is available
    if (!isRealtimeAvailable() || !supabase) {
      setError("Supabase Realtime not configured. Check environment variables.");
      return;
    }

    hasUnsubscribedRef.current = false;

    // Create a channel for this submission
    const channelName = `processing_jobs:submission_id=eq.${submissionId}`;
    const channel = supabase
      .channel(channelName)
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "processing_jobs",
          filter: `submission_id=eq.${submissionId}`,
        },
        (payload: RealtimePostgresChangesPayload<ProcessingJobRow>) => {
          const row = payload.new as ProcessingJobRow;

          // Parse progress_json if available
          let progressData: ProcessingProgress;
          if (row.progress_json) {
            try {
              progressData = JSON.parse(row.progress_json);
            } catch {
              // Fallback to legacy columns
              progressData = {
                status: row.status,
                progress: row.progress_percentage,
                message: row.progress_message || `Processing: ${row.status}`,
                updated_at: row.updated_at,
              };
            }
          } else {
            // Fallback to legacy columns
            progressData = {
              status: row.status,
              progress: row.progress_percentage,
              message: row.progress_message || `Processing: ${row.status}`,
              updated_at: row.updated_at,
            };
          }

          setProgress(progressData);

          // Call callbacks
          onProgress?.(progressData);

          if (progressData.status === "COMPLETED") {
            onComplete?.(progressData);
            if (autoUnsubscribe) {
              unsubscribe();
            }
          } else if (progressData.status === "ERROR") {
            onError?.(
              progressData.error || "Unknown error",
              progressData.error_details
            );
            if (autoUnsubscribe) {
              unsubscribe();
            }
          }
        }
      )
      .subscribe((status: string) => {
        if (status === "SUBSCRIBED") {
          setIsConnected(true);
          setError(null);
          console.log("[Realtime] Subscribed to processing_jobs updates");
        } else if (status === "CHANNEL_ERROR") {
          setError("Failed to connect to Realtime channel");
          setIsConnected(false);
        } else if (status === "TIMED_OUT") {
          setError("Realtime connection timed out");
          setIsConnected(false);
        }
      });

    channelRef.current = channel;

    // Cleanup on unmount or submissionId change
    return () => {
      unsubscribe();
    };
  }, [submissionId, autoUnsubscribe, onProgress, onComplete, onError, unsubscribe]);

  return {
    progress,
    isConnected,
    error,
    isRealtimeAvailable: isRealtimeAvailable(),
    unsubscribe,
  };
}

/**
 * Fetch initial job status from database
 * Use this to get current status before subscribing to updates
 */
export async function fetchJobStatus(
  submissionId: string
): Promise<ProcessingProgress | null> {
  if (!supabase) {
    console.warn("[Realtime] Supabase not configured");
    return null;
  }

  try {
    const { data, error } = await supabase
      .from("processing_jobs")
      .select("*")
      .eq("submission_id", submissionId)
      .single();

    if (error) {
      console.error("[Realtime] Failed to fetch job status:", error);
      return null;
    }

    const row = data as ProcessingJobRow;

    // Parse progress_json if available
    if (row.progress_json) {
      try {
        return JSON.parse(row.progress_json);
      } catch {
        // Fallback to legacy columns
      }
    }

    return {
      status: row.status,
      progress: row.progress_percentage,
      message: row.progress_message || `Processing: ${row.status}`,
      updated_at: row.updated_at,
    };
  } catch (err) {
    console.error("[Realtime] Error fetching job status:", err);
    return null;
  }
}

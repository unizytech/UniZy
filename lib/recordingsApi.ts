/**
 * API Client for Recording Management
 *
 * Provides functions to interact with /api/v1/recordings/* endpoints
 * for listing and reprocessing recordings.
 */

import { authGet, authPost, AuthOptions } from './apiClient';

// Re-export AuthOptions for consumers
export type { AuthOptions };

const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

// ============================================================================
// Types
// ============================================================================

export interface RecordingInfo {
  session_id: string;
  correlation_id: string | null;
  student_id: string | null;
  student_identifier: string | null;
  patient_name: string | null;
  consultation_datetime: string;
  completed_at: string | null;
  template_code: string | null;
  template_name: string | null;
  processing_mode: string | null;
  extraction_mode: string | null;
  transcription_model: string | null;
  extraction_model: string | null;
  has_audio: boolean;
  has_transcript: boolean;
  has_extraction: boolean;
  has_processed_audio: boolean;
  last_extraction_id: string | null;
  last_submission_id: string | null;  // For audio playback API
  status: string;
  error_message: string | null;
  audio_quality: { overall_quality: string; summary_message: string } | null;
  chunk_count: number;  // Number of audio chunks (for abandoned RECORDING status)
  last_chunk_at: string | null;  // Timestamp of last chunk (to verify truly abandoned)
  is_merged: boolean;  // True for display-only merged extraction rows
}

export interface RecordingsListResponse {
  recordings: RecordingInfo[];
  total_count: number;
}

export interface ListRecordingsParams {
  student_id?: string;
  student_identifier?: string;
  status?: string;
  date_from?: string;  // ISO date string
  date_to?: string;    // ISO date string
  limit?: number;
  offset?: number;
}

export interface ReprocessRequest {
  mode: 'new_extraction' | 'reprocess_transcript';
  template_code: string;
  processing_mode: string;
  extraction_mode: 'core' | 'additional' | 'full';
}

export interface ReprocessResponse {
  submission_id: string;
  mode_used: 'new_extraction' | 'reprocess_transcript';
  fallback_used: boolean;
  message: string;
}

export interface AudioDataResponse {
  submission_id: string;
  session_id: string;
  audio_data: string;  // Base64 encoded audio
  mime_type: string;
  size_bytes: number;
  duration_seconds: number | null;
  transcript: string | null;  // Transcript text if available
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Handle API errors consistently
 */
export function handleApiError(error: any): string {
  if (error.response?.data?.detail) {
    return error.response.data.detail;
  }
  if (error.message) {
    return error.message;
  }
  return 'An unknown error occurred';
}

/**
 * List recordings for a counsellor
 *
 * @param doctorId - UUID of the counsellor
 * @param params - Optional filter parameters
 * @param auth - Authentication options
 * @returns List of recordings with metadata
 */
export async function listCounsellorRecordings(
  doctorId: string,
  params?: ListRecordingsParams,
  auth?: string | AuthOptions | null
): Promise<RecordingsListResponse> {
  // Build query string
  const queryParams = new URLSearchParams();
  if (params?.student_id) queryParams.set('student_id', params.student_id);
  if (params?.student_identifier) queryParams.set('student_identifier', params.student_identifier);
  if (params?.status) queryParams.set('status', params.status);
  if (params?.date_from) queryParams.set('date_from', params.date_from);
  if (params?.date_to) queryParams.set('date_to', params.date_to);
  if (params?.limit) queryParams.set('limit', params.limit.toString());
  if (params?.offset) queryParams.set('offset', params.offset.toString());

  const queryString = queryParams.toString();
  const url = `/api/v1/recordings/counsellor/${encodeURIComponent(doctorId)}${queryString ? `?${queryString}` : ''}`;

  const response = await authGet(url, auth ?? null);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch recordings: ${response.statusText}`);
  }

  return response.json();
}

/**
 * List recordings for an assistant
 */
export async function listAssistantRecordings(
  nurseId: string,
  params?: ListRecordingsParams,
  auth?: string | AuthOptions | null
): Promise<RecordingsListResponse> {
  const queryParams = new URLSearchParams();
  if (params?.student_id) queryParams.set('student_id', params.student_id);
  if (params?.student_identifier) queryParams.set('student_identifier', params.student_identifier);
  if (params?.status) queryParams.set('status', params.status);
  if (params?.date_from) queryParams.set('date_from', params.date_from);
  if (params?.date_to) queryParams.set('date_to', params.date_to);
  if (params?.limit) queryParams.set('limit', params.limit.toString());
  if (params?.offset) queryParams.set('offset', params.offset.toString());

  const queryString = queryParams.toString();
  const url = `/api/v1/recordings/assistant/${encodeURIComponent(nurseId)}${queryString ? `?${queryString}` : ''}`;

  const response = await authGet(url, auth ?? null);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch assistant recordings: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Reprocess a recording with new template/settings
 *
 * @param sessionId - UUID of the recording session to reprocess
 * @param request - Reprocess configuration
 * @param auth - Authentication options
 * @returns Submission ID for tracking progress
 */
export async function reprocessRecording(
  sessionId: string,
  request: ReprocessRequest,
  auth?: string | AuthOptions | null
): Promise<ReprocessResponse> {
  const url = `/api/v1/recordings/${encodeURIComponent(sessionId)}/reprocess`;

  const response = await authPost(url, auth ?? null, request);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to reprocess recording: ${response.statusText}`);
  }

  return response.json();
}

export interface ExtractionViewerData {
  extraction_id: string;
  session_id: string | null;
  is_merged: boolean;
  transcript_text: string | null;
  ehr_payload: Record<string, unknown> | null;
  edited_extraction: Record<string, unknown> | null;
  original_extraction: Record<string, unknown> | null;
  edit_count: number;
  last_edited_at: string | null;
  last_edited_by: string | null;
  edited_by_type: string | null;
  form_type: string | null;
}

/**
 * Fetch transcript + extraction (original/edited) + EHR payload for the viewer modal.
 * Reuses the existing /ehr-payload endpoint extended with transcript_text.
 */
export async function getExtractionViewerData(
  extractionId: string,
  auth?: string | AuthOptions | null
): Promise<ExtractionViewerData> {
  const url = `/api/v1/extractions/${encodeURIComponent(extractionId)}/ehr-payload`;
  const response = await authGet(url, auth ?? null);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch extraction: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get audio data for a recording by submission ID
 *
 * @param submissionId - UUID of the submission (from processing_jobs)
 * @param auth - Authentication options
 * @returns Audio data with base64 encoded content and mime type
 */
export async function getRecordingAudio(
  submissionId: string,
  auth?: string | AuthOptions | null,
  audioType: 'original' | 'processed' = 'original'
): Promise<AudioDataResponse> {
  const typeParam = audioType === 'processed' ? '?audio_type=processed' : '';
  const url = `/api/v1/recordings/audio/${encodeURIComponent(submissionId)}${typeParam}`;

  const response = await authGet(url, auth ?? null);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch audio: ${response.statusText}`);
  }

  return response.json();
}

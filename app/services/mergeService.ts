/**
 * Merge Service - API Client for Extraction Merge Feature
 *
 * Provides functions to interact with the extraction merge API endpoints.
 */

import { authGet, authPost } from '@lib/apiClient';

// =====================================================
// Type Definitions
// =====================================================

/**
 * Upload type determines the merge strategy for uploaded JSON.
 *
 * DEEP_MERGE types: Data is contextually merged, latest/most complete value wins for conflicts
 * APPEND types: Arrays are concatenated, never replaced
 */
export type UploadType =
  // DEEP_MERGE strategy
  | 'OP_SUMMARY'
  | 'DISCHARGE_SUMMARY'
  | 'EXAMINATION'
  | 'OPTOMETRY'
  | 'OTHER'
  // APPEND strategy
  | 'INVESTIGATION'
  | 'PRESCRIPTION'
  | 'NOTES';

/**
 * Uploaded JSON data to be merged.
 *
 * The merge strategy (DEEP_MERGE vs APPEND) is determined by the upload_type:
 * - DEEP_MERGE: OP_SUMMARY, DISCHARGE_SUMMARY, EXAMINATION, OPTOMETRY, OTHER
 * - APPEND: INVESTIGATION, PRESCRIPTION, NOTES
 *
 * The backend will automatically detect the source schema format and transform
 * it to match the target consultation type schema if needed.
 *
 * Supported schema transformations:
 * - OPHTHAL_OCR → OPHTHAL_FULL (ophthalmology records)
 */
export interface UploadedJsonSource {
  /** JSON data to merge */
  data: Record<string, any>;
  /** Type of upload - determines merge strategy (DEEP_MERGE vs APPEND) */
  upload_type: UploadType;
  /** Display name for the uploaded source (e.g., 'External Lab Report') */
  source_name?: string;
  /** Date of the source data (ISO format) for chronological ordering */
  source_date?: string;
  /** Optional consultation type code for field mapping */
  consultation_type_code?: string;
}

/**
 * Schema transformation metadata returned from merge operations.
 * Indicates whether uploaded JSON was transformed to match target schema.
 */
export interface SchemaTransformation {
  /** Whether transformation was applied */
  applied: boolean;
  /** Detected source schema type (e.g., 'OPHTHAL_OCR', 'OPHTHAL_FULL') */
  source_schema?: string;
  /** Target schema type */
  target_schema?: string;
  /** Number of fields in original data */
  original_field_count?: number;
  /** Number of fields after transformation */
  transformed_field_count?: number;
}

export interface MergeRequest {
  /** Option 1: Direct extraction IDs (recommended) */
  source_extraction_ids?: string[];
  /** Option 2: Submission IDs (auto-resolved to extraction IDs) */
  source_submission_ids?: string[];
  /** Target template code (e.g., "OP_GENERAL", "OP_SMITH_1225141530") */
  target_template_code: string;
  doctor_id: string;
  merge_notes?: string;
  /** Optional JSON sources to merge (up to 4 total sources) */
  uploaded_json_sources?: UploadedJsonSource[];
  /** Required for JSON-only merges (external patient ID like "PAT-12345") */
  patient_id?: string;
}

export interface MergePreviewRequest {
  /** Option 1: Direct extraction IDs (recommended) */
  source_extraction_ids?: string[];
  /** Option 2: Submission IDs (auto-resolved to extraction IDs) */
  source_submission_ids?: string[];
  /** Target template code (e.g., "OP_GENERAL", "OP_SMITH_1225141530") */
  target_template_code: string;
  doctor_id: string;
  /** Optional JSON sources to merge (up to 4 total sources) */
  uploaded_json_sources?: UploadedJsonSource[];
  /** Required for JSON-only merges (external patient ID like "PAT-12345") */
  patient_id?: string;
}

export interface MergeMetadata {
  source_count: number;
  /** Target template code used for merge */
  target_template_code: string;
  merge_timestamp: string;
  doctor_confirmed: boolean;
  merge_notes?: string;
  conflict_count: number;
  conflicts_resolved: string[];
  cross_type_scenario: string;
  consultation_types_merged: string[];
  /** Schema transformation metadata if uploaded JSON was transformed */
  schema_transformation?: SchemaTransformation;
  /** Whether uploaded JSON sources were included in merge */
  has_uploaded_json?: boolean;
  /** Source names of uploaded JSON files */
  uploaded_json_source_names?: string[];
}

export interface MergeResponse {
  success: boolean;
  extraction_id?: string;
  merged_data: Record<string, any>;
  merge_metadata: MergeMetadata;
  preview: boolean;
}

/**
 * Async merge response - returned immediately from /merge endpoint
 */
export interface MergeAsyncResponse {
  success: boolean;
  extraction_id: string;
  status: 'processing' | 'completed' | 'failed';
  message: string;
}

/**
 * Merge status response - returned from /merge/status/{extraction_id}
 */
export interface MergeStatusResponse {
  extraction_id: string;
  status: 'processing' | 'completed' | 'failed';
  progress?: string;
  merged_data?: Record<string, any>;
  merge_metadata?: MergeMetadata;
  error?: string;
  created_at?: string;
  completed_at?: string;
}

export interface PatientTimelineExtraction {
  extraction_id: string;
  consultation_type_code: string;
  consultation_type_name: string;
  created_at: string;
  doctor_name?: string;
  is_merged: boolean;
  source_count: number;
  segment_count: number;
}

export interface PatientTimelineResponse {
  patient_id: string;
  extractions: PatientTimelineExtraction[];
  total_count: number;
}

export interface SourceExtractionInfo {
  source_extraction_id: string;
  consultation_type_code: string;
  consultation_type_name: string;
  created_at: string;
  doctor_name?: string;
  merge_order: number;
  merge_strategy: string;
}

export interface MergeLineageResponse {
  merged_extraction_id: string;
  is_merged: boolean;
  source_extractions: SourceExtractionInfo[];
  merge_metadata: MergeMetadata;
}

// =====================================================
// API Functions
// =====================================================

/**
 * Get merge status by extraction_id
 */
export async function getMergeStatus(
  extractionId: string,
  accessToken?: string | null
): Promise<MergeStatusResponse> {
  const response = await authGet(
    `/api/v1/extractions/merge/status/${extractionId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get merge status');
  }

  return response.json();
}

/**
 * Merge multiple extractions into a single consolidated output.
 *
 * This function is async - it starts the merge and polls until completion.
 * The backend returns immediately with an extraction_id, then processes in background.
 *
 * @param request - Merge request parameters
 * @param accessToken - Optional access token for authentication
 * @param pollIntervalMs - Poll interval in milliseconds (default: 2000)
 * @param maxWaitMs - Maximum wait time in milliseconds (default: 120000 = 2 minutes)
 * @param onProgress - Optional callback for progress updates
 */
export async function mergeExtractions(
  request: MergeRequest,
  accessToken?: string | null,
  pollIntervalMs: number = 2000,
  maxWaitMs: number = 120000,
  onProgress?: (status: MergeStatusResponse) => void
): Promise<MergeResponse> {
  // Step 1: Start the merge (returns immediately with extraction_id)
  const response = await authPost(
    `/api/v1/extractions/merge`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start merge');
  }

  const asyncResponse: MergeAsyncResponse = await response.json();
  const { extraction_id } = asyncResponse;

  // Step 2: Poll for completion
  const startTime = Date.now();

  while (true) {
    // Check timeout
    if (Date.now() - startTime > maxWaitMs) {
      throw new Error(`Merge timed out after ${maxWaitMs / 1000} seconds. Extraction ID: ${extraction_id}`);
    }

    // Wait before polling
    await new Promise(resolve => setTimeout(resolve, pollIntervalMs));

    // Get status (pass accessToken for polling)
    const status = await getMergeStatus(extraction_id, accessToken);

    // Call progress callback if provided
    if (onProgress) {
      onProgress(status);
    }

    if (status.status === 'completed') {
      // Return in MergeResponse format
      return {
        success: true,
        extraction_id: status.extraction_id,
        merged_data: status.merged_data || {},
        merge_metadata: status.merge_metadata || {
          source_count: 0,
          target_template_code: request.target_template_code,
          merge_timestamp: status.completed_at || new Date().toISOString(),
          doctor_confirmed: true,
          conflict_count: 0,
          conflicts_resolved: [],
          cross_type_scenario: 'UNKNOWN',
          consultation_types_merged: [],
        },
        preview: false,
      };
    } else if (status.status === 'failed') {
      throw new Error(status.error || 'Merge failed');
    }
    // status === 'processing' - continue polling
  }
}

/**
 * Preview merge without saving to database
 */
export async function previewMerge(
  request: MergePreviewRequest,
  accessToken?: string | null
): Promise<MergeResponse> {
  const response = await authPost(
    `/api/v1/extractions/merge/preview`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to preview merge');
  }

  return response.json();
}

/**
 * Get patient extraction timeline
 */
export async function getPatientTimeline(
  patientId: string,
  consultationTypeCode?: string,
  accessToken?: string | null
): Promise<PatientTimelineResponse> {
  let url = `/api/v1/extractions/patient/${patientId}/timeline`;
  if (consultationTypeCode) {
    url += `?consultation_type_code=${encodeURIComponent(consultationTypeCode)}`;
  }

  const response = await authGet(url, accessToken ?? null);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch patient timeline');
  }

  return response.json();
}

/**
 * Get merge lineage information for a merged extraction
 */
export async function getMergeInfo(
  extractionId: string,
  accessToken?: string | null
): Promise<MergeLineageResponse> {
  const response = await authGet(
    `/api/v1/extractions/${extractionId}/merge-info`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch merge info');
  }

  return response.json();
}

/**
 * Health check for merge service
 */
export async function checkMergeHealth(accessToken?: string | null): Promise<any> {
  const response = await authGet(
    `/api/v1/extractions/merge/health`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error('Merge service health check failed');
  }

  return response.json();
}

// =====================================================
// Schema Transformation Functions
// =====================================================

export interface TransformSchemaRequest {
  /** JSON data to transform */
  data: Record<string, any>;
  /** Target schema type (e.g., 'OPHTHAL_FULL') */
  target_schema: string;
}

export interface TransformSchemaResponse {
  success: boolean;
  /** Transformed data in target schema format */
  transformed_data?: Record<string, any>;
  /** Original data (preserved for reference) */
  original_data?: Record<string, any>;
  /** Detected source schema type */
  source_schema_detected?: string;
  /** Whether transformation was actually applied */
  transformation_applied: boolean;
  /** Error message if transformation failed */
  error?: string;
  /** Metadata about the transformation */
  metadata?: {
    original_field_count: number;
    transformed_field_count: number;
    unmapped_fields?: string[];
  };
}

/**
 * Transform JSON data from one schema format to another.
 *
 * This is useful for previewing how uploaded JSON will be transformed
 * before performing a merge operation.
 *
 * Supported transformations:
 * - OPHTHAL_OCR → OPHTHAL_FULL (ophthalmology records)
 *
 * @param request - The transformation request
 * @param accessToken - Optional access token for authentication
 * @returns TransformSchemaResponse with transformed data or error
 */
export async function transformSchema(
  request: TransformSchemaRequest,
  accessToken?: string | null
): Promise<TransformSchemaResponse> {
  const response = await authPost(
    `/api/v1/extractions/transform-schema`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to transform schema');
  }

  return response.json();
}

/**
 * Detect the schema type of JSON data.
 *
 * @param data - JSON data to analyze
 * @param accessToken - Optional access token for authentication
 * @returns The detected schema type (e.g., 'OPHTHAL_OCR', 'OPHTHAL_FULL', 'UNKNOWN')
 */
export async function detectSchemaType(
  data: Record<string, any>,
  accessToken?: string | null
): Promise<{ schema_type: string; confidence: number }> {
  const response = await authPost(
    `/api/v1/extractions/detect-schema`,
    accessToken ?? null,
    { data }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to detect schema type');
  }

  return response.json();
}

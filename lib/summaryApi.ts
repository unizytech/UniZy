/**
 * API Client for Multi-Consultation Type Summary Extraction
 *
 * Provides functions to interact with /api/v1/summary/* endpoints
 * for OP, DISCHARGE, RESPIRATORY, and future consultation types.
 */

import {
  ConsultationType,
  ConsultationTypesResponse,
  ConsultationTypeResponse,
  ConsultationTypeCode,
  ExtractionRequest,
  MedicalExtractionResponse,
  SegmentListResponse,
  TemplateListResponse,
  ExtractionMode,
  ValidationResult,
  ActivatedTemplate,
  ProcessingMode,
  BrevityLevel,
  TerminologyStyle,
  MergeTargetTemplate,
  DoctorTemplatesResponse,
} from './types';
import { authGet, authPost, authPut, authDelete, createAuthHeaders, AuthOptions } from './apiClient';

// Re-export AuthOptions for consumers
export type { AuthOptions };

const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

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

// ============================================================================
// Consultation Type Management
// ============================================================================

/**
 * Get all available consultation types
 */
export async function getConsultationTypes(
  auth?: string | AuthOptions | null
): Promise<ConsultationTypesResponse> {
  const response = await authGet(`/api/v1/summary/consultation-types`, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch consultation types: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get details for a specific consultation type
 */
export async function getConsultationType(
  typeCode: ConsultationTypeCode,
  auth?: string | AuthOptions | null
): Promise<ConsultationTypeResponse> {
  const response = await authGet(`/api/v1/summary/consultation-types/${encodeURIComponent(typeCode)}`, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch consultation type: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Create a new consultation type (Admin)
 */
export interface CreateConsultationTypeRequest {
  type_code: string;
  type_name: string;
  description?: string;
  specialty_applicable?: string[];
  display_order: number;
  icon_name?: string;
  color_code?: string;
  clone_from_consultation_type_id?: string;  // Clone segments from existing consultation type
  // Visibility controls (optional - if all empty/undefined, everyone can see this consultation type)
  visible_to_hospitals?: string[];  // Hospital UUIDs that can see this consultation type
  visible_to_doctors?: string[];  // Doctor UUIDs that can see this consultation type
  visible_to_specializations?: string[];  // Specializations that can see this consultation type
}

export async function createConsultationType(
  request: CreateConsultationTypeRequest,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; consultation_type: any; message: string }> {
  const response = await authPost(`/api/v1/summary/admin/consultation-types`, auth ?? null, request);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to create consultation type: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Medical Summary Extraction
// ============================================================================

/**
 * Extract medical summary for any consultation type
 */
export async function extractMedicalSummary(
  request: ExtractionRequest,
  auth?: string | AuthOptions | null
): Promise<MedicalExtractionResponse> {
  const response = await authPost(`/api/v1/summary/extract`, auth ?? null, request);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Extraction failed: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Segment Configuration Management
// ============================================================================

/**
 * Get segment definitions for a consultation type
 */
export async function getSegments(
  consultationTypeCode: ConsultationTypeCode,
  userId?: string,
  mode?: ExtractionMode,
  auth?: string | AuthOptions | null
): Promise<SegmentListResponse> {
  const params = new URLSearchParams();
  if (userId) params.append('doctor_id', userId);
  if (mode) params.append('mode', mode);

  const endpoint = `/api/v1/summary/segments/${encodeURIComponent(consultationTypeCode)}${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch segments: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Template Management
// ============================================================================

/**
 * Get available templates for a consultation type
 * @param consultationTypeCode - Consultation type code
 * @param doctorId - Optional doctor ID for visibility filtering (hospital, specialization, platform-wide)
 * @param filterType - Optional filter ('admin', 'doctor', 'all')
 * @param auth - Bearer token or API key for authentication
 */
export async function getTemplates(
  consultationTypeCode: ConsultationTypeCode,
  doctorId?: string,
  filterType?: 'admin' | 'doctor' | 'all',
  auth?: string | AuthOptions | null
): Promise<TemplateListResponse> {
  const params = new URLSearchParams();
  if (doctorId) {
    params.append('doctor_id', doctorId);
  }
  if (filterType) {
    params.append('filter_type', filterType);
  }

  const endpoint = `/api/v1/summary/templates/${encodeURIComponent(consultationTypeCode)}${params.toString() ? `?${params.toString()}` : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch templates: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get all templates across all consultation types
 * @param filterType - Optional filter ('admin', 'doctor', 'all')
 * @param doctorId - Optional doctor ID for visibility filtering
 * @param auth - Bearer token or API key for authentication
 */
export async function getAllTemplates(
  filterType?: 'admin' | 'doctor' | 'all',
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<TemplateListResponse> {
  const params = new URLSearchParams();
  if (filterType) {
    params.append('filter_type', filterType);
  }
  if (doctorId) {
    params.append('doctor_id', doctorId);
  }

  const endpoint = `/api/v1/summary/templates${params.toString() ? `?${params.toString()}` : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch all templates: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Activate a template configuration
 */
export async function activateTemplate(
  consultationTypeCode: ConsultationTypeCode,
  templateCode: string,
  userId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; template: any }> {
  const endpoint = `/api/v1/summary/templates/${encodeURIComponent(consultationTypeCode)}/activate/${encodeURIComponent(templateCode)}?doctor_id=${userId}`;
  const response = await authPost(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to activate template: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Template Admin Functions
// ============================================================================

export interface CreateTemplateData {
  template_code: string;
  template_name: string;
  description: string;
  consultation_type_code: ConsultationTypeCode;
  specialty?: string;
  use_case?: string;
  specialization?: string;
  hospital_id?: string;
  estimated_extraction_time_seconds?: number;
  is_active?: boolean; // Whether template is active (default: true)
  // New inheritance options
  inherit_from_type?: 'consultation_type' | 'template';
  inherit_from_id?: string; // consultation type code OR template code
  // Deprecated: kept for backwards compatibility
  inherit_from_consultation_type?: boolean;
}

export interface UpdateTemplateData {
  template_name?: string;
  description?: string;
  specialty?: string;
  use_case?: string;
  specialization?: string;
  estimated_extraction_time_seconds?: number;
}

export interface TemplateSegmentConfig {
  category: 'core' | 'additional' | 'excluded';
  display_order: number;
  brevity_level?: 'concise' | 'balanced' | 'detailed';
  terminology_style?: 'medical_terms' | 'simple_terms' | 'as_spoken';
}

/**
 * Create a new template (Admin)
 */
export async function createTemplate(
  data: CreateTemplateData,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; template: any; segments_configured?: number }> {
  const params = new URLSearchParams();
  if (doctorId) params.append('doctor_id', doctorId);

  const endpoint = `/api/v1/summary/admin/templates${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authPost(endpoint, auth ?? null, data);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to create template: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Template Import from Source DB (Admin)
// ============================================================================

export interface SourceTemplate {
  template_code: string;
  template_name: string;
  description?: string | null;
  is_active?: boolean | null;
  type_code?: string | null;
  type_name?: string | null;
  hospital_scoped?: boolean;
  doctor_scoped?: boolean;
}

export interface ImportTemplateResult {
  success: boolean;
  template_id: string;
  template_code: string;
  created: {
    segment_definitions: number;
    consultation_type: boolean;
    system_prompt_config: boolean;
    system_prompt_components: number;
    consultation_type_segments: number;
    template_segments: number;
    hospital_remapped: boolean;
    assembly_warnings: string[];
  };
}

/**
 * List templates available on the configured source Supabase project (Admin).
 */
export async function listSourceTemplates(
  auth?: string | AuthOptions | null
): Promise<SourceTemplate[]> {
  const response = await authGet('/api/v1/summary/admin/templates/import-source/list', auth ?? null);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to list source templates: ${response.statusText}`);
  }
  const data = await response.json();
  return data.templates as SourceTemplate[];
}

/**
 * Import a template (and its dependency graph) from the source DB into the target DB (Admin).
 */
export async function importTemplateFromSource(
  sourceTemplateCode: string,
  auth?: string | AuthOptions | null
): Promise<ImportTemplateResult> {
  const response = await authPost(
    '/api/v1/summary/admin/templates/import-from-source',
    auth ?? null,
    { source_template_code: sourceTemplateCode }
  );
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to import template: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Update template metadata (Admin)
 */
export async function updateTemplate(
  templateCode: string,
  data: UpdateTemplateData,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; template: any }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}`;
  const response = await authPut(endpoint, auth ?? null, data);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update template: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Preview assembled prompt for a template (Admin)
 */
export async function getTemplatePromptPreview(
  templateCode: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  template_code: string;
  template_name: string;
  assembled_full_prompt: string | null;
  prompt_assembled_at: string | null;
  has_prompt: boolean;
}> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/preview-prompt`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to preview template prompt: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete a template (Admin)
 */
export async function deleteTemplate(
  templateCode: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}`;
  const response = await authDelete(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to delete template: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete a segment definition (Admin)
 */
export async function deleteSegment(
  segmentId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string }> {
  const endpoint = `/api/v1/summary/admin/segments/${encodeURIComponent(segmentId)}`;
  const response = await authDelete(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to delete segment: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete a consultation type (Admin)
 */
export async function deleteConsultationType(
  consultationTypeCode: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string }> {
  const endpoint = `/api/v1/summary/admin/consultation-types/${encodeURIComponent(consultationTypeCode)}`;
  const response = await authDelete(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to delete consultation type: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// REACTIVATE FUNCTIONS (Restore soft-deleted entities)
// ============================================================================

/**
 * Reactivate a soft-deleted template (Admin)
 */
export async function reactivateTemplate(
  templateCode: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/reactivate`;
  const response = await authPost(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to reactivate template: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Reactivate a soft-deleted segment (Admin)
 */
export async function reactivateSegment(
  segmentId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string }> {
  const endpoint = `/api/v1/summary/admin/segments/${encodeURIComponent(segmentId)}/reactivate`;
  const response = await authPost(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to reactivate segment: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Reactivate a soft-deleted consultation type (Admin)
 */
export async function reactivateConsultationType(
  consultationTypeCode: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string }> {
  const endpoint = `/api/v1/summary/admin/consultation-types/${encodeURIComponent(consultationTypeCode)}/reactivate`;
  const response = await authPost(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to reactivate consultation type: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get template segment configuration (Admin)
 */
export async function getTemplateSegments(
  templateCode: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; template_code: string; template_name: string; segments: any[]; count: number }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/segments`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch template segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update a template segment configuration (Admin)
 */
export async function updateTemplateSegment(
  templateCode: string,
  segmentCode: string,
  config: TemplateSegmentConfig,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; configuration: any }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/segments/${encodeURIComponent(segmentCode)}`;
  const response = await authPut(endpoint, auth ?? null, config);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update segment: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Bulk update template segments (Admin)
 */
export async function bulkUpdateTemplateSegments(
  templateCode: string,
  segments: Array<{ segment_code: string } & TemplateSegmentConfig>,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; configurations: any[] }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/segments/bulk`;
  const response = await authPost(endpoint, auth ?? null, { segments });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to bulk update segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Inherit segment configuration from consultation type (Admin)
 */
export async function inheritTemplateConfiguration(
  templateCode: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; segments_configured: number; segments: any[] }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/inherit`;
  const response = await authPost(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to inherit configuration: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Template Field Config (Admin): gap-analysis + empty-payload trim
// Drives GET /api/v1/ehr/extraction-gaps and GET /api/v1/ehr/template-schema
// ============================================================================

export interface TemplateFieldConfigSegment {
  segment_code: string;
  segment_name: string;
  category: string;
  display_order: number;
  shape: 'flat' | 'nested_presence' | 'comorbidity' | 'array' | 'unknown';
  schema_leaves: string[];
  default_leaves: string[];
  gap_analysis_fields_json: string[] | null;
  include_in_empty_payload: boolean | null;
}

export interface TemplateFieldConfigResponse {
  success: boolean;
  template_code: string;
  template_name: string;
  segments: TemplateFieldConfigSegment[];
  count: number;
}

export interface SegmentFieldConfigUpdateBody {
  gap_analysis_fields_json?: string[] | null;
  include_in_empty_payload?: boolean | null;
}

export async function getTemplateFieldConfig(
  templateCode: string,
  auth?: string | AuthOptions | null
): Promise<TemplateFieldConfigResponse> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/field-config`;
  const response = await authGet(endpoint, auth ?? null);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch field config: ${response.statusText}`);
  }
  return response.json();
}

export async function updateSegmentFieldConfig(
  templateCode: string,
  segmentCode: string,
  body: SegmentFieldConfigUpdateBody,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; template_code: string; segment_code: string; configuration: any }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/field-config/${encodeURIComponent(segmentCode)}`;
  const response = await authPut(endpoint, auth ?? null, body);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update segment field config: ${response.statusText}`);
  }
  return response.json();
}

export async function bulkUpdateTemplateFieldConfig(
  templateCode: string,
  segments: Array<{ segment_code: string } & SegmentFieldConfigUpdateBody>,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; template_code: string; updated: any[]; update_count: number; errors: any[] }> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/field-config/bulk`;
  const response = await authPost(endpoint, auth ?? null, { segments });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to bulk update field config: ${response.statusText}`);
  }
  return response.json();
}


// ============================================================================
// Doctor Template Segment APIs (EHR-authenticated)
// These are for doctors configuring their own templates via the Doctor Config screen
// ============================================================================

/**
 * Get template segment configuration (Doctor/EHR-authenticated)
 */
export async function getDoctorTemplateSegments(
  templateCode: string,
  doctorId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; template_code: string; template_name: string; segments: any[]; count: number }> {
  const endpoint = `/api/v1/summary/doctor/templates/${encodeURIComponent(templateCode)}/segments?doctor_id=${encodeURIComponent(doctorId)}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch template segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update a template segment configuration (Doctor/EHR-authenticated)
 */
export async function updateDoctorTemplateSegment(
  templateCode: string,
  segmentCode: string,
  config: TemplateSegmentConfig,
  doctorId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; configuration: any }> {
  const endpoint = `/api/v1/summary/doctor/templates/${encodeURIComponent(templateCode)}/segments/${encodeURIComponent(segmentCode)}?doctor_id=${encodeURIComponent(doctorId)}`;
  const response = await authPut(endpoint, auth ?? null, config);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update segment: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Bulk update template segments (Doctor/EHR-authenticated)
 */
export async function bulkUpdateDoctorTemplateSegments(
  templateCode: string,
  segments: Array<{ segment_code: string } & TemplateSegmentConfig>,
  doctorId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; configurations: any[] }> {
  const endpoint = `/api/v1/summary/doctor/templates/${encodeURIComponent(templateCode)}/segments/bulk?doctor_id=${encodeURIComponent(doctorId)}`;
  const response = await authPost(endpoint, auth ?? null, { segments });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to bulk update segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Inherit segment configuration from consultation type (Doctor/EHR-authenticated)
 */
export async function inheritDoctorTemplateConfiguration(
  templateCode: string,
  doctorId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; segments_configured: number; segments: any[] }> {
  const endpoint = `/api/v1/summary/doctor/templates/${encodeURIComponent(templateCode)}/inherit?doctor_id=${encodeURIComponent(doctorId)}`;
  const response = await authPost(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to inherit configuration: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get segments available to add to a template (not yet in template but in consultation type)
 */
export interface AvailableSegment {
  segment_id: string;
  segment_code: string;
  segment_name: string;
  description?: string;
  default_category: string;
  default_display_order: number;
  default_brevity_level: string;
  default_terminology_style: string;
}

export async function getAvailableSegmentsForTemplate(
  templateCode: string,
  auth?: string | AuthOptions | null
): Promise<{
  template_code: string;
  template_name: string;
  consultation_type_code: string;
  available_segments: AvailableSegment[];
  count: number;
}> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/segments/available`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get available segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Add segments from consultation type to template
 */
export interface AddSegmentsFromTypeRequest {
  segment_codes?: string[];
  add_all_missing?: boolean;
  default_category?: string;
}

export async function addSegmentsFromType(
  templateCode: string,
  request: AddSegmentsFromTypeRequest,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  template_code: string;
  message: string;
  segments_added: Array<{ segment_code: string; segment_name: string; category: string }>;
  count: number;
}> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/segments/add-from-type`;
  const response = await authPost(endpoint, auth ?? null, request);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to add segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Assign a segment to a consultation type (creates junction table entry)
 * Also auto-syncs to all templates of that consultation type as 'excluded'
 */
export interface AssignSegmentRequest {
  segment_id?: string;  // REQUIRED when segment_code is not unique (e.g., 'HISTORY' exists in multiple consultation types)
  category?: string;
  display_order?: number;
  brevity_level?: string;
  terminology_style?: string;
}

export async function assignSegmentToConsultationType(
  consultationTypeCode: string,
  segmentCode: string,
  request?: AssignSegmentRequest,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  message: string;
  consultation_type_code: string;
  segment_code: string;
  templates_synced: number;
}> {
  const endpoint = `/api/v1/summary/admin/consultation-types/${encodeURIComponent(consultationTypeCode)}/segments/${encodeURIComponent(segmentCode)}/assign`;
  const response = await authPost(endpoint, auth ?? null, request || {});

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to assign segment: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Unassign a segment from a consultation type (removes junction table entry only)
 */
export async function unassignSegmentFromConsultationType(
  consultationTypeCode: string,
  segmentCode: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  message: string;
  segment_code: string;
  consultation_type_code: string;
}> {
  const endpoint = `/api/v1/summary/admin/consultation-types/${encodeURIComponent(consultationTypeCode)}/segments/${encodeURIComponent(segmentCode)}/unassign`;
  const response = await authDelete(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to unassign segment: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Unassign a segment from a template (removes junction table entry only)
 */
export async function unassignSegmentFromTemplate(
  templateCode: string,
  segmentCode: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  message: string;
  segment_code: string;
  template_code: string;
}> {
  const endpoint = `/api/v1/summary/admin/templates/${encodeURIComponent(templateCode)}/segments/${encodeURIComponent(segmentCode)}/unassign`;
  const response = await authDelete(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to unassign segment: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Validation
// ============================================================================

/**
 * Validate doctor's segment configuration
 */
export async function validateSegmentConfig(
  userId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; validation: ValidationResult }> {
  const endpoint = `/api/v1/summary/segments/validate?doctor_id=${userId}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to validate configuration: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Consultation Type Segment Configuration (Admin)
// ============================================================================

export interface ConsultationTypeSegmentUpdate {
  segment_name?: string;
  default_category?: 'core' | 'additional' | 'excluded';
  display_order?: number;
  default_brevity_level?: BrevityLevel;
  default_terminology_style?: TerminologyStyle;
  prompt_section_text?: string;
  schema_definition_json?: any;
  is_required?: boolean;
}

/**
 * Get all segment definitions for a consultation type (Admin)
 */
export async function getConsultationTypeSegments(
  consultationTypeCode: ConsultationTypeCode,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; consultation_type_code: string; segments: any[]; count: number }> {
  const endpoint = `/api/v1/summary/admin/consultation-types/${encodeURIComponent(consultationTypeCode)}/segments`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to get consultation type segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update a segment definition for a consultation type (Admin)
 */
export async function updateConsultationTypeSegment(
  consultationTypeCode: ConsultationTypeCode,
  segmentCode: string,
  config: ConsultationTypeSegmentUpdate,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; segment: any }> {
  const endpoint = `/api/v1/summary/admin/consultation-types/${encodeURIComponent(consultationTypeCode)}/segments/${encodeURIComponent(segmentCode)}`;
  const response = await authPut(endpoint, auth ?? null, config);

  if (!response.ok) {
    throw new Error(`Failed to update consultation type segment: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Bulk update segment definitions for a consultation type (Admin)
 */
export async function bulkUpdateConsultationTypeSegments(
  consultationTypeCode: ConsultationTypeCode,
  segments: any[],
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; message: string; segments: any[]; count: number }> {
  const endpoint = `/api/v1/summary/admin/consultation-types/${encodeURIComponent(consultationTypeCode)}/segments/bulk`;
  const response = await authPost(endpoint, auth ?? null, { segments });

  if (!response.ok) {
    throw new Error(`Failed to bulk update consultation type segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get all segment definitions (Admin)
 */
export async function getAllSegments(
  consultationTypeCode?: ConsultationTypeCode,
  includeCommon: boolean = true,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; segments: any[]; count: number }> {
  const params = new URLSearchParams();
  if (consultationTypeCode) params.append('consultation_type_code', consultationTypeCode);
  params.append('include_common', includeCommon.toString());

  const endpoint = `/api/v1/summary/admin/segments?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch all segments: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Get consultation type color for UI display
 */
export function getConsultationTypeColor(typeCode: ConsultationTypeCode): string {
  const colors: Record<ConsultationTypeCode, string> = {
    OP: '#4F46E5', // Blue
    DISCHARGE: '#10B981', // Green
    RESPIRATORY: '#F59E0B', // Amber
  };
  return colors[typeCode] || '#6B7280'; // Gray fallback
}

/**
 * Get consultation type icon name
 */
export function getConsultationTypeIcon(typeCode: ConsultationTypeCode): string {
  const icons: Record<ConsultationTypeCode, string> = {
    OP: 'stethoscope',
    DISCHARGE: 'clipboard-check',
    RESPIRATORY: 'lungs',
  };
  return icons[typeCode] || 'file-text';
}

/**
 * Get consultation type display name
 */
export function getConsultationTypeName(typeCode: ConsultationTypeCode): string {
  const names: Record<ConsultationTypeCode, string> = {
    OP: 'Outpatient Consultation',
    DISCHARGE: 'Discharge Summary',
    RESPIRATORY: 'Respiratory Monitoring',
  };
  return names[typeCode] || typeCode;
}

/**
 * Create a new segment definition (Admin)
 */
export interface CreateSegmentRequest {
  segment_code: string;
  segment_name: string;
  consultation_type_code?: ConsultationTypeCode;  // Optional if template-specific
  template_code?: string;  // For template-specific segments
  prompt_section_text: string;
  schema_definition_json: any;
  default_category?: 'core' | 'additional';
  display_order?: number;
  default_brevity_level?: BrevityLevel;
  default_terminology_style?: TerminologyStyle;
  is_required?: boolean;
  is_active?: boolean;  // Segment activation status (auto-activated when assigned)
}

export async function createSegment(
  request: CreateSegmentRequest,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; segment: any }> {
  const endpoint = `/api/v1/summary/admin/segments`;
  const response = await authPost(endpoint, auth ?? null, request);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to create segment: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update a segment definition (Admin)
 */
export interface UpdateSegmentRequest {
  segment_name?: string;
  prompt_section_text?: string;
  schema_definition_json?: any;
  default_category?: 'core' | 'additional';
  display_order?: number;
  default_brevity_level?: BrevityLevel;
  default_terminology_style?: TerminologyStyle;
  is_required?: boolean;
  is_active?: boolean;  // Segment activation status
}

export async function updateSegment(
  segmentId: string,
  request: UpdateSegmentRequest,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; segment: any }> {
  const endpoint = `/api/v1/summary/admin/segments/${encodeURIComponent(segmentId)}`;
  const response = await authPut(endpoint, auth ?? null, request);

  if (!response.ok) {
    throw new Error(`Failed to update segment: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Segment Approval Workflow (Doctor → Admin)
// ============================================================================

/**
 * Get all pending segment requests (Admin)
 */
export async function getPendingSegments(
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  segments: any[];
  count: number;
}> {
  const endpoint = `/api/v1/summary/admin/segments/pending`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch pending segments: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Approve a pending segment request by adding schema (Admin)
 */
export async function approveSegmentRequest(
  segmentId: string,
  schemaDefinitionJson: any,
  adminId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; segment: any }> {
  const endpoint = `/api/v1/admin/segments/${encodeURIComponent(segmentId)}/approve?admin_id=${adminId}`;
  const response = await authPut(endpoint, auth ?? null, { schema_definition_json: schemaDefinitionJson });

  if (!response.ok) {
    throw new Error(`Failed to approve segment: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Segment Parent Tracking - Middle-Ground Approach
// ============================================================================

export interface CloneSegmentRequest {
  parent_segment_code: string;
  source_consultation_type_id: string;  // Required - where the parent segment is defined
  new_segment_code: string;
  new_segment_name: string;
  consultation_type_id?: string;  // For the new segment
  template_id?: string;
  // Optional overrides - if provided, use these instead of copying from parent
  prompt_section_text?: string;  // Custom prompt (if not provided, copies from parent)
  schema_definition_json?: Record<string, unknown>;  // Custom schema (if not provided, copies from parent)
}

/**
 * Clone an existing segment to create a new one with parent tracking
 */
export async function cloneSegment(
  request: CloneSegmentRequest,
  adminId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; segment: any; message: string }> {
  const endpoint = `/api/v1/summary/admin/segments/clone?admin_id=${adminId}`;
  const response = await authPost(endpoint, auth ?? null, request);

  if (!response.ok) {
    throw new Error(`Failed to clone segment: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Combine Segments - AI-Powered Merge
// ============================================================================

export interface CombineSegmentSource {
  segment_id: string;
  consultation_type_id: string;
}

export interface CombineSegmentsRequest {
  segments: CombineSegmentSource[];
}

export interface CombineSegmentsResponse {
  success: boolean;
  merged_prompt: string;
  merged_schema: Record<string, unknown>;
  merge_notes: string;
  source_segments: Array<{
    id: string;
    segment_code: string;
    segment_name: string;
  }>;
  message: string;
}

/**
 * Combine multiple segments into one using AI to merge prompts and schemas
 */
export async function combineSegments(
  request: CombineSegmentsRequest,
  adminId: string,
  auth?: string | AuthOptions | null
): Promise<CombineSegmentsResponse> {
  const endpoint = `/api/v1/summary/admin/segments/combine?admin_id=${adminId}`;
  const response = await authPost(endpoint, auth ?? null, request);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to combine segments: ${errorText || response.statusText}`);
  }

  return response.json();
}

/**
 * Get a segment along with its parent for comparison
 */
export async function getSegmentWithParent(
  segmentCode: string,
  consultationTypeId?: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  data: {
    segment: any;
    parent: any | null;
    relationship: {
      has_parent: boolean;
      is_cloned: boolean;
      diverged: boolean;
      cloned_at: string | null;
      last_sync_at: string | null;
      parent_code?: string;
    };
  };
}> {
  const params = new URLSearchParams();
  if (consultationTypeId) {
    params.append('consultation_type_id', consultationTypeId);
  }

  const endpoint = `/api/v1/summary/admin/segments/${encodeURIComponent(segmentCode)}/with-parent?${params}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to get segment with parent: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get all child segments that were cloned from a parent
 */
export async function getSegmentChildren(
  parentSegmentCode: string,
  includeDiverged: boolean = true,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  parent_segment_code: string;
  children: any[];
  counts: {
    total: number;
    in_sync: number;
    diverged: number;
  };
}> {
  const params = new URLSearchParams({ include_diverged: includeDiverged.toString() });

  const endpoint = `/api/v1/summary/admin/segments/${encodeURIComponent(parentSegmentCode)}/children?${params}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to get segment children: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Propagate changes from a parent segment to selected child segments
 */
export async function propagateParentChanges(
  parentSegmentCode: string,
  childSegmentCodes: string[],
  forceUpdateDiverged: boolean,
  adminId: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  message: string;
  updated: Array<{ segment_code: string; synced_at: string }>;
  skipped: Array<{ segment_code: string; reason: string }>;
  errors: Array<{ segment_code: string; error: string }>;
}> {
  const endpoint = `/api/v1/summary/admin/segments/${encodeURIComponent(parentSegmentCode)}/propagate?admin_id=${adminId}`;
  const response = await authPost(endpoint, auth ?? null, {
    segment_codes: childSegmentCodes,
    force_update_diverged: forceUpdateDiverged,
  });

  if (!response.ok) {
    throw new Error(`Failed to propagate changes: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Sync a single child segment from its parent
 */
export async function syncSegmentFromParent(
  segmentCode: string,
  consultationTypeId?: string,
  forceSync: boolean = false,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; segment: any; message: string }> {
  const params = new URLSearchParams({ force_sync: forceSync.toString() });
  if (consultationTypeId) {
    params.append('consultation_type_id', consultationTypeId);
  }

  const endpoint = `/api/v1/summary/admin/segments/${encodeURIComponent(segmentCode)}/sync-from-parent?${params}`;
  const response = await authPost(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to sync segment: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// NEW: Doctor Templates API
// ============================================================================

/**
 * Get all templates for a doctor
 */
export async function getActivatedTemplates(
  doctorId: string,
  accessToken?: string | null
): Promise<{ success: boolean; templates: ActivatedTemplate[]; count: number }> {
  const response = await authGet(
    `/api/v1/summary/templates?doctor_id=${doctorId}&filter_type=doctor`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch doctor templates: ${response.statusText}`);
  }

  const data = await response.json();
  const templates = data.templates || [];
  return {
    success: true,
    templates: templates,
    count: templates.length
  };
}

/**
 * Get templates accessible to a doctor for merge target dropdown
 *
 * Returns templates the doctor can use for merge operations:
 * - Owned templates (doctor_id matches)
 * - Shared templates (via doctor_templates junction)
 * - Common templates (doctor_id = NULL)
 *
 * Uses the existing /templates endpoint and transforms the response
 * to a simplified format for dropdown display.
 *
 * @param doctorId - Doctor UUID
 * @param auth - Bearer token or API key for authentication
 */
export async function getDoctorTemplates(
  doctorId: string,
  auth?: string | AuthOptions | null
): Promise<DoctorTemplatesResponse> {
  // Use existing endpoint with filter_type=doctor
  const endpoint = `/api/v1/summary/templates?filter_type=doctor&doctor_id=${encodeURIComponent(doctorId)}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch doctor templates: ${response.statusText}`);
  }

  const data = await response.json();

  // Transform full template objects to simplified MergeTargetTemplate format
  const templates = (data.templates || []).map((t: any) => ({
    template_code: t.template_code,
    template_name: t.template_name,
    is_common: t.doctor_id === null || t.doctor_id === undefined,
  }));

  return {
    success: true,
    templates,
    count: templates.length,
  };
}

/**
 * Get all templates accessible to a doctor (owned, shared, common)
 */
export async function getDoctorAccessibleTemplates(
  doctorId: string,
  consultationTypeId?: string,
  includeCommon: boolean = true,
  activeOnly: boolean = false,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; templates: any[]; count: number }> {
  const params = new URLSearchParams({
    doctor_id: doctorId,
    include_common: includeCommon.toString(),
    active_only: activeOnly.toString(),
  });

  if (consultationTypeId) {
    params.append('consultation_type_id', consultationTypeId);
  }

  const endpoint = `/api/v1/doctor-templates/accessible?${params}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch accessible templates: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get existing shares for a template
 */
export async function getTemplateShares(
  templateId: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  shares: {
    doctors: Array<{
      id: string;
      doctor_id: string;
      doctor_name: string;
      email: string;
      specialization: string;
      hospital_id: string;
      is_active: boolean;
      activated_at: string;
    }>;
    hospital_ids: string[];
    specializations: string[];
    total_shares: number;
  };
}> {
  const endpoint = `/api/v1/doctor-templates/template-shares/${templateId}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to get template shares: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Share template with individual doctors
 */
export async function shareTemplate(
  sharingDoctorId: string,
  templateId: string,
  doctorIds: string[],
  newOwnerId?: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; shared_count: number; failed_count: number; failures: any[]; ownership_assigned?: any }> {
  const endpoint = `/api/v1/doctor-templates/share`;
  const response = await authPost(endpoint, auth ?? null, {
    sharing_doctor_id: sharingDoctorId,
    template_id: templateId,
    doctor_ids: doctorIds,
    new_owner_id: newOwnerId || null,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to share template: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Share template with all doctors in a hospital
 */
export async function shareTemplateWithHospital(
  sharingDoctorId: string,
  templateId: string,
  hospitalId: string,
  newOwnerId?: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; shared_count: number; ownership_assigned?: any }> {
  const endpoint = `/api/v1/doctor-templates/share-hospital`;
  const response = await authPost(endpoint, auth ?? null, {
    sharing_doctor_id: sharingDoctorId,
    template_id: templateId,
    hospital_id: hospitalId,
    new_owner_id: newOwnerId || null,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to share template with hospital: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Share template with all doctors of a specialization
 */
export async function shareTemplateWithSpecialization(
  sharingDoctorId: string,
  templateId: string,
  specialization: string,
  newOwnerId?: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; shared_count: number; ownership_assigned?: any }> {
  const endpoint = `/api/v1/doctor-templates/share-specialization`;
  const response = await authPost(endpoint, auth ?? null, {
    sharing_doctor_id: sharingDoctorId,
    template_id: templateId,
    specialization: specialization,
    new_owner_id: newOwnerId || null,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to share template with specialization: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Activate a template for a doctor
 */
export async function activateDoctorTemplate(
  doctorId: string,
  templateId: string,
  consultationTypeId: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  is_active: boolean;
  activated_template_id: string;
  message: string;
  deactivated_previous: boolean;
}> {
  const endpoint = `/api/v1/doctor-templates/activate`;
  const response = await authPost(endpoint, auth ?? null, {
    doctor_id: doctorId,
    template_id: templateId,
    consultation_type_id: consultationTypeId,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to activate template: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Deactivate a template for a doctor
 */
export async function deactivateDoctorTemplate(
  doctorId: string,
  templateId: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  is_active: boolean;
  message: string;
}> {
  const params = new URLSearchParams({
    doctor_id: doctorId,
    template_id: templateId,
  });

  const endpoint = `/api/v1/doctor-templates/deactivate?${params}`;
  const response = await authPost(endpoint, auth ?? null);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate template: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Revoke doctor's access to a template
 */
export async function revokeTemplateAccess(
  sharingDoctorId: string,
  doctorId: string,
  templateId: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean }> {
  const params = new URLSearchParams({
    sharing_doctor_id: sharingDoctorId,
    doctor_id: doctorId,
    template_id: templateId,
  });

  const endpoint = `/api/v1/doctor-templates/revoke?${params}`;
  const response = await authDelete(endpoint, auth ?? null);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to revoke template access: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Activate from consultation type - Create doctor-owned template from consultation type
 */
export async function activateFromConsultationType(
  doctorId: string,
  consultationTypeId: string,
  templateName?: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  template: any;
  message: string;
}> {
  const endpoint = `/api/v1/doctor-templates/activate-from-consultation-type`;
  const response = await authPost(endpoint, auth ?? null, {
    doctor_id: doctorId,
    consultation_type_id: consultationTypeId,
    template_name: templateName,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to activate from consultation type: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Clone template - Create doctor-owned copy of an existing template
 */
export async function cloneTemplate(
  doctorId: string,
  sourceTemplateId: string,
  templateName?: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  template: any;
  message: string;
}> {
  const endpoint = `/api/v1/doctor-templates/clone`;
  const response = await authPost(endpoint, auth ?? null, {
    doctor_id: doctorId,
    source_template_id: sourceTemplateId,
    template_name: templateName,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to clone template: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get doctor dashboard - Returns visible consultation types and accessible templates
 */
export async function getDoctorDashboard(
  doctorId: string,
  auth?: string | AuthOptions | null
): Promise<{
  success: boolean;
  consultation_types: Array<{
    id: string;
    type_code: string;
    type_name: string;
    description?: string;
    icon_name?: string;
    color_code?: string;
    access_type: string;
    badge: string;
  }>;
  templates: Array<any>;
  consultation_types_count: number;
  templates_count: number;
}> {
  const endpoint = `/api/v1/doctor-templates/dashboard/${encodeURIComponent(doctorId)}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to get doctor dashboard: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// NEW: Processing Modes API (processing_modes table)
// ============================================================================

/**
 * Get all processing modes
 */
export async function getProcessingModes(accessToken?: string | null): Promise<{
  success: boolean;
  processing_modes: ProcessingMode[];
  count: number;
}> {
  const response = await authGet(`/api/v1/summary/processing-modes`, accessToken ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch processing modes: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get a specific processing mode by code
 */
export async function getProcessingMode(
  modeCode: string,
  auth?: string | AuthOptions | null
): Promise<{ success: boolean; processing_mode: ProcessingMode }> {
  const endpoint = `/api/v1/processing-modes/${encodeURIComponent(modeCode)}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch processing mode: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// NEW: Emotion Analysis API
// ============================================================================

export interface EmotionSegment {
  segment_code: string;
  segment_name: string;
  segment_data: Record<string, unknown>;
  confidence?: string;
  created_at?: string;
}

// NEW: Unified emotion segment (combines text + audio with source indicator)
export interface UnifiedEmotionSegment {
  segment_code: string;
  segment_name: string;
  source: 'text_only' | 'audio_only' | 'combined' | string;
  segment_value: Record<string, unknown>;
  created_at?: string;
}

// NEW: Congruence summary (simplified for display)
export interface CongruenceSummary {
  overall_congruence?: string;  // "High", "Moderate", "Low"
  congruence_score?: number;    // 0.0 - 1.0
  has_mismatches?: boolean;
}

export interface InterventionData {
  id?: string;
  code: string;
  name: string;
  description: string;
  category: string;
  priority: string;
  priority_score: number;
  trigger_reason: string;
  is_top_3: boolean;
  analysis_mode: string;
  rationale_sources: Array<{
    segment: string;
    source_mode: string;
    content: string;
  }>;
  created_at?: string;
}

export interface EmotionAnalysisData {
  extraction_id: string;
  // DEPRECATED: Legacy text/audio split (kept for backward compatibility with old extractions)
  text_emotions: EmotionSegment[];
  audio_emotions: EmotionSegment[];
  congruence: EmotionSegment | null;
  // NEW: Unified emotions (preferred - single list with source indicators)
  unified_emotions?: UnifiedEmotionSegment[];
  congruence_summary?: CongruenceSummary | null;
  // Interventions
  interventions: InterventionData[];
  // Started flags (to detect mode - if not started, extraction was never initiated)
  emotion_extraction_started: boolean;
  audio_emotion_extraction_started: boolean;
  congruence_analysis_started: boolean;
  // Completed flags
  emotion_extraction_completed: boolean;
  audio_emotion_extraction_completed: boolean;
  congruence_analysis_completed: boolean;
}

/**
 * Get emotion analysis results for an extraction
 */
export async function getEmotionAnalysis(
  extractionId: string,
  auth?: string | AuthOptions | null
): Promise<EmotionAnalysisData> {
  const endpoint = `/api/v1/extractions/${encodeURIComponent(extractionId)}/emotions`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch emotion analysis: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get emotion analysis results by submission_id (alternative lookup)
 *
 * Use this when extraction_id is not available but submission_id is.
 * This is a wrapper that looks up the extraction_id from submission_id.
 */
export async function getEmotionAnalysisBySubmission(
  submissionId: string,
  auth?: string | AuthOptions | null
): Promise<EmotionAnalysisData> {
  const endpoint = `/api/v1/extractions/by-submission/${encodeURIComponent(submissionId)}/emotions`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch emotion analysis: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Clinical Triage Suggestions
// ============================================================================

export interface TriageSuggestion {
  category: string;
  suggestion: string;
  priority: string;
  rationale: string;
  source: string;
  related_presentation?: string;
}

export interface TriageSuggestionsResponse {
  success: boolean;
  extraction_id: string | null;
  specialty: string;
  consultation_type: string;
  critical_actions: TriageSuggestion[];
  important_considerations: TriageSuggestion[];
  nice_to_have: TriageSuggestion[];
  matched_presentations: string[];
  identified_red_flags: string[];
  gap_analysis: {
    risk_level?: string;
    risk_factors?: string[];
    differential_considerations?: string[];
    safety_netting?: string;
    critical_suggestions?: Array<{
      type: string;
      suggestion: string;
      urgency: string;
      rationale: string;
    }>;
    additional_suggestions?: Array<{
      type: string;
      suggestion: string;
      rationale: string;
    }>;
    error?: string;
  };
  total_suggestions: number;
  generated_at: string;
  processing_time_ms: number;
}

/**
 * Get clinical triage suggestions for an extraction
 *
 * First checks if suggestions already exist in DB. If they do, returns cached results.
 * If not (or if forceRegenerate=true), generates new suggestions.
 *
 * Generates prioritized clinical suggestions including:
 * - Critical actions (red flags, safety concerns)
 * - Important considerations (missing investigations, history gaps)
 * - Nice-to-have recommendations
 *
 * Uses matched differential diagnosis trees + Gemini AI for gap analysis.
 */
export async function getTriageSuggestions(
  extractionId: string,
  includeGemini: boolean = true,
  auth?: string | AuthOptions | null,
  forceRegenerate: boolean = false
): Promise<TriageSuggestionsResponse> {
  const endpoint = `/api/v1/triage/generate`;
  const response = await authPost(endpoint, auth ?? null, {
    extraction_id: extractionId,
    include_gemini: includeGemini,
    force_regenerate: forceRegenerate,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch triage suggestions: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Extraction Edit Management
// ============================================================================

export interface UpdateExtractionRequest {
  edited_data: Record<string, unknown>;
  edited_by: string;  // Doctor UUID
}

export interface UpdateExtractionResponse {
  success: boolean;
  message: string;
  extraction_id: string;
  edit_count: number;
  last_edited_at: string;
  medicine_feedback_scheduled: boolean;
  ehr_sync_scheduled?: boolean;
  warnings?: Array<{
    category: string;
    severity: 'info' | 'warning' | 'error';
    message: string;
  }>;
}

/**
 * Save doctor's edits to an extraction
 *
 * This stores the edits in `edited_extraction_json` field while preserving
 * the original AI-generated extraction. Also schedules background task to
 * compare medicine name changes and log them for future matching.
 */
export async function saveExtractionEdits(
  extractionId: string,
  editedData: Record<string, unknown>,
  editedById: string,
  auth?: string | AuthOptions | null,
  editedByType: 'doctor' | 'nurse' = 'doctor'
): Promise<UpdateExtractionResponse> {
  const endpoint = `/api/v1/extractions/${encodeURIComponent(extractionId)}`;
  const response = await authPut(endpoint, auth ?? null, {
    edited_data: editedData,
    edited_by: editedById,
    edited_by_type: editedByType,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to save extraction edits: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Save doctor's edits to an extraction using submission_id
 *
 * This is a wrapper for cases where only submission_id is available
 * (from the recording workflow) and not the extraction_id.
 *
 * Lookup path: submission_id -> processing_jobs -> medical_extractions
 */
export async function saveExtractionEditsBySubmission(
  submissionId: string,
  editedData: Record<string, unknown>,
  editedById: string,
  auth?: string | AuthOptions | null,
  editedByType: 'doctor' | 'nurse' = 'doctor'
): Promise<UpdateExtractionResponse> {
  const endpoint = `/api/v1/extractions/by-submission/${encodeURIComponent(submissionId)}`;
  const response = await authPut(endpoint, auth ?? null, {
    edited_data: editedData,
    edited_by: editedById,
    edited_by_type: editedByType,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to save extraction edits: ${response.statusText}`);
  }

  return response.json();
}


// ─── Translation API Functions ──────────────────────────────────────────────

export interface ExtractionTranslation {
  id: string;
  extraction_id: string;
  target_language: string;
  translated_extraction_json: Record<string, unknown>;
  edited_translated_json: Record<string, unknown> | null;
  translation_edit_count: number;
  last_translation_edited_at: string | null;
  translation_started: boolean;
  translation_completed: boolean;
  translation_failed: boolean;
  translation_error: string | null;
  translation_time_seconds: number | null;
  model_used: string | null;
  created_at: string;
  updated_at: string;
}

export async function getExtractionTranslation(
  extractionId: string,
  auth?: string | AuthOptions | null,
): Promise<{ success: boolean; translation: ExtractionTranslation }> {
  const endpoint = `/api/v1/extractions/${encodeURIComponent(extractionId)}/translation`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('NO_TRANSLATION');
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch translation: ${response.statusText}`);
  }

  return response.json();
}

export async function saveTranslationEdits(
  extractionId: string,
  editedData: Record<string, unknown>,
  editedById: string,
  auth?: string | AuthOptions | null,
  editedByType: 'doctor' | 'nurse' = 'doctor',
): Promise<{ success: boolean; message: string; translation: ExtractionTranslation }> {
  const endpoint = `/api/v1/extractions/${encodeURIComponent(extractionId)}/translation`;
  const response = await authPut(endpoint, auth ?? null, {
    edited_data: editedData,
    edited_by: editedById,
    edited_by_type: editedByType,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to save translation edits: ${response.statusText}`);
  }

  return response.json();
}

export async function retryExtractionTranslation(
  extractionId: string,
  auth?: string | AuthOptions | null,
): Promise<{ success: boolean; message: string }> {
  const endpoint = `/api/v1/extractions/${encodeURIComponent(extractionId)}/translation/retry`;
  const response = await authPost(endpoint, auth ?? null, {});

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to retry translation: ${response.statusText}`);
  }

  return response.json();
}


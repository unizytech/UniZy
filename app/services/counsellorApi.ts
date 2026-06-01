/**
 * Counsellor API Service
 *
 * Provides API client functions for counsellor management endpoints.
 */

import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

export interface Counsellor {
  id: string;
  email: string;
  full_name: string;
  specialization: string | null;
  school_id: string | null;
  auth_user_id: string | null;
  default_template: string;
  default_transcription_engine: string;
  default_transcription_model: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
  translation_language: string | null;
}

export interface CreateCounsellorRequest {
  email: string;
  full_name: string;
  specialization?: string;
  default_template?: string;
  default_transcription_engine?: string;
  default_transcription_model?: string;
}

export interface UpdateCounsellorRequest {
  email?: string;
  full_name?: string;
  specialization?: string;
  default_template?: string;
  default_transcription_engine?: string;
  default_transcription_model?: string;
  is_active?: boolean;
  translation_language?: string;
}

export interface CounsellorConfiguration {
  doctor: Counsellor;
  global_config: any[];
  consultation_configs: {
    [key: string]: any[];
  };
}

/**
 * Get all counsellors
 */
export async function getCounsellors(activeOnly: boolean = true, accessToken?: string | null): Promise<Counsellor[]> {
  const response = await authGet(
    `/api/v1/counsellors?active_only=${activeOnly}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch counsellors: ${response.statusText}`);
  }

  const data = await response.json();
  return data.counsellors;
}

/**
 * Search counsellors by name or email
 */
export async function searchCounsellors(query: string, accessToken?: string | null): Promise<Counsellor[]> {
  if (query.length < 2) {
    return [];
  }

  const response = await authGet(
    `/api/v1/counsellors/search?q=${encodeURIComponent(query)}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to search counsellors: ${response.statusText}`);
  }

  const data = await response.json();
  return data.counsellors;
}

/**
 * Get counsellor by ID
 */
export async function getCounsellor(doctorId: string, accessToken?: string | null): Promise<Counsellor> {
  const response = await authGet(
    `/api/v1/counsellors/${doctorId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch counsellor: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctor;
}

/**
 * Create new counsellor
 */
export async function createCounsellor(request: CreateCounsellorRequest, accessToken?: string | null): Promise<Counsellor> {
  const response = await authPost(
    `/api/v1/counsellors`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create counsellor: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctor;
}

/**
 * Update counsellor
 */
export async function updateCounsellor(
  doctorId: string,
  request: UpdateCounsellorRequest,
  accessToken?: string | null
): Promise<Counsellor> {
  const response = await authPut(
    `/api/v1/counsellors/${doctorId}`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update counsellor: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctor;
}

/**
 * Deactivate counsellor (soft delete)
 */
export async function deactivateCounsellor(doctorId: string, accessToken?: string | null): Promise<Counsellor> {
  const response = await authDelete(
    `/api/v1/counsellors/${doctorId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate counsellor: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctor;
}

/**
 * Permanently delete a counsellor (hard delete)
 */
export async function deleteCounsellorPermanently(doctorId: string, accessToken?: string | null): Promise<void> {
  const response = await authDelete(
    `/api/v1/counsellors/${doctorId}/permanent`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to delete counsellor: ${response.statusText}`);
  }
}

/**
 * Get counsellor's configurations (global + consultation-specific)
 */
export async function getCounsellorConfigurations(
  doctorId: string,
  accessToken?: string | null
): Promise<CounsellorConfiguration> {
  const response = await authGet(
    `/api/v1/counsellors/${doctorId}/configurations`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch counsellor configurations: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    doctor: data.doctor,
    global_config: data.global_config,
    consultation_configs: data.consultation_configs,
  };
}

/**
 * Get counsellor's templates (directly owned by counsellor)
 */
export interface CounsellorTemplate {
  id: string;  // Template UUID
  template_code: string;
  template_name: string;  // Direct name (no override concept)
  consultation_type_id: string;
  consultation_type_code: string;
  consultation_type_name: string;
  description: string;
  counsellor_id: string;  // Owner of template
  is_active: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export async function getCounsellorTemplates(
  doctorId: string,
  accessToken?: string | null
): Promise<CounsellorTemplate[]> {
  const response = await authGet(
    `/api/v1/summary/templates?counsellor_id=${doctorId}&filter_type=doctor`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch counsellor templates: ${response.statusText}`);
  }

  const data = await response.json();
  return data.templates || [];
}

/**
 * Get list of all active counsellors (for sharing templates)
 */
export interface CounsellorListItem {
  id: string;
  full_name: string;
  email: string;
  specialization: string | null;
}

export async function getAllCounsellorsForSharing(accessToken?: string | null): Promise<CounsellorListItem[]> {
  const response = await authGet(
    `/api/v1/counsellors/list-all`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch counsellors list: ${response.statusText}`);
  }

  const data = await response.json();
  return data.counsellors || [];
}

/**
 * Get list of all active schools (for sharing templates)
 */
export interface School {
  id: string;
  school_name: string;
  school_code: string | null;
  city: string | null;
  state: string | null;
}

export async function getSchools(accessToken?: string | null): Promise<School[]> {
  const response = await authGet(
    `/api/v1/counsellors/schools`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch schools: ${response.statusText}`);
  }

  const data = await response.json();
  return data.schools || [];
}

/**
 * Get list of distinct specializations (for sharing templates)
 */
export async function getSpecializations(accessToken?: string | null): Promise<string[]> {
  const response = await authGet(
    `/api/v1/counsellors/specializations`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch specializations: ${response.statusText}`);
  }

  const data = await response.json();
  return data.specializations || [];
}

/**
 * Create counsellor for school (EHR-style: auto-generated UUID, uses school_code)
 */
export interface CreateCounsellorForSchoolRequest {
  school_code: string;
  full_name: string;
  email: string;
  specialization?: string;
}

export async function createCounsellorForSchool(
  request: CreateCounsellorForSchoolRequest,
  accessToken?: string | null
): Promise<{ counsellor_id: string }> {
  const response = await authPost(
    `/api/v1/counsellors/ehr`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create counsellor: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get counsellors filtered by school
 */
export async function getCounsellorsBySchool(
  hospitalId: string,
  accessToken?: string | null
): Promise<CounsellorListItem[]> {
  const response = await authGet(
    `/api/v1/counsellors/list-all?school_id=${hospitalId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch counsellors: ${response.statusText}`);
  }

  const data = await response.json();
  return data.counsellors || [];
}

export async function setCounsellorDefaultTemplate(
  doctorId: string,
  templateId: string | null,
  accessToken?: string | null
): Promise<{ default_template_id: string | null }> {
  const response = await authPut(
    `/api/v1/counsellors/${doctorId}/default-template`,
    accessToken ?? null,
    { template_id: templateId }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to set default template: ${response.statusText}`);
  }

  const data = await response.json();
  return { default_template_id: data.default_template_id ?? null };
}

/**
 * Nurse API Service
 *
 * Provides API client functions for nurse management endpoints.
 */

import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

export interface Nurse {
  id: string;
  email: string;
  full_name: string;
  qualification: string | null;
  hospital_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateNurseRequest {
  email: string;
  full_name: string;
  qualification?: string;
  hospital_id?: string;
}

export interface UpdateNurseRequest {
  email?: string;
  full_name?: string;
  qualification?: string;
  hospital_id?: string;
  is_active?: boolean;
}

export interface NurseTemplate {
  id: string;
  nurse_id: string;
  template_id: string;
  template_code: string;
  template_name?: string;
  consultation_type_code?: string;
  consultation_type_name?: string;
  description?: string;
  is_active: boolean;
  activated_at: string | null;
  created_at: string;
}

export interface NurseListItem {
  id: string;
  full_name: string;
  email: string;
  qualification: string | null;
}

export interface NurseDoctor {
  id: string;
  doctor_id: string;
  doctor_name: string;
  doctor_email: string;
  specialization: string | null;
  is_active: boolean;
}

// ============================================================================
// Nurse CRUD Operations
// ============================================================================

/**
 * Get all nurses
 */
export async function getNurses(
  activeOnly: boolean = true,
  hospitalId?: string,
  accessToken?: string | null
): Promise<Nurse[]> {
  let url = `/api/v1/nurses?active_only=${activeOnly}`;
  if (hospitalId) {
    url += `&hospital_id=${hospitalId}`;
  }

  const response = await authGet(url, accessToken ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch nurses: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurses;
}

/**
 * Search nurses by name or email
 */
export async function searchNurses(query: string, accessToken?: string | null): Promise<Nurse[]> {
  if (query.length < 2) {
    return [];
  }

  const response = await authGet(
    `/api/v1/nurses/search?q=${encodeURIComponent(query)}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to search nurses: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurses;
}

/**
 * Get nurse by ID
 */
export async function getNurse(nurseId: string, accessToken?: string | null): Promise<Nurse> {
  const response = await authGet(
    `/api/v1/nurses/${nurseId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch nurse: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurse;
}

/**
 * Create new nurse
 */
export async function createNurse(request: CreateNurseRequest, accessToken?: string | null): Promise<Nurse> {
  const response = await authPost(
    `/api/v1/nurses`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create nurse: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurse;
}

/**
 * Update nurse
 */
export async function updateNurse(
  nurseId: string,
  request: UpdateNurseRequest,
  accessToken?: string | null
): Promise<Nurse> {
  const response = await authPut(
    `/api/v1/nurses/${nurseId}`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update nurse: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurse;
}

/**
 * Deactivate nurse (soft delete)
 */
export async function deactivateNurse(nurseId: string, accessToken?: string | null): Promise<Nurse> {
  const response = await authDelete(
    `/api/v1/nurses/${nurseId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate nurse: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurse;
}

/**
 * Get list of all active nurses (for sharing templates)
 */
export async function getAllNursesForSharing(accessToken?: string | null): Promise<NurseListItem[]> {
  const response = await authGet(
    `/api/v1/nurses/list-all`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch nurses list: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurses || [];
}

// ============================================================================
// Nurse-Doctor Association Operations
// ============================================================================

/**
 * Get doctors linked to a nurse
 */
export async function getNurseDoctors(nurseId: string, accessToken?: string | null): Promise<NurseDoctor[]> {
  const response = await authGet(
    `/api/v1/nurses/${nurseId}/doctors`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch nurse's doctors: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctors || [];
}

/**
 * Link nurse to a doctor
 */
export async function linkNurseToDoctor(
  nurseId: string,
  doctorId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authPost(
    `/api/v1/nurses/${nurseId}/doctors/${doctorId}`,
    accessToken ?? null,
    {}
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to link nurse to doctor: ${response.statusText}`);
  }
}

/**
 * Unlink nurse from a doctor
 */
export async function unlinkNurseFromDoctor(
  nurseId: string,
  doctorId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authDelete(
    `/api/v1/nurses/${nurseId}/doctors/${doctorId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to unlink nurse from doctor: ${response.statusText}`);
  }
}

// ============================================================================
// Nurse Template Operations
// ============================================================================

/**
 * Get templates accessible by a nurse
 */
export async function getNurseTemplates(nurseId: string, accessToken?: string | null): Promise<NurseTemplate[]> {
  const response = await authGet(
    `/api/v1/nurse-templates/accessible?nurse_id=${nurseId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch nurse templates: ${response.statusText}`);
  }

  const data = await response.json();
  return data.templates || [];
}

/**
 * Get the active template for a nurse
 */
export async function getNurseActiveTemplate(nurseId: string, accessToken?: string | null): Promise<NurseTemplate | null> {
  const response = await authGet(
    `/api/v1/nurse-templates/active?nurse_id=${nurseId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    if (response.status === 404) {
      return null;
    }
    throw new Error(`Failed to fetch nurse active template: ${response.statusText}`);
  }

  const data = await response.json();
  return data.template || null;
}

/**
 * Share template with nurses
 */
export interface ShareTemplateWithNursesResult {
  success: boolean;
  message: string;
  shared_count: number;
  failed_count: number;
  failures?: Array<{ nurse_id: string; error: string }>;
}

export async function shareTemplateWithNurses(
  templateId: string,
  templateCode: string,
  nurseIds: string[],
  accessToken?: string | null
): Promise<ShareTemplateWithNursesResult> {
  const response = await authPost(
    `/api/v1/nurse-templates/share`,
    accessToken ?? null,
    {
      template_id: templateId,
      template_code: templateCode,
      nurse_ids: nurseIds,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to share template with nurses: ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Activate template for nurse
 */
export async function activateNurseTemplate(
  nurseId: string,
  templateId: string,
  accessToken?: string | null
): Promise<{ success: boolean; is_active: boolean }> {
  const response = await authPost(
    `/api/v1/nurse-templates/activate`,
    accessToken ?? null,
    {
      nurse_id: nurseId,
      template_id: templateId,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to activate nurse template: ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Deactivate template for nurse
 */
export async function deactivateNurseTemplate(
  nurseId: string,
  templateId: string,
  accessToken?: string | null
): Promise<{ success: boolean; is_active: boolean }> {
  const response = await authPost(
    `/api/v1/nurse-templates/deactivate`,
    accessToken ?? null,
    {
      nurse_id: nurseId,
      template_id: templateId,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate nurse template: ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Revoke nurse's access to a template
 */
export async function revokeNurseTemplateAccess(
  nurseId: string,
  templateId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authDelete(
    `/api/v1/nurse-templates/revoke?nurse_id=${nurseId}&template_id=${templateId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to revoke nurse template access: ${response.statusText}`);
  }
}

/**
 * Validate if nurse has access to use a template
 */
export async function validateNurseTemplateAccess(
  nurseId: string,
  templateId: string,
  accessToken?: string | null
): Promise<{ has_access: boolean }> {
  const response = await authGet(
    `/api/v1/nurse-templates/validate-access?nurse_id=${nurseId}&template_id=${templateId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to validate nurse template access: ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Get nurses who have access to a specific template (for sharing modal)
 */
export async function getTemplateNurseShares(
  templateId: string,
  accessToken?: string | null
): Promise<Array<{ nurse_id: string; is_active: boolean }>> {
  const response = await authGet(
    `/api/v1/nurse-templates/template-shares/${templateId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch template nurse shares: ${response.statusText}`);
  }

  const data = await response.json();
  return data.shares || [];
}

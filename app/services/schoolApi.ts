/**
 * School API Service
 *
 * Provides API client functions for school management endpoints.
 */

import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

export interface School {
  id: string;
  school_name: string;
  school_code: string | null;
  is_active?: boolean;
  city?: string | null;
  state?: string | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * Get all schools (active only, via counsellors/schools endpoint)
 */
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
 * Create a new school
 */
export async function createSchool(
  request: { school_code: string; school_name: string },
  accessToken?: string | null
): Promise<{ school_id: string }> {
  const response = await authPost(
    `/api/v1/schools`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create school: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update a school's name or code
 */
export async function updateSchool(
  hospitalId: string,
  request: { school_code?: string; school_name?: string },
  accessToken?: string | null
): Promise<School> {
  const response = await authPut(
    `/api/v1/schools/${hospitalId}`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update school: ${response.statusText}`);
  }

  const data = await response.json();
  return data.hospital;
}

/**
 * Deactivate a school (soft delete)
 */
export async function deactivateSchool(
  hospitalId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authDelete(
    `/api/v1/schools/${hospitalId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate school: ${response.statusText}`);
  }
}

/**
 * Permanently delete a school (hard delete)
 */
export async function deleteSchoolPermanently(
  hospitalId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authDelete(
    `/api/v1/schools/${hospitalId}/permanent`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to delete school: ${response.statusText}`);
  }
}

/**
 * Get feature flags for a school
 */
export async function getSchoolFeatures(
  hospitalId: string,
  accessToken?: string | null
): Promise<Record<string, boolean>> {
  const response = await authGet(
    `/api/v1/schools/${hospitalId}/features`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch feature flags: ${response.statusText}`);
  }

  const data = await response.json();
  return data.feature_flags || {};
}

/**
 * Update feature flags for a school (partial merge)
 */
export async function updateSchoolFeatures(
  hospitalId: string,
  flags: Record<string, boolean>,
  accessToken?: string | null
): Promise<Record<string, boolean>> {
  const response = await authPut(
    `/api/v1/schools/${hospitalId}/features`,
    accessToken ?? null,
    { feature_flags: flags }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update feature flags: ${response.statusText}`);
  }

  const data = await response.json();
  return data.feature_flags || {};
}

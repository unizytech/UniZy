/**
 * Hospital API Service
 *
 * Provides API client functions for hospital management endpoints.
 */

import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

export interface Hospital {
  id: string;
  hospital_name: string;
  hospital_code: string | null;
  is_active?: boolean;
  city?: string | null;
  state?: string | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * Get all hospitals (active only, via doctors/hospitals endpoint)
 */
export async function getHospitals(accessToken?: string | null): Promise<Hospital[]> {
  const response = await authGet(
    `/api/v1/doctors/hospitals`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch hospitals: ${response.statusText}`);
  }

  const data = await response.json();
  return data.hospitals || [];
}

/**
 * Create a new hospital
 */
export async function createHospital(
  request: { hospital_code: string; hospital_name: string },
  accessToken?: string | null
): Promise<{ hospital_id: string }> {
  const response = await authPost(
    `/api/v1/hospitals`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create hospital: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update a hospital's name or code
 */
export async function updateHospital(
  hospitalId: string,
  request: { hospital_code?: string; hospital_name?: string },
  accessToken?: string | null
): Promise<Hospital> {
  const response = await authPut(
    `/api/v1/hospitals/${hospitalId}`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update hospital: ${response.statusText}`);
  }

  const data = await response.json();
  return data.hospital;
}

/**
 * Deactivate a hospital (soft delete)
 */
export async function deactivateHospital(
  hospitalId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authDelete(
    `/api/v1/hospitals/${hospitalId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate hospital: ${response.statusText}`);
  }
}

/**
 * Permanently delete a hospital (hard delete)
 */
export async function deleteHospitalPermanently(
  hospitalId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authDelete(
    `/api/v1/hospitals/${hospitalId}/permanent`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to delete hospital: ${response.statusText}`);
  }
}

/**
 * Get feature flags for a hospital
 */
export async function getHospitalFeatures(
  hospitalId: string,
  accessToken?: string | null
): Promise<Record<string, boolean>> {
  const response = await authGet(
    `/api/v1/hospitals/${hospitalId}/features`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch feature flags: ${response.statusText}`);
  }

  const data = await response.json();
  return data.feature_flags || {};
}

/**
 * Update feature flags for a hospital (partial merge)
 */
export async function updateHospitalFeatures(
  hospitalId: string,
  flags: Record<string, boolean>,
  accessToken?: string | null
): Promise<Record<string, boolean>> {
  const response = await authPut(
    `/api/v1/hospitals/${hospitalId}/features`,
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

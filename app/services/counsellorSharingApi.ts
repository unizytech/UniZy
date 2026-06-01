/**
 * Counsellor Sharing API Service
 *
 * API client functions for counsellor-to-counsellor student sharing management.
 */

import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

export interface SharingLink {
  id: string;
  counsellor_id: string;
  counsellor_name: string;
  counsellor_email?: string;
  linked_counsellor_id: string;
  linked_counsellor_name: string;
  linked_counsellor_email?: string;
  sharing_mode: 'all_patients' | 'specific_patients';
  student_ids: string[] | null;
  student_count: number | null;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface CreateSharingLinkRequest {
  counsellor_id: string;
  linked_counsellor_id: string;
  student_ids: string[] | null;
}

export interface UpdateSharingLinkRequest {
  student_ids: string[] | null;
}

export async function getSharingLinks(
  hospitalId?: string,
  accessToken?: string | null,
): Promise<SharingLink[]> {
  const params = hospitalId ? `?school_id=${hospitalId}` : '';
  const response = await authGet(`/api/v1/counsellor-sharing${params}`, accessToken ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch sharing links: ${response.statusText}`);
  }

  const data = await response.json();
  return data.sharing_links || [];
}

export async function createSharingLink(
  request: CreateSharingLinkRequest,
  accessToken?: string | null,
): Promise<{ link_id: string; message: string }> {
  const response = await authPost(`/api/v1/counsellor-sharing`, accessToken ?? null, request);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create sharing link: ${response.statusText}`);
  }

  return response.json();
}

export async function updateSharingLink(
  doctorId: string,
  linkedCounsellorId: string,
  request: UpdateSharingLinkRequest,
  accessToken?: string | null,
): Promise<void> {
  const response = await authPut(
    `/api/v1/counsellor-sharing/${doctorId}/${linkedCounsellorId}`,
    accessToken ?? null,
    request,
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update sharing link: ${response.statusText}`);
  }
}

export async function addStudentsToLink(
  doctorId: string,
  linkedCounsellorId: string,
  patientIds: string[],
  accessToken?: string | null,
): Promise<{ student_ids: string[] }> {
  const response = await authPost(
    `/api/v1/counsellor-sharing/${doctorId}/${linkedCounsellorId}/students`,
    accessToken ?? null,
    { student_ids: patientIds },
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to add students: ${response.statusText}`);
  }

  return response.json();
}

export async function removeStudentsFromLink(
  doctorId: string,
  linkedCounsellorId: string,
  patientIds: string[],
  accessToken?: string | null,
): Promise<{ student_ids: string[] }> {
  const response = await authPost(
    `/api/v1/counsellor-sharing/${doctorId}/${linkedCounsellorId}/remove-students`,
    accessToken ?? null,
    { student_ids: patientIds },
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to remove students: ${response.statusText}`);
  }

  return response.json();
}

export async function deactivateSharingLink(
  doctorId: string,
  linkedCounsellorId: string,
  accessToken?: string | null,
): Promise<void> {
  const response = await authDelete(
    `/api/v1/counsellor-sharing/${doctorId}/${linkedCounsellorId}`,
    accessToken ?? null,
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate sharing link: ${response.statusText}`);
  }
}

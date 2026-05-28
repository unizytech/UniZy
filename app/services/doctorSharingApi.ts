/**
 * Doctor Sharing API Service
 *
 * API client functions for doctor-to-doctor patient sharing management.
 */

import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

export interface SharingLink {
  id: string;
  doctor_id: string;
  doctor_name: string;
  doctor_email?: string;
  linked_doctor_id: string;
  linked_doctor_name: string;
  linked_doctor_email?: string;
  sharing_mode: 'all_patients' | 'specific_patients';
  patient_ids: string[] | null;
  patient_count: number | null;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface CreateSharingLinkRequest {
  doctor_id: string;
  linked_doctor_id: string;
  patient_ids: string[] | null;
}

export interface UpdateSharingLinkRequest {
  patient_ids: string[] | null;
}

export async function getSharingLinks(
  hospitalId?: string,
  accessToken?: string | null,
): Promise<SharingLink[]> {
  const params = hospitalId ? `?hospital_id=${hospitalId}` : '';
  const response = await authGet(`/api/v1/doctor-sharing${params}`, accessToken ?? null);

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
  const response = await authPost(`/api/v1/doctor-sharing`, accessToken ?? null, request);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create sharing link: ${response.statusText}`);
  }

  return response.json();
}

export async function updateSharingLink(
  doctorId: string,
  linkedDoctorId: string,
  request: UpdateSharingLinkRequest,
  accessToken?: string | null,
): Promise<void> {
  const response = await authPut(
    `/api/v1/doctor-sharing/${doctorId}/${linkedDoctorId}`,
    accessToken ?? null,
    request,
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update sharing link: ${response.statusText}`);
  }
}

export async function addPatientsToLink(
  doctorId: string,
  linkedDoctorId: string,
  patientIds: string[],
  accessToken?: string | null,
): Promise<{ patient_ids: string[] }> {
  const response = await authPost(
    `/api/v1/doctor-sharing/${doctorId}/${linkedDoctorId}/patients`,
    accessToken ?? null,
    { patient_ids: patientIds },
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to add patients: ${response.statusText}`);
  }

  return response.json();
}

export async function removePatientsFromLink(
  doctorId: string,
  linkedDoctorId: string,
  patientIds: string[],
  accessToken?: string | null,
): Promise<{ patient_ids: string[] }> {
  const response = await authPost(
    `/api/v1/doctor-sharing/${doctorId}/${linkedDoctorId}/remove-patients`,
    accessToken ?? null,
    { patient_ids: patientIds },
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to remove patients: ${response.statusText}`);
  }

  return response.json();
}

export async function deactivateSharingLink(
  doctorId: string,
  linkedDoctorId: string,
  accessToken?: string | null,
): Promise<void> {
  const response = await authDelete(
    `/api/v1/doctor-sharing/${doctorId}/${linkedDoctorId}`,
    accessToken ?? null,
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate sharing link: ${response.statusText}`);
  }
}

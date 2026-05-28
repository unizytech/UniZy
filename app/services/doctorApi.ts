/**
 * Doctor API Service
 *
 * Provides API client functions for doctor management endpoints.
 */

import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

export interface Doctor {
  id: string;
  email: string;
  full_name: string;
  specialization: string | null;
  hospital_id: string | null;
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

export interface CreateDoctorRequest {
  email: string;
  full_name: string;
  specialization?: string;
  default_template?: string;
  default_transcription_engine?: string;
  default_transcription_model?: string;
}

export interface UpdateDoctorRequest {
  email?: string;
  full_name?: string;
  specialization?: string;
  default_template?: string;
  default_transcription_engine?: string;
  default_transcription_model?: string;
  is_active?: boolean;
  translation_language?: string;
}

export interface DoctorConfiguration {
  doctor: Doctor;
  global_config: any[];
  consultation_configs: {
    [key: string]: any[];
  };
}

/**
 * Get all doctors
 */
export async function getDoctors(activeOnly: boolean = true, accessToken?: string | null): Promise<Doctor[]> {
  const response = await authGet(
    `/api/v1/doctors?active_only=${activeOnly}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch doctors: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctors;
}

/**
 * Search doctors by name or email
 */
export async function searchDoctors(query: string, accessToken?: string | null): Promise<Doctor[]> {
  if (query.length < 2) {
    return [];
  }

  const response = await authGet(
    `/api/v1/doctors/search?q=${encodeURIComponent(query)}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to search doctors: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctors;
}

/**
 * Get doctor by ID
 */
export async function getDoctor(doctorId: string, accessToken?: string | null): Promise<Doctor> {
  const response = await authGet(
    `/api/v1/doctors/${doctorId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch doctor: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctor;
}

/**
 * Create new doctor
 */
export async function createDoctor(request: CreateDoctorRequest, accessToken?: string | null): Promise<Doctor> {
  const response = await authPost(
    `/api/v1/doctors`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create doctor: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctor;
}

/**
 * Update doctor
 */
export async function updateDoctor(
  doctorId: string,
  request: UpdateDoctorRequest,
  accessToken?: string | null
): Promise<Doctor> {
  const response = await authPut(
    `/api/v1/doctors/${doctorId}`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update doctor: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctor;
}

/**
 * Deactivate doctor (soft delete)
 */
export async function deactivateDoctor(doctorId: string, accessToken?: string | null): Promise<Doctor> {
  const response = await authDelete(
    `/api/v1/doctors/${doctorId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate doctor: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctor;
}

/**
 * Permanently delete a doctor (hard delete)
 */
export async function deleteDoctorPermanently(doctorId: string, accessToken?: string | null): Promise<void> {
  const response = await authDelete(
    `/api/v1/doctors/${doctorId}/permanent`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to delete doctor: ${response.statusText}`);
  }
}

/**
 * Get doctor's configurations (global + consultation-specific)
 */
export async function getDoctorConfigurations(
  doctorId: string,
  accessToken?: string | null
): Promise<DoctorConfiguration> {
  const response = await authGet(
    `/api/v1/doctors/${doctorId}/configurations`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch doctor configurations: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    doctor: data.doctor,
    global_config: data.global_config,
    consultation_configs: data.consultation_configs,
  };
}

/**
 * Get doctor's templates (directly owned by doctor)
 */
export interface DoctorTemplate {
  id: string;  // Template UUID
  template_code: string;
  template_name: string;  // Direct name (no override concept)
  consultation_type_id: string;
  consultation_type_code: string;
  consultation_type_name: string;
  description: string;
  doctor_id: string;  // Owner of template
  is_active: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export async function getDoctorTemplates(
  doctorId: string,
  accessToken?: string | null
): Promise<DoctorTemplate[]> {
  const response = await authGet(
    `/api/v1/summary/templates?doctor_id=${doctorId}&filter_type=doctor`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch doctor templates: ${response.statusText}`);
  }

  const data = await response.json();
  return data.templates || [];
}

/**
 * Get list of all active doctors (for sharing templates)
 */
export interface DoctorListItem {
  id: string;
  full_name: string;
  email: string;
  specialization: string | null;
}

export async function getAllDoctorsForSharing(accessToken?: string | null): Promise<DoctorListItem[]> {
  const response = await authGet(
    `/api/v1/doctors/list-all`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch doctors list: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctors || [];
}

/**
 * Get list of all active hospitals (for sharing templates)
 */
export interface Hospital {
  id: string;
  hospital_name: string;
  hospital_code: string | null;
  city: string | null;
  state: string | null;
}

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
 * Get list of distinct specializations (for sharing templates)
 */
export async function getSpecializations(accessToken?: string | null): Promise<string[]> {
  const response = await authGet(
    `/api/v1/doctors/specializations`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch specializations: ${response.statusText}`);
  }

  const data = await response.json();
  return data.specializations || [];
}

/**
 * Create doctor for hospital (EHR-style: auto-generated UUID, uses hospital_code)
 */
export interface CreateDoctorForHospitalRequest {
  hospital_code: string;
  full_name: string;
  email: string;
  specialization?: string;
}

export async function createDoctorForHospital(
  request: CreateDoctorForHospitalRequest,
  accessToken?: string | null
): Promise<{ doctor_id: string }> {
  const response = await authPost(
    `/api/v1/doctors/ehr`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create doctor: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get doctors filtered by hospital
 */
export async function getDoctorsByHospital(
  hospitalId: string,
  accessToken?: string | null
): Promise<DoctorListItem[]> {
  const response = await authGet(
    `/api/v1/doctors/list-all?hospital_id=${hospitalId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch doctors: ${response.statusText}`);
  }

  const data = await response.json();
  return data.doctors || [];
}

export async function setDoctorDefaultTemplate(
  doctorId: string,
  templateId: string | null,
  accessToken?: string | null
): Promise<{ default_template_id: string | null }> {
  const response = await authPut(
    `/api/v1/doctors/${doctorId}/default-template`,
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

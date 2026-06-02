/**
 * Dashboard API Client
 *
 * Provides functions for the school management dashboard:
 * - Intervention summary and category breakdown
 * - Student list by category
 * - Outcome tracking metrics
 * - Time-to-action analytics
 * - Status updates
 */

import { authGet, authPost, AuthOptions } from './apiClient';

export type { AuthOptions };

// ============================================================================
// Types
// ============================================================================

export interface PeriodStats {
  total_students: number;
  patients_with_interventions: number;
  percentage: number;
  revenue_potential: number;
}

export interface CategoryStats {
  category: string;
  label: string;
  icon: string;
  color: string;
  student_count: number;
  intervention_count: number;
  revenue_potential: number;
  aggregate_risk_score: number;
  risk_band: string;
  intervention_types: string[];
  card_type: 'score' | 'intervention';
  avg_compliance_score: number | null;
  avg_dropoff_probability: number | null;
}

export interface BreakdownStats {
  id: string;
  name: string;
  specialization?: string | null;
  by_category: Record<string, number>;
  total_at_risk: number;
}

export interface StudentMetricRow {
  student_id: string;
  patient_name: string;
  mrn: string | null;
  compliance_likelihood: string | null;
  dropoff_probability: number | null;
  is_surgery_candidate: boolean;
  health_service_count: number;
  health_service_level: string;
  has_followup_due: boolean;
  followup_count: number;
}

export interface InterventionSummaryResponse {
  total_students: number;
  patients_with_interventions: number;
  percentage: number;
  revenue_potential: number;
  by_period: Record<string, PeriodStats>;
  by_category: CategoryStats[];
  high_risk_categories: string[];
  by_department: BreakdownStats[];
  by_doctor: BreakdownStats[];
  by_patient: StudentMetricRow[];
  filters_applied: Record<string, any>;
}

export interface StudentIntervention {
  id: string;
  code: string;
  category: string;  // Raw DB category (OP_TO_IP, FOLLOWUP_DUE, etc.) - mapped to 5 dashboard categories at display layer
  priority: string;
  priority_score: number;
  take_up_likelihood: number | null;
  revenue_estimate: number | null;
  trigger_reason: string | null;
  action: string | null;
  days_since_generated: number;
  status: string;
}

export interface StudentWithInterventions {
  student_id: string;
  patient_name: string;
  mrn: string | null;
  counsellor_name: string | null;
  last_consultation: string | null;
  interventions: StudentIntervention[];
  total_revenue_potential: number;
}

export interface StudentsListResponse {
  students: StudentWithInterventions[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface OutcomeMetricsResponse {
  total_interventions: number;
  by_status: Record<string, number>;
  conversion_rate: number;
  completion_rate: number;
  actual_revenue: number;
  potential_revenue: number;
  revenue_capture_rate: number;
}

export interface TimeToActionResponse {
  avg_time_to_contact_hours: number;
  avg_time_to_completion_days: number;
  by_priority: Record<string, { avg_contact_hours: number; avg_completion_days: number }>;
  by_category: Record<string, { avg_contact_hours: number; avg_completion_days: number }>;
}

export interface UpdateStatusRequest {
  status: 'CONTACTED' | 'ACCEPTED' | 'DECLINED' | 'COMPLETED' | 'EXPIRED';
  notes?: string;
  actual_revenue?: number;
  updated_by_user_id?: string;
  updated_by_user_type?: string;
}

export interface UpdateStatusResponse {
  success: boolean;
  intervention_id: string;
  new_status: string;
  message: string;
}

// Period type for filtering
export type TimePeriod = 'today' | 'week' | 'mtd' | 'ytd' | 'custom';

// ============================================================================
// School & Counsellor Types
// ============================================================================

export interface School {
  id: string;
  school_name: string;
  school_code: string;
  city: string | null;
  state: string | null;
}

export interface Counsellor {
  id: string;
  full_name: string;
  counsellor_name?: string; // Alias for backwards compatibility
  email: string | null;
  specialization: string | null;
  school_id: string | null;
}

// Category type for filtering (6 dashboard categories)
export type InterventionCategory =
  | 'TREATMENT_COMPLIANCE'
  | 'DROP_OFF_RISK'
  | 'FOLLOWUP_DUE'
  | 'HEALTH_SERVICES'
  | 'SURGERY_CANDIDATE'
  | 'QUALITY_RISK';

// Priority threshold
export type PriorityThreshold = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

// ============================================================================
// Category Configuration
// ============================================================================

export const CATEGORY_CONFIG: Record<InterventionCategory, {
  label: string;
  icon: string;
  color: string;
  bgColor: string;
  textColor: string;
  borderColor: string;
  cardType: 'score' | 'intervention';
}> = {
  TREATMENT_COMPLIANCE: {
    label: 'Treatment Compliance',
    icon: '📋',
    color: 'blue',
    bgColor: 'bg-blue-50',
    textColor: 'text-blue-700',
    borderColor: 'border-blue-200',
    cardType: 'score',
  },
  DROP_OFF_RISK: {
    label: 'Drop-off Risk',
    icon: '⚠️',
    color: 'amber',
    bgColor: 'bg-amber-50',
    textColor: 'text-amber-700',
    borderColor: 'border-amber-200',
    cardType: 'score',
  },
  FOLLOWUP_DUE: {
    label: 'Follow-up Due',
    icon: '📅',
    color: 'cyan',
    bgColor: 'bg-cyan-50',
    textColor: 'text-cyan-700',
    borderColor: 'border-cyan-200',
    cardType: 'intervention',
  },
  HEALTH_SERVICES: {
    label: 'Health Services',
    icon: '💊',
    color: 'teal',
    bgColor: 'bg-teal-50',
    textColor: 'text-teal-700',
    borderColor: 'border-teal-200',
    cardType: 'intervention',
  },
  SURGERY_CANDIDATE: {
    label: 'Surgery Candidate',
    icon: '🏥',
    color: 'purple',
    bgColor: 'bg-purple-50',
    textColor: 'text-purple-700',
    borderColor: 'border-purple-200',
    cardType: 'intervention',
  },
  QUALITY_RISK: {
    label: 'Quality & Safety',
    icon: '🚨',
    color: 'red',
    bgColor: 'bg-red-50',
    textColor: 'text-red-700',
    borderColor: 'border-red-200',
    cardType: 'intervention',
  },
};

// ============================================================================
// Error Handling
// ============================================================================

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
// Dashboard Summary API
// ============================================================================

/**
 * Get intervention summary for the main dashboard
 */
export async function getInterventionSummary(
  options: {
    period?: TimePeriod;
    startDate?: string;
    endDate?: string;
    hospitalId?: string;
    departmentId?: string;
    doctorId?: string;
    priorityThreshold?: PriorityThreshold;
  } = {},
  auth?: string | AuthOptions | null
): Promise<InterventionSummaryResponse> {
  const params = new URLSearchParams();

  if (options.period) params.append('period', options.period);
  if (options.startDate) params.append('start_date', options.startDate);
  if (options.endDate) params.append('end_date', options.endDate);
  if (options.hospitalId) params.append('school_id', options.hospitalId);
  if (options.departmentId) params.append('department_id', options.departmentId);
  if (options.doctorId) params.append('counsellor_id', options.doctorId);
  if (options.priorityThreshold) params.append('priority_threshold', options.priorityThreshold);

  const endpoint = `/api/v1/dashboard/intervention-summary${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get intervention summary: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Student List API
// ============================================================================

/**
 * Get student list by category (or all categories if category is undefined)
 */
export async function getStudentsByCategory(
  category: InterventionCategory | undefined,
  options: {
    hospitalId?: string;
    departmentId?: string;
    doctorId?: string;
    priorityThreshold?: PriorityThreshold;
    page?: number;
    pageSize?: number;
    sortBy?: 'priority_score' | 'revenue_potential' | 'created_at';
    period?: TimePeriod;
  } = {},
  auth?: string | AuthOptions | null
): Promise<StudentsListResponse> {
  const params = new URLSearchParams();

  // Category is optional - if not provided, returns all categories
  if (category) params.append('category', category);

  if (options.hospitalId) params.append('school_id', options.hospitalId);
  if (options.departmentId) params.append('department_id', options.departmentId);
  if (options.doctorId) params.append('counsellor_id', options.doctorId);
  if (options.priorityThreshold) params.append('priority_threshold', options.priorityThreshold);
  if (options.page) params.append('page', options.page.toString());
  if (options.pageSize) params.append('page_size', options.pageSize.toString());
  if (options.sortBy) params.append('sort_by', options.sortBy);
  if (options.period) params.append('period', options.period);

  const endpoint = `/api/v1/dashboard/students?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get students: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Outcome Metrics API
// ============================================================================

/**
 * Get outcome metrics for ROI tracking
 */
export async function getOutcomeMetrics(
  options: {
    hospitalId?: string;
    departmentId?: string;
    doctorId?: string;
    period?: TimePeriod;
  } = {},
  auth?: string | AuthOptions | null
): Promise<OutcomeMetricsResponse> {
  const params = new URLSearchParams();

  if (options.hospitalId) params.append('school_id', options.hospitalId);
  if (options.departmentId) params.append('department_id', options.departmentId);
  if (options.doctorId) params.append('counsellor_id', options.doctorId);
  if (options.period) params.append('period', options.period);

  const endpoint = `/api/v1/dashboard/outcome-metrics${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get outcome metrics: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Time-to-Action API
// ============================================================================

/**
 * Get time-to-action analytics
 */
export async function getTimeToActionMetrics(
  options: {
    hospitalId?: string;
    period?: TimePeriod;
  } = {},
  auth?: string | AuthOptions | null
): Promise<TimeToActionResponse> {
  const params = new URLSearchParams();

  if (options.hospitalId) params.append('school_id', options.hospitalId);
  if (options.period) params.append('period', options.period);

  const endpoint = `/api/v1/dashboard/time-to-action${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get time-to-action metrics: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Status Update API
// ============================================================================

/**
 * Update intervention status
 */
export async function updateInterventionStatus(
  interventionId: string,
  request: UpdateStatusRequest,
  auth?: string | AuthOptions | null
): Promise<UpdateStatusResponse> {
  const endpoint = `/api/v1/dashboard/interventions/${encodeURIComponent(interventionId)}/status`;
  const response = await authPost(endpoint, auth ?? null, request);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update intervention status: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Format currency in Indian Rupees
 */
export function formatCurrency(amount: number): string {
  if (amount >= 10000000) {
    return `₹${(amount / 10000000).toFixed(1)}Cr`;
  } else if (amount >= 100000) {
    return `₹${(amount / 100000).toFixed(1)}L`;
  } else if (amount >= 1000) {
    return `₹${(amount / 1000).toFixed(1)}K`;
  }
  return `₹${amount.toFixed(0)}`;
}

/**
 * Format percentage
 */
export function formatPercentage(value: number): string {
  return `${value.toFixed(1)}%`;
}

/**
 * Get risk band color
 */
export function getRiskBandColor(riskBand: string): { bg: string; text: string } {
  switch (riskBand?.toUpperCase()) {
    case 'HIGH':
      return { bg: 'bg-red-100', text: 'text-red-700' };
    case 'MEDIUM':
      return { bg: 'bg-amber-100', text: 'text-amber-700' };
    case 'LOW':
      return { bg: 'bg-green-100', text: 'text-green-700' };
    default:
      return { bg: 'bg-gray-100', text: 'text-gray-700' };
  }
}

/**
 * Get priority color
 */
export function getPriorityColor(priority: string): { bg: string; text: string } {
  switch (priority?.toUpperCase()) {
    case 'CRITICAL':
      return { bg: 'bg-red-100', text: 'text-red-700' };
    case 'HIGH':
      return { bg: 'bg-orange-100', text: 'text-orange-700' };
    case 'MEDIUM':
      return { bg: 'bg-yellow-100', text: 'text-yellow-700' };
    case 'LOW':
      return { bg: 'bg-green-100', text: 'text-green-700' };
    default:
      return { bg: 'bg-gray-100', text: 'text-gray-700' };
  }
}

/**
 * Get status color
 */
export function getStatusColor(status: string): { bg: string; text: string; border: string } {
  switch (status?.toUpperCase()) {
    case 'PENDING':
      return { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-300' };
    case 'CONTACTED':
      return { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-300' };
    case 'ACCEPTED':
      return { bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-300' };
    case 'DECLINED':
      return { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-300' };
    case 'COMPLETED':
      return { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-300' };
    case 'EXPIRED':
      return { bg: 'bg-gray-50', text: 'text-gray-500', border: 'border-gray-300' };
    default:
      return { bg: 'bg-gray-50', text: 'text-gray-700', border: 'border-gray-300' };
  }
}

/**
 * Get days overdue text
 */
export function getDaysOverdueText(days: number): { text: string; color: string } {
  if (days <= 0) {
    return { text: 'Today', color: 'text-blue-600' };
  } else if (days === 1) {
    return { text: '1 day', color: 'text-amber-600' };
  } else if (days <= 7) {
    return { text: `${days} days`, color: 'text-amber-600' };
  } else {
    return { text: `${days} days`, color: 'text-red-600' };
  }
}

// ============================================================================
// School & Counsellor API
// ============================================================================

/**
 * Get list of all active schools
 */
export async function getSchools(
  auth?: string | AuthOptions | null
): Promise<School[]> {
  const endpoint = '/api/v1/counsellors/schools';
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get schools: ${response.statusText}`);
  }

  const data = await response.json();
  return data.schools || [];
}

/**
 * Get list of all active counsellors, optionally filtered by school
 */
export async function getCounsellors(
  options: {
    hospitalId?: string;
  } = {},
  auth?: string | AuthOptions | null
): Promise<Counsellor[]> {
  const endpoint = '/api/v1/counsellors/list-all';
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get counsellors: ${response.statusText}`);
  }

  const data = await response.json();
  let counsellors = data.counsellors || [];

  // Filter by school if specified
  if (options.hospitalId) {
    counsellors = counsellors.filter((d: Counsellor) => d.school_id === options.hospitalId);
  }

  // Map full_name to counsellor_name for backwards compatibility
  counsellors = counsellors.map((d: any) => ({
    ...d,
    counsellor_name: d.full_name || d.counsellor_name,
  }));

  return counsellors;
}

/**
 * Get list of distinct specializations from active counsellors
 */
export async function getSpecializations(
  auth?: string | AuthOptions | null
): Promise<string[]> {
  const endpoint = '/api/v1/counsellors/specializations';
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get specializations: ${response.statusText}`);
  }

  const data = await response.json();
  return data.specializations || [];
}

// ============================================================================
// Student Info API (for modal in By Student table)
// ============================================================================

export interface StudentLastVisitInfo {
  found: boolean;
  diagnosis: any;
  counsellor_name: string | null;
  visit_date: string | null;
  preferred_language: string | null;
}

/**
 * Get last visit info for a student (diagnosis, counsellor, date)
 * Uses existing student history endpoint
 */
export async function getStudentLastVisitInfo(
  studentId: string,
  auth?: string | AuthOptions | null
): Promise<StudentLastVisitInfo> {
  const endpoint = `/api/v1/students/${encodeURIComponent(studentId)}/last-diagnosis`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    return { found: false, diagnosis: null, counsellor_name: null, visit_date: null, preferred_language: null };
  }

  const data = await response.json();

  // Flatten diagnosis to a simple string (extract "name" from objects)
  let diagnosis: string | null = null;
  const raw = data.diagnosis;
  if (raw) {
    if (typeof raw === 'string') {
      diagnosis = raw;
    } else if (Array.isArray(raw)) {
      const names = raw.map((item: any) =>
        typeof item === 'string' ? item : item?.name || JSON.stringify(item)
      );
      diagnosis = names.join(', ');
    } else if (typeof raw === 'object' && raw.name) {
      diagnosis = raw.name;
    } else {
      diagnosis = JSON.stringify(raw);
    }
  }

  return {
    found: data.found ?? false,
    diagnosis,
    counsellor_name: data.metadata?.counsellor_name ?? null,
    visit_date: data.metadata?.created_at ?? null,
    preferred_language: data.patient?.preferred_language ?? null,
  };
}

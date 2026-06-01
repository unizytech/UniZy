/**
 * API Client for Student History Retrieval
 *
 * Provides functions to interact with /api/v1/students/* endpoints
 * for retrieving student medical history data.
 *
 * All functions accept an optional accessToken parameter for authentication.
 * Pass the Supabase JWT token to authenticate requests.
 */

import { authGet, AuthOptions } from './apiClient';

// Re-export AuthOptions for consumers
export type { AuthOptions };

const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

// ============================================================================
// Types
// ============================================================================

export interface StudentInfo {
  id: string;
  student_id: string;
  full_name: string | null;
  date_of_birth: string | null;
  gender: string | null;
}

export interface ExtractionMetadata {
  extraction_id: string;
  session_id: string | null;
  consultation_type: string | null;
  counsellor_id: string | null;
  counsellor_name: string | null;
  created_at: string;
  is_edited: boolean;
}

export interface LastPrescriptionResponse {
  patient: StudentInfo;
  prescription: Record<string, any> | null;
  metadata: ExtractionMetadata | null;
  found: boolean;
}

export interface LastDiagnosisResponse {
  patient: StudentInfo;
  diagnosis: any;
  metadata: ExtractionMetadata | null;
  found: boolean;
}

export interface LastInvestigationsResponse {
  patient: StudentInfo;
  investigations: any;
  metadata: ExtractionMetadata | null;
  found: boolean;
}

export interface CaseSummary {
  diagnosis: any;
  chief_complaints: any;
  prescription: any;
  examination: any;
  treatment_plan: any;
  follow_up: any;
  history: any;
}

export interface LastCaseSummaryResponse {
  patient: StudentInfo;
  case_summary: CaseSummary | null;
  metadata: ExtractionMetadata | null;
  found: boolean;
}

export interface EmotionSummary {
  anxiety_pre_consultation: Record<string, any> | null;
  anxiety_post_consultation: Record<string, any> | null;
  other_emotions: Record<string, any> | null;
  audio_anxiety: Record<string, any> | null;
  congruence_analysis: Record<string, any> | null;
  financial_concerns: Record<string, any> | null;
  compliance_likelihood: Record<string, any> | null;
}

export interface EmotionPatternItem {
  label: string;  // e.g., "Anxiety Level", "Financial Concerns", "Treatment Compliance"
  value: string;  // e.g., "High", "Moderate concerns", "Low likelihood"
  trend: 'improving' | 'worsening' | 'stable' | null;
}

export interface EmotionPatternSummary {
  visits_analyzed: number;
  patterns: EmotionPatternItem[];
  has_emotion_data: boolean;
}

export interface InterventionSummary {
  id: string;
  code: string;
  name: string;
  description: string;
  category: string;
  priority: string;
  priority_score: number;
  trigger_reason: string;
  is_top_3: boolean;
}

export interface StudentContextResponse {
  patient: StudentInfo;
  last_case_summary: CaseSummary | null;
  case_summary_metadata: ExtractionMetadata | null;
  emotion_summary: EmotionSummary | null;
  emotion_metadata: ExtractionMetadata | null;
  recommended_interventions: InterventionSummary[];
  consultation_count: number;
  last_visit_date: string | null;
  found: boolean;
}

export interface StudentSearchResult {
  id: string;
  student_id: string;
  full_name: string | null;
  date_of_birth: string | null;
  gender: string | null;
  consultation_count: number;
  last_visit_date: string | null;
  add_info?: Record<string, unknown> | null;  // Additional info (e.g., room/bed for NICU students)
  school_id?: string | null;
  school_name?: string | null;
}

export interface StudentSearchResponse {
  students: StudentSearchResult[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface ConsultationHistoryItem {
  extraction_id: string;
  session_id: string | null;
  consultation_type: string | null;
  consultation_type_name: string | null;
  counsellor_id: string | null;
  counsellor_name: string | null;
  created_at: string;
  is_edited: boolean;
  has_emotion_analysis: boolean;
  segment_count: number;
  primary_diagnosis: string | null;
  chief_complaint: string | null;
}

export interface ConsultationHistoryResponse {
  patient: StudentInfo;
  consultations: ConsultationHistoryItem[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface StudentHistoryAllResponse {
  patient: StudentInfo;
  last_prescription: Record<string, any> | null;
  last_diagnosis: any;
  last_investigations_ordered: any;
  last_investigations_results: any;
  last_case_summary: CaseSummary | null;
  emotion_summary: EmotionSummary | null;
  recommended_interventions: InterventionSummary[];
  consultation_count: number;
  last_visit_date: string | null;
  prescription_metadata: ExtractionMetadata | null;
  diagnosis_metadata: ExtractionMetadata | null;
  investigations_ordered_metadata: ExtractionMetadata | null;
  investigations_results_metadata: ExtractionMetadata | null;
  case_summary_metadata: ExtractionMetadata | null;
  emotion_metadata: ExtractionMetadata | null;
  // Summary view data (emotion patterns from last 3 visits, top 3 interventions)
  emotion_pattern_summary: EmotionPatternSummary | null;
  top_interventions: InterventionSummary[];
}

// ============================================================================
// Pattern Analysis Types
// ============================================================================

export interface VisitSummary {
  extraction_id: string;
  visit_date: string;
  consultation_type: string | null;
  counsellor_id: string | null;
  counsellor_name: string | null;
  diagnoses: Array<{
    name: string;
    type: string | null;
    code: string | null;
  }>;
  chief_complaints: string[];
  medicines: Array<{
    name: string;
    dosage: string | null;
    duration: string | null;
  }>;
  has_emotion_data: boolean;
  anxiety_score: number | null;
}

export interface DiagnosisPattern {
  diagnosis: string;
  occurrence_count: number;
  first_seen: string;
  last_seen: string;
  is_recurring: boolean;
}

export interface ComplaintPattern {
  complaint: string;
  occurrence_count: number;
  first_reported: string;
  last_reported: string;
  is_recurring: boolean;
}

export interface EmotionTrend {
  visit_date: string;
  extraction_id: string;
  anxiety_score: number | null;
  anxiety_level: string | null;
  other_emotions: string[];
  congruence_status: string | null;
}

export interface MultiVisitPatternResponse {
  patient: StudentInfo;
  visits_analyzed: number;
  visit_summaries: VisitSummary[];
  diagnosis_patterns: DiagnosisPattern[];
  complaint_patterns: ComplaintPattern[];
  recurring_diagnoses: string[];
  recurring_complaints: string[];
  common_medicines: Array<{
    name: string;
    prescription_count: number;
  }>;
}

export interface EmotionPatternResponse {
  patient: StudentInfo;
  visits_analyzed: number;
  emotion_trends: EmotionTrend[];
  average_anxiety_score: number | null;
  anxiety_trend: 'improving' | 'worsening' | 'stable' | 'insufficient_data';
  high_anxiety_visits: number;
  visits_with_emotion_data: number;
}

export interface DiagnosisPatternResponse {
  patient: StudentInfo;
  visits_analyzed: number;
  diagnosis_patterns: DiagnosisPattern[];
  recurring_diagnoses: string[];
  unique_diagnosis_count: number;
  most_common_diagnosis: string | null;
}

export interface ComplaintPatternResponse {
  patient: StudentInfo;
  visits_analyzed: number;
  complaint_patterns: ComplaintPattern[];
  recurring_complaints: string[];
  unique_complaint_count: number;
  most_common_complaint: string | null;
}

// ============================================================================
// Clinical Timeline Types
// ============================================================================

export interface TimelineChange {
  type: 'first_time_diagnosis' | 'recurring_diagnosis' | 'medication_added' | 'medication_removed' | 'medication_changed' | 'complaint_resolved' | 'complaint_not_mentioned' | 'complaint_new';
  category: 'diagnosis' | 'medication' | 'complaint';
  name: string;
  details: string | null;
  confidence: 'high' | 'medium' | 'low' | null;
  previous_value: string | null;
  new_value: string | null;
}

export interface TimelineVisit {
  extraction_id: string;
  visit_date: string;
  consultation_type: string | null;
  counsellor_name: string | null;
  changes: TimelineChange[];
  diagnoses: string[];
  complaints: string[];
  medications: Array<{ name: string; dosage: string }>;
  has_significant_changes: boolean;
}

export interface ClinicalTimelineResponse {
  patient: StudentInfo;
  timeline: TimelineVisit[];
  summary: {
    total_visits: number;
    first_time_diagnoses: number;
    recurring_diagnoses: number;
    medication_changes: number;
    resolved_complaints: number;
  };
  visit_count: number;
}

// ============================================================================
// Prescreen Types
// ============================================================================

export interface PrescreenResponse {
  patient: StudentInfo;
  // Latest prescreen template extraction (if exists)
  prescreen_data: Record<string, any> | null;
  prescreen_metadata: ExtractionMetadata | null;
  has_prescreen: boolean;
  // Emotion pattern summary (last 3 consultations)
  emotion_pattern_summary: EmotionPatternSummary | null;
  // Top 3 recommended interventions (from most recent consultation)
  top_interventions: InterventionSummary[];
  // Student warning factors (CAUTION segment from last consultation) - can be object or string
  warning_factors: Record<string, any> | string | null;
  warning_factors_date: string | null;
  // Past diagnosis summary (SUMMARY segment from last consultation) - can be object or string
  past_diagnosis_summary: Record<string, any> | string | null;
  past_diagnosis_summary_date: string | null;
  // Clinical timeline (last 5 visits)
  clinical_timeline: {
    timeline: Array<{
      extraction_id: string;
      visit_date: string;
      consultation_type: string | null;
      counsellor_name: string | null;
      changes: Array<{
        type: string;
        name: string;
        details: string | null;
        confidence: string;
      }>;
      diagnoses: string[];
      complaints: string[];
      medications: Array<{ name: string; dosage: string }>;
      has_significant_changes: boolean;
    }>;
    summary: {
      total_visits: number;
      first_time_diagnoses: number;
      recurring_diagnoses: number;
      medication_changes: number;
      resolved_complaints: number;
    };
    visit_count: number;
  } | null;
  // Last prescription (can be array or object depending on extraction format)
  last_prescription: Record<string, any> | Array<any> | null;
  last_prescription_date: string | null;
  // Metadata
  consultation_count: number;
  last_visit_date: string | null;
}

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
// Student Search
// ============================================================================

/**
 * Search for students by name or student ID
 */
export async function searchStudents(
  query?: string,
  doctorId?: string,
  page: number = 1,
  pageSize: number = 20,
  accessToken?: string | null
): Promise<StudentSearchResponse> {
  const params = new URLSearchParams();
  if (query) params.append('query', query);
  if (doctorId) params.append('counsellor_id', doctorId);
  params.append('page', page.toString());
  params.append('page_size', pageSize.toString());

  const response = await authGet(`/api/v1/students/search?${params.toString()}`, accessToken ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Search failed: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Consultation History
// ============================================================================

/**
 * Get consultation history for a student
 */
export async function getConsultationHistory(
  patientId: string,
  doctorId?: string,
  page: number = 1,
  pageSize: number = 20,
  auth?: string | AuthOptions | null
): Promise<ConsultationHistoryResponse> {
  const params = new URLSearchParams();
  if (doctorId) params.append('counsellor_id', doctorId);
  params.append('page', page.toString());
  params.append('page_size', pageSize.toString());

  const response = await authGet(
    `/api/v1/students/${encodeURIComponent(patientId)}/consultations?${params.toString()}`,
    auth ?? null
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get consultation history: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Individual History Endpoints
// ============================================================================

/**
 * Get last prescription for a student
 */
export async function getLastPrescription(
  patientId: string,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<LastPrescriptionResponse> {
  const params = new URLSearchParams();
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/last-prescription${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get last prescription: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get last diagnosis for a student
 */
export async function getLastDiagnosis(
  patientId: string,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<LastDiagnosisResponse> {
  const params = new URLSearchParams();
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/last-diagnosis${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get last diagnosis: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get last investigation results for a student
 */
export async function getLastInvestigationsResults(
  patientId: string,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<LastInvestigationsResponse> {
  const params = new URLSearchParams();
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/last-investigations-results${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get investigation results: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get last investigations ordered for a student
 */
export async function getLastInvestigationsOrdered(
  patientId: string,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<LastInvestigationsResponse> {
  const params = new URLSearchParams();
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/last-investigations-ordered${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get ordered investigations: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get last case summary for a student
 */
export async function getLastCaseSummary(
  patientId: string,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<LastCaseSummaryResponse> {
  const params = new URLSearchParams();
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/last-case-summary${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get case summary: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get student context (case summary + emotions + interventions)
 */
export async function getStudentContext(
  patientId: string,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<StudentContextResponse> {
  const params = new URLSearchParams();
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/context${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get student context: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get all student history data in one request
 */
export async function getAllStudentHistory(
  patientId: string,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<StudentHistoryAllResponse> {
  const params = new URLSearchParams();
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/history/all${params.toString() ? '?' + params.toString() : ''}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get student history: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Pattern Analysis APIs
// ============================================================================

/**
 * Get multi-visit pattern analysis for a student
 * Analyzes diagnoses, complaints, and medications across multiple visits
 */
export async function getMultiVisitPatterns(
  patientId: string,
  numVisits: number = 3,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<MultiVisitPatternResponse> {
  const params = new URLSearchParams();
  params.append('num_visits', numVisits.toString());
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/patterns/multi-visit?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get multi-visit patterns: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get emotion trend patterns for a student
 * Analyzes anxiety scores and emotion data across visits
 */
export async function getEmotionPatterns(
  patientId: string,
  numVisits: number = 5,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<EmotionPatternResponse> {
  const params = new URLSearchParams();
  params.append('num_visits', numVisits.toString());
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/patterns/emotions?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get emotion patterns: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get diagnosis pattern analysis for a student
 * Identifies recurring diagnoses across visits
 */
export async function getDiagnosisPatterns(
  patientId: string,
  numVisits: number = 5,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<DiagnosisPatternResponse> {
  const params = new URLSearchParams();
  params.append('num_visits', numVisits.toString());
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/patterns/diagnoses?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get diagnosis patterns: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get chief complaint patterns for a student
 * Identifies recurring complaints across visits
 */
export async function getComplaintPatterns(
  patientId: string,
  numVisits: number = 5,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<ComplaintPatternResponse> {
  const params = new URLSearchParams();
  params.append('num_visits', numVisits.toString());
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/patterns/complaints?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get complaint patterns: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Clinical Timeline API
// ============================================================================

/**
 * Get clinical timeline with change detection across visits
 *
 * Returns chronological timeline showing:
 * - New diagnoses (first time vs recurring)
 * - Medication changes (added, removed, dosage changed)
 * - Complaint resolution status (resolved, not mentioned, new)
 *
 * Logic for "new" diagnosis:
 * - Compares against last 3 visits OR last 6 months (whichever window is smaller)
 * - "First Time" = never seen in student history
 * - "Recurring" = seen before but not in recent window
 */
export async function getClinicalTimeline(
  patientId: string,
  numVisits: number = 5,
  doctorId?: string,
  auth?: string | AuthOptions | null
): Promise<ClinicalTimelineResponse> {
  const params = new URLSearchParams();
  params.append('num_visits', numVisits.toString());
  if (doctorId) params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/clinical-timeline?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get clinical timeline: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Prescreen API
// ============================================================================

/**
 * Get prescreen information for a student before consultation
 *
 * Returns:
 * 1. Latest prescreen template extraction (if available)
 * 2. Emotion pattern summary (aggregated from last 3 consultations)
 * 3. Top 3 recommended interventions (from most recent consultation)
 * 4. Student warning factors (CAUTION segment - allergies, contraindications)
 * 5. Past diagnosis summary (SUMMARY segment from last consultation)
 *
 * @param patientId - Student UUID
 * @param doctorId - Counsellor UUID (required - prescreen data is counsellor-specific)
 * @param auth - Bearer token or API key for authentication
 */
export async function getStudentPrescreen(
  patientId: string,
  doctorId: string,
  auth?: string | AuthOptions | null
): Promise<PrescreenResponse> {
  const params = new URLSearchParams();
  params.append('counsellor_id', doctorId);

  const endpoint = `/api/v1/students/${encodeURIComponent(patientId)}/prescreen?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get student prescreen: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Extraction Details API
// ============================================================================

export interface ExtractionSegment {
  segment_code: string;
  segment_value: Record<string, any> | null;
  version_type: string;
  is_edited: boolean;
  is_deleted: boolean;
  brevity_level: string | null;
  terminology_style: string | null;
  display_format: string | null;
}

export interface ExtractionDetailsResponse {
  extraction_id: string;
  session_id: string | null;
  consultation_type_id: string;
  counsellor_id: string | null;
  student_id: string | null;
  extraction_mode: string;
  segment_count: number;
  extraction_data: Record<string, any>;
  is_edited: boolean;
  edit_count: number;
  last_edited_at: string | null;
  last_edited_by: string | null;
  created_at: string;
  updated_at: string;
  segments: ExtractionSegment[] | null;
}

/**
 * Get full extraction details by extraction ID
 *
 * @param extractionId - The extraction UUID
 * @param includeSegments - Whether to include individual segment data (default: true)
 * @param auth - Bearer token or API key for authentication
 */
export async function getExtractionDetails(
  extractionId: string,
  includeSegments: boolean = true,
  auth?: string | AuthOptions | null
): Promise<ExtractionDetailsResponse> {
  const params = new URLSearchParams();
  params.append('include_segments', includeSegments.toString());

  const endpoint = `/api/v1/extractions/${encodeURIComponent(extractionId)}?${params.toString()}`;
  const response = await authGet(endpoint, auth ?? null);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get extraction details: ${response.statusText}`);
  }

  return response.json();
}

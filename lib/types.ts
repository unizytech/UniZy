// FIX: The LiveSession type is not exported from @google/genai.
// Define it locally based on its usage in the app.
export interface LiveSession {
  sendRealtimeInput(input: { media: { data: string; mimeType: string; } }): void;
  close(): void;
}

export enum AppMode {
  VHR = 'vhr',
  Live = 'live',
  PatientHistory = 'patient-history',
  PatientCreate = 'patient-create',
  Dashboard = 'dashboard',
  QAEngine = 'qa-engine',
  DoctorConfig = 'doctor-config',
  Providers = 'providers',
  TemplateAdmin = 'template-admin',
  SystemPromptAdmin = 'system-prompt-admin',
  MedicineAdmin = 'medicine-admin',
  InvestigationAdmin = 'investigation-admin',
  ExtractionHistory = 'extraction-history',
  UsageSummary = 'usage-summary',
  PocMetrics = 'poc-metrics',
  APIKeys = 'api-keys',
  Compare = 'compare',
  ProcessingModes = 'processing-modes',
  HospitalTemplates = 'hospital-templates',
  TriageLayers = 'triage-layers',
  DoctorSharing = 'doctor-sharing',
  TemplateFieldConfig = 'template-field-config',
}

export interface LiveSessionManager {
  session: LiveSession;
  close: () => void;
  pause: () => void;
  resume: () => void;
  getSessionHandle: () => string | null;
  isPaused: () => boolean;
}

export interface UploadResult {
  transcription: string;
  speed: number; // in seconds
  error?: string | null;
  // FIX: Add insights property to support displaying extracted medical data.
  insights?: any | null;
}

export interface ConversationUpdate {
  speaker: 'user' | 'ai';
  text: string;
  isFinal: boolean;
}

export interface TreatmentTask {
  task: string;
  when: string;
  instructions: string;
}

export interface ExtractionResult {
  promptName: string;
  model: string;
  extractionTime: number;
  data: any;
  error?: string | null;
}

export interface DirectExtractResult {
  insights: any;
  speed: number; // in seconds
  error?: string | null;
}

// ============================================================================
// Multi-Consultation Type Summary Extraction Types
// ============================================================================

export type BrevityLevel = 'concise' | 'balanced' | 'detailed';
export type TerminologyStyle = 'medical_terms' | 'simple_terms' | 'as_spoken';
export type SegmentCategory = 'core' | 'additional' | 'excluded';
export type ExtractionMode = 'core' | 'additional' | 'full';

// NOTE: EmotionExtractionMode removed (Jan 2026)
// Simplified to combined-only mode - use enable_emotion_analysis boolean instead

// Consultation Types (from database - can be extended via admin UI)
export type ConsultationTypeCode =
  | 'OP'
  | 'OP_CONCISE'
  | 'DISCHARGE'
  | 'NEONATAL_DAILY'
  | 'NEONATAL_PROFORMA'
  | 'OPTOMETRY'
  | 'OPHTHALMOLOGY'
  | 'OPHTHAL_DISCHARGE'
  | 'OPHTHAL_FULL'
  | string;  // Allow dynamic types from admin UI

export interface ConsultationType {
  id: string;
  type_code: string;  // Use string to support dynamic types
  type_name: string;
  description: string;
  specialty_applicable: string[] | null;
  is_active: boolean;
  display_order: number;
  icon_name: string | null;
  color_code: string | null;
  created_at: string;
  updated_at: string;
  // Emotion analysis configuration (simplified to single boolean)
  enable_emotion_analysis?: boolean;  // When true, runs combined multimodal (audio+text) emotion analysis
  // Triage and Consultation Insights configuration
  enable_triage_analysis?: boolean;  // Enable/disable triage suggestions (red flags, missing investigations)
  enable_consultation_insights?: boolean;  // Enable/disable consultation insights, assessments, and interventions
}

export interface ConsultationTypesResponse {
  success: boolean;
  consultation_types: ConsultationType[];
  count: number;
}

export interface ConsultationTypeResponse {
  success: boolean;
  consultation_type: ConsultationType;
}

export interface Segment {
  id: string;  // Unique segment definition ID (UUID)
  segment_code: string;
  segment_name: string;
  prompt_section_text: string;
  schema_definition_json: any;
  default_category: SegmentCategory;
  display_order: number;
  default_brevity_level: BrevityLevel;
  default_terminology_style: TerminologyStyle;
  is_active?: boolean;  // Segment activation status (auto-activated when assigned to consultation type/template)
  is_required: boolean;
}

export interface SegmentConfig {
  category?: SegmentCategory;
  brevity_level?: BrevityLevel;
  terminology_style?: TerminologyStyle;
}

export interface ExtractionRequest {
  transcript: string;
  doctor_id?: string;
  patient_id?: string;  // Patient ID for context (optional - also stored in session)
  template_code?: string;  // Unique identifier for DB lookups (primary)
  template_name?: string;  // Display name for human readability
  processing_mode?: string;  // Processing mode code (fast, default, thorough, ultra, ultra_fast)
  mode?: ExtractionMode;  // Extraction mode: core, additional, or full
  submission_id?: string;  // Processing job submission_id (required - from /chunk is_last=true or /live/session)
}

export interface ValidationResult {
  is_valid: boolean;
  error_message: string | null;
  warnings: string[];
}

export interface ExtractionMetadata {
  // Standardized metadata (same structure for API response and webhook)
  correlation_id: string | null;
  submission_id: string | null;
  extraction_id: string;
  doctor_id: string | null;
  patient_id: string | null;  // External varchar, not DB id
  template_code: string | null;  // Template code used for extraction
  mode: ExtractionMode | 'merge';  // core, additional, full, or merge
  segment_count: number;
  processing_mode: string | null;  // fast, default, thorough, etc.
  timestamp: string;  // ISO 8601 format
}

export interface OPExtractionResponse {
  success: boolean;
  insights: Record<string, any>;
  metadata: ExtractionMetadata;
}

export interface MedicalExtractionResponse {
  success: boolean;
  insights: Record<string, any>;
  metadata: ExtractionMetadata;
}

export interface Template {
  id: string;
  template_code: string;
  template_name: string;
  template_description?: string;  // Database column name
  description?: string;           // Alternative
  use_case?: string;              // Optional - might not be returned by all APIs
  is_default?: boolean;           // Optional - might not be returned by all APIs
  is_active?: boolean;            // Active status
  estimated_extraction_time_seconds?: number;  // Optional - might not be returned by all APIs
  consultation_type_id?: string | null;
  consultation_type_code?: string | null;
  consultation_type_name?: string | null;
  specialization?: string | null; // For visibility filtering
  hospital_id?: string | null;
  doctor_id?: string | null; // NULL = common template, UUID = doctor-owned
}

// Junction table: Template link for doctors (is_active = soft-delete flag)
export interface DoctorTemplate {
  id: string;
  doctor_id: string;
  template_id: string;
  is_active: boolean; // true = linked, false = soft-deleted
  activated_at: string;
  created_at: string;
  updated_at: string;
}

// Doctor template (directly owned by doctor)
// DEPRECATED: Use Template with doctor_id field instead
export interface ActivatedTemplate {
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

// Processing mode configuration (processing_modes table)
export interface ProcessingMode {
  id: string;
  mode_code: string;
  mode_name: string;
  description?: string;
  transcription_api: 'gemini_batch' | 'gemini_live';
  transcription_model: string;
  extraction_model: string;
  triage_model?: string;
  merge_model?: string;
  compare_model?: string;
  emotion_model?: string;
  insights_model?: string;
  validator_model?: string;
  estimated_time_seconds?: number;
  display_order: number;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface TemplateListResponse {
  success: boolean;
  templates: Template[];
  count: number;
}

export interface SegmentListResponse {
  success: boolean;
  segments: Segment[];
  consultation_type_code?: ConsultationTypeCode;
  consultation_type_name?: string;
  mode?: ExtractionMode;
  count?: number;
}

// Merge target template (for dropdown population)
export interface MergeTargetTemplate {
  template_code: string;        // Use as dropdown value
  template_name: string;        // Display in dropdown
  is_common: boolean;           // true if common template (doctor_id = NULL)
}

// Response from GET /api/v1/summary/templates?filter_type=doctor&doctor_id=<uuid>
export interface DoctorTemplatesResponse {
  success: boolean;
  templates: MergeTargetTemplate[];
  count: number;
}

// ============================================================================
// Nurse Types
// ============================================================================

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

export interface NurseTemplate {
  id: string;
  nurse_id: string;
  template_id: string;
  template_code: string;
  template_name?: string;
  consultation_type_code?: string;
  is_active: boolean;
  activated_at: string | null;
  created_at: string;
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
// Q&A Engine Types
// ============================================================================

export type QuestionCategory = 'clinical' | 'risk' | 'referrals' | 'interventions' | 'triage' | 'analytics';
export type QueryIntent = 'semantic' | 'hybrid' | 'sql';
export type SearchLevel = 'document' | 'segment';
export type QAResponseFormat = 'narrative' | 'table' | 'chart' | 'stat_card';
export type ChartType = 'bar' | 'line' | 'pie' | 'stat_card';
export type TemporalReferenceType = 'relative_visit' | 'absolute_date' | 'relative_time' | 'visit_number' | 'comparison';

export interface SuggestedQuestion {
  id: string;
  question: string;
  category: QuestionCategory;
  description?: string;
  expected_intent?: QueryIntent;
  expected_segment_codes?: string[];
}

export interface QASearchResult {
  extraction_id: string;
  patient_id?: string;
  patient_name?: string;
  patient_external_id?: string;
  doctor_id?: string;
  doctor_name?: string;
  consultation_type_name?: string;
  created_at: string;
  similarity_score: number;
  matched_segment_code?: string;
  matched_content_preview?: string;
  extraction_data?: Record<string, any>;
}

export interface QAChartData {
  chart_type: ChartType;
  title: string;
  labels: string[];
  values: number[];
  secondary_values?: number[];
  secondary_label?: string;
}

export interface QAStatCardData {
  title: string;
  value: number | string;
  subtitle?: string;
  change_percent?: number;
  trend?: 'up' | 'down' | 'neutral';
}

export interface TemporalReference {
  type: TemporalReferenceType;
  raw_text: string;
  resolved_date?: string;
  resolved_extraction_id?: string;
  visit_offset?: number;
}

export interface PatientVisit {
  extraction_id: string;
  created_at: string;
  consultation_type_id?: string;
  consultation_type_code?: string;
  consultation_type_name?: string;
  doctor_id?: string;
  doctor_name?: string;
}

export interface QAPriorContext {
  query: string;                // Previous user query
  narrative?: string;           // Previous assistant narrative response
  intent?: string;              // Previous query intent (semantic/hybrid/sql)
  extraction_id?: string;       // Extraction ID if previous answer was from a specific visit
}

export interface QAQueryRequest {
  query: string;
  hospital_id?: string;  // Required for admin users without hospital in auth context
  doctor_id?: string;
  patient_id?: string;
  consultation_type_id?: string;
  extraction_id?: string;  // Reference specific extraction/visit
  date_from?: string;
  date_to?: string;
  prior_context?: QAPriorContext;  // Last Q&A exchange for follow-up queries
  limit?: number;
  offset?: number;
}

export interface ReframeExpansion {
  original: string;
  expanded: string;
  category: string;  // abbreviation, colloquial, temporal
}

export interface ReframeCorrection {
  original: string;
  corrected: string;
  category: string;  // typo, misspelling, normalization
}

export interface QAQueryResponse {
  success: boolean;
  query: string;
  intent: QueryIntent;
  response_format: QAResponseFormat;
  // Reframing info (shows how query was transformed)
  reframed_query?: string;
  reframe_expansions?: ReframeExpansion[];
  reframe_corrections?: ReframeCorrection[];
  // Response content
  narrative?: string;
  results?: QASearchResult[];
  total_count?: number;
  referenced_extraction_ids?: string[];  // Extraction IDs referenced in narrative
  chart?: QAChartData;
  stat_card?: QAStatCardData;
  // Temporal/longitudinal response data
  temporal_references?: TemporalReference[];
  longitudinal_data?: Record<string, any>;  // Comparison/change data
  referenced_visits?: PatientVisit[];  // Visits referenced in response
  // Performance metrics
  reframe_time_ms?: number;
  temporal_resolution_time_ms?: number;
  longitudinal_time_ms?: number;
  embedding_time_ms?: number;
  search_time_ms?: number;
  synthesis_time_ms?: number;
  total_time_ms?: number;
  error_message?: string;
}

export interface QAMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response?: QAQueryResponse;
  isLoading?: boolean;
}

export interface EmbeddingModel {
  id: string;
  model_code: string;
  model_name: string;
  provider: string;
  dimensions: number;
  description?: string;
  is_default: boolean;
  is_active: boolean;
  price_per_million_tokens?: number;
}

// ============================================================================
// Feature Flags Types
// ============================================================================

export interface FeatureFlags {
  care_plan: boolean;
  merge: boolean;
  interventions: boolean;
  upload: boolean;
  ocr: boolean;
  edit_prescription: boolean;
  edit_investigation: boolean;
  edit_record: boolean;
  patient_qa: boolean;
  doctor_qa: boolean;
  template_configuration: boolean;
  patient_registration: boolean;
  billing: boolean;
  nudge_plan: boolean;
  iris: boolean;
  triage_support: boolean;
  [key: string]: boolean;  // extensible — new flags can be added without schema changes
}

export const DEFAULT_FEATURE_FLAGS: FeatureFlags = {
  care_plan: true,
  merge: true,
  interventions: true,
  upload: true,
  ocr: false,
  edit_prescription: true,
  edit_investigation: true,
  edit_record: true,
  patient_qa: true,
  doctor_qa: true,
  template_configuration: true,
  patient_registration: true,
  billing: false,
  nudge_plan: false,
  iris: false,
  triage_support: false,
};

export const FEATURE_FLAG_LABELS: Record<string, string> = {
  care_plan: 'Care Plan',
  merge: 'Merge Extractions',
  interventions: 'Interventions',
  upload: 'File Upload',
  ocr: 'OCR Processing',
  edit_prescription: 'Edit Prescription',
  edit_investigation: 'Edit Investigation',
  edit_record: 'Edit Record',
  patient_qa: 'Patient Q&A',
  doctor_qa: 'Doctor Q&A',
  template_configuration: 'Template Configuration',
  patient_registration: 'Patient Registration',
  billing: 'Billing',
  nudge_plan: 'Nudge Plan',
  iris: 'IRIS',
  triage_support: 'Triage Support',
};
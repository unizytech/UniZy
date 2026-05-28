'use client';

import React from 'react';

// Unified emotion segment (combines text + audio with source indicator)
export interface UnifiedEmotionSegment {
  segment_code: string;
  segment_name: string;
  source: 'text_only' | 'audio_only' | 'combined' | string;
  segment_value: Record<string, unknown>;
  created_at?: string;
}

export interface CongruenceSummary {
  overall_congruence?: string;
  congruence_score?: number;
  has_mismatches?: boolean;
}

export interface EmotionAnalysisData {
  // Unified emotions with source field (text_only, audio_only, combined)
  unifiedEmotions?: UnifiedEmotionSegment[];
  // Congruence summary (overall text vs audio alignment)
  congruenceSummary?: CongruenceSummary | null;
  // NOTE: Interventions moved to separate modal - use InterventionsModal
  loading: boolean;
  error?: string;
  // Started flags (to detect mode - if not started, don't show "in progress")
  emotionExtractionStarted?: boolean;
  audioEmotionExtractionStarted?: boolean;
  congruenceAnalysisStarted?: boolean;
  // Completed flags
  emotionExtractionCompleted?: boolean;
  audioEmotionExtractionCompleted?: boolean;
  congruenceAnalysisCompleted?: boolean;
}

interface EmotionAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: EmotionAnalysisData;
  extractionId?: string | null;
  onRefresh?: () => void;
}

// ============================================================================
// Intensity Mapping Configuration
// ============================================================================

interface IntensityConfig {
  level: number; // 0-100 percentage
  color: string; // Tailwind color class
  bgColor: string; // Background color class
  textColor: string; // Text color class
}

const INTENSITY_LEVELS: Record<string, IntensityConfig> = {
  // Anxiety / Severity / Compliance Levels
  'none': { level: 0, color: 'bg-gray-300', bgColor: 'bg-gray-100', textColor: 'text-gray-600' },
  'mild': { level: 33, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'moderate': { level: 66, color: 'bg-yellow-500', bgColor: 'bg-yellow-100', textColor: 'text-yellow-700' },
  'severe': { level: 100, color: 'bg-red-500', bgColor: 'bg-red-100', textColor: 'text-red-700' },
  'high': { level: 90, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'low': { level: 25, color: 'bg-red-500', bgColor: 'bg-red-100', textColor: 'text-red-700' },

  // Trajectory / Change
  'improved': { level: 25, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'stable': { level: 50, color: 'bg-blue-500', bgColor: 'bg-blue-100', textColor: 'text-blue-700' },
  'unchanged': { level: 50, color: 'bg-blue-500', bgColor: 'bg-blue-100', textColor: 'text-blue-700' },
  'worsened': { level: 90, color: 'bg-red-500', bgColor: 'bg-red-100', textColor: 'text-red-700' },
  'variable': { level: 60, color: 'bg-orange-500', bgColor: 'bg-orange-100', textColor: 'text-orange-700' },
  'unable to determine': { level: 50, color: 'bg-gray-400', bgColor: 'bg-gray-100', textColor: 'text-gray-600' },

  // Voice Warmth
  'cold': { level: 15, color: 'bg-blue-400', bgColor: 'bg-blue-100', textColor: 'text-blue-700' },
  'neutral': { level: 40, color: 'bg-gray-400', bgColor: 'bg-gray-100', textColor: 'text-gray-700' },
  'warm': { level: 70, color: 'bg-orange-400', bgColor: 'bg-orange-100', textColor: 'text-orange-700' },
  'very warm': { level: 95, color: 'bg-red-400', bgColor: 'bg-red-100', textColor: 'text-red-700' },

  // Consistency
  'highly consistent': { level: 95, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'mostly consistent': { level: 70, color: 'bg-green-400', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'inconsistent': { level: 30, color: 'bg-red-400', bgColor: 'bg-red-100', textColor: 'text-red-700' },

  // Compliance Likelihood (with percentage variants)
  // Note: 'high', 'moderate', 'low' already defined above - only add the percentage variants
  'high (80-100%)': { level: 90, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'moderate (50-79%)': { level: 66, color: 'bg-yellow-500', bgColor: 'bg-yellow-100', textColor: 'text-yellow-700' },
  'low (20-49%)': { level: 25, color: 'bg-red-500', bgColor: 'bg-red-100', textColor: 'text-red-700' },
  'very low': { level: 10, color: 'bg-red-600', bgColor: 'bg-red-100', textColor: 'text-red-800' },
  'very low (0-19%)': { level: 10, color: 'bg-red-600', bgColor: 'bg-red-100', textColor: 'text-red-800' },

  // Turn-taking Balance
  'doctor-dominated': { level: 80, color: 'bg-blue-500', bgColor: 'bg-blue-100', textColor: 'text-blue-700' },
  'balanced': { level: 50, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'patient-dominated': { level: 80, color: 'bg-purple-500', bgColor: 'bg-purple-100', textColor: 'text-purple-700' },

  // Conversation Flow
  'natural': { level: 90, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'mostly natural': { level: 70, color: 'bg-green-400', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'somewhat stilted': { level: 40, color: 'bg-yellow-500', bgColor: 'bg-yellow-100', textColor: 'text-yellow-700' },
  'stilted': { level: 20, color: 'bg-red-400', bgColor: 'bg-red-100', textColor: 'text-red-700' },

  // Engagement Level / General Medium
  'medium': { level: 50, color: 'bg-yellow-500', bgColor: 'bg-yellow-100', textColor: 'text-yellow-700' },

  // Primary Style
  'warm/empathetic': { level: 85, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'empathetic': { level: 85, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'clinical': { level: 50, color: 'bg-blue-500', bgColor: 'bg-blue-100', textColor: 'text-blue-700' },
  'authoritative': { level: 60, color: 'bg-purple-500', bgColor: 'bg-purple-100', textColor: 'text-purple-700' },
  'rushed': { level: 30, color: 'bg-red-500', bgColor: 'bg-red-100', textColor: 'text-red-700' },
  'collaborative': { level: 80, color: 'bg-teal-500', bgColor: 'bg-teal-100', textColor: 'text-teal-700' },

  // Clarity/Rating levels (Excellent, Good, Fair, Poor)
  'excellent': { level: 95, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'good': { level: 75, color: 'bg-green-400', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'fair': { level: 50, color: 'bg-yellow-500', bgColor: 'bg-yellow-100', textColor: 'text-yellow-700' },
  'poor': { level: 25, color: 'bg-red-500', bgColor: 'bg-red-100', textColor: 'text-red-700' },

  // Patient Concerns Addressed levels
  'fully': { level: 95, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'mostly': { level: 75, color: 'bg-green-400', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'partially': { level: 50, color: 'bg-yellow-500', bgColor: 'bg-yellow-100', textColor: 'text-yellow-700' },
  'not addressed': { level: 15, color: 'bg-red-500', bgColor: 'bg-red-100', textColor: 'text-red-700' },

  // Reassurance Effectiveness
  'none attempted': { level: 0, color: 'bg-gray-300', bgColor: 'bg-gray-100', textColor: 'text-gray-600' },

  // Patient Anxiety Impact
  'significantly reduced': { level: 15, color: 'bg-green-500', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'somewhat reduced': { level: 35, color: 'bg-green-400', bgColor: 'bg-green-100', textColor: 'text-green-700' },
  'no effect': { level: 50, color: 'bg-gray-400', bgColor: 'bg-gray-100', textColor: 'text-gray-600' },
  'somewhat increased': { level: 70, color: 'bg-orange-500', bgColor: 'bg-orange-100', textColor: 'text-orange-700' },
  'significantly increased': { level: 90, color: 'bg-red-500', bgColor: 'bg-red-100', textColor: 'text-red-700' },
};

function getIntensityConfig(value: string): IntensityConfig {
  const normalized = value?.toLowerCase()?.trim() || '';
  return INTENSITY_LEVELS[normalized] || {
    level: 50,
    color: 'bg-gray-400',
    bgColor: 'bg-gray-100',
    textColor: 'text-gray-700'
  };
}

// ============================================================================
// Field Display Order Configuration
// ============================================================================

// Define the display order for each segment type - important metrics first, notes/rationale last
const FIELD_ORDER: Record<string, string[]> = {
  // Audio-based emotion segments
  'AUDIO_PATIENT_ANXIETY': ['anxiety_trajectory', 'initial_anxiety_level', 'final_anxiety_level', 'rationale'],
  'AUDIO_DOCTOR_STYLE': ['primary_style', 'voice_warmth', 'tone_consistency', 'rationale'],
  'AUDIO_INTERACTION_DYNAMICS': ['turn_taking_balance', 'conversation_flow', 'mutual_engagement', 'rationale'],
  'AUDIO_FINANCIAL_CONCERNS': ['severity', 'rationale'],
  'AUDIO_COMPLIANCE_INDICATORS': ['likelihood', 'rationale'],
  'AUDIO_OTHER_EMOTIONS': ['dominant_emotion', 'emotional_trajectory', 'rationale'],

  // Text-based emotion segments (use 'notes' instead of 'rationale')
  'TEXT_EMOTION_ANXIETY_PRE_CONSULTATION': ['level', 'indicators', 'timestamp_start', 'confidence', 'notes'],
  'TEXT_EMOTION_ANXIETY_POST_CONSULTATION': ['level', 'change_from_pre', 'indicators', 'timestamp_end', 'confidence', 'notes'],
  'TEXT_EMOTION_OTHER_EMOTIONS_DETECTED': ['dominant_emotion', 'emotions_detected', 'notes'],
  'TEXT_EMOTION_FINANCIAL_CONCERNS': ['severity', 'concerns_present', 'specific_concerns', 'alternative_treatment_requested', 'confidence', 'notes'],
  'TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD': ['likelihood', 'positive_factors', 'negative_factors', 'key_barriers', 'recommendations', 'confidence', 'notes'],
  'TEXT_EMOTION_DOCTOR_COMMUNICATION_STYLE': [
    'primary_style', 'secondary_style', 'patient_anxiety_impact', 'clarity_rating',
    'empathy_indicators', 'communication_strengths', 'areas_for_improvement', 'confidence', 'notes'
  ],
};

// Fields that should show progress bars
const PROGRESS_BAR_FIELDS = new Set([
  // Audio segments
  'anxiety_trajectory', 'initial_anxiety_level', 'final_anxiety_level',
  'voice_warmth', 'tone_consistency', 'primary_style',
  'turn_taking_balance', 'conversation_flow', 'mutual_engagement',
  'emotional_trajectory',

  // Text segments - anxiety and severity levels
  'level', 'severity', 'likelihood',
  'change_from_pre', 'patient_anxiety_impact', 'clarity_rating',
  'confidence',
]);

// Fields to exclude from default rendering (shown specially elsewhere)
const EXCLUDED_FIELDS = new Set<string>([]);

// ============================================================================
// In Progress Section Component
// ============================================================================

interface InProgressSectionProps {
  title: string;
  icon: string;
  color: 'blue' | 'green' | 'purple';
}

function InProgressSection({ title, icon, color }: InProgressSectionProps) {
  const colorClasses = {
    blue: {
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      text: 'text-blue-700',
      spinner: 'border-blue-500',
    },
    green: {
      bg: 'bg-green-50',
      border: 'border-green-200',
      text: 'text-green-700',
      spinner: 'border-green-500',
    },
    purple: {
      bg: 'bg-purple-50',
      border: 'border-purple-200',
      text: 'text-purple-700',
      spinner: 'border-purple-500',
    },
  };

  const colors = colorClasses[color];

  return (
    <div className={`${colors.bg} border ${colors.border} rounded-lg p-4`}>
      <div className="flex items-center gap-3">
        <span className="text-xl">{icon}</span>
        <div className="flex-1">
          <h3 className={`font-semibold ${colors.text}`}>{title}</h3>
          <p className="text-sm text-gray-500">Analysis in progress...</p>
        </div>
        <div className={`animate-spin rounded-full h-5 w-5 border-2 border-t-transparent ${colors.spinner}`}></div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function EmotionAnalysisModal({ isOpen, onClose, data, extractionId, onRefresh }: EmotionAnalysisModalProps) {
  if (!isOpen) return null;

  // Check for unified emotions
  const hasUnifiedEmotions = data.unifiedEmotions && data.unifiedEmotions.length > 0;
  const hasAnyData = hasUnifiedEmotions;

  // Check if analysis is still in progress
  const emotionInProgress = (data.emotionExtractionStarted === true && data.emotionExtractionCompleted === false) ||
                            (data.audioEmotionExtractionStarted === true && data.audioEmotionExtractionCompleted === false);
  const congruenceInProgress = data.congruenceAnalysisStarted === true && data.congruenceAnalysisCompleted === false;
  const anyInProgress = (emotionInProgress || congruenceInProgress) && !hasUnifiedEmotions;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="bg-gradient-to-r from-purple-600 to-indigo-600 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Emotion Analysis</h2>
              {extractionId && (
                <p className="text-purple-200 text-xs font-mono">ID: {extractionId.slice(0, 8)}...</p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-white hover:bg-white hover:bg-opacity-20 rounded-full p-2 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {data.loading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
              <p className="mt-4 text-gray-600">Loading emotion analysis...</p>
            </div>
          ) : data.error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
              <svg className="w-12 h-12 text-red-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-red-700 font-medium">{data.error}</p>
            </div>
          ) : !hasAnyData ? (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
              <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-gray-600 font-medium">No emotion analysis available</p>
              <p className="text-gray-400 text-sm mt-1">
                Emotion analysis may still be processing or not enabled for this consultation type.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Unified Emotions Section */}
              {hasUnifiedEmotions ? (
                <UnifiedEmotionsSection
                  segments={data.unifiedEmotions!}
                  congruenceSummary={data.congruenceSummary}
                />
              ) : anyInProgress ? (
                <InProgressSection
                  title="Emotion Analysis"
                  icon="🧠"
                  color="purple"
                />
              ) : null}

              {/* Note: Interventions are now displayed in a separate modal - View Interventions button */}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-gray-50 px-6 py-4 border-t flex justify-between items-center">
          {/* In Progress Info */}
          {anyInProgress && !data.loading ? (
            <div className="flex items-center gap-2 text-amber-600 text-sm">
              <svg className="w-4 h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Analysis in progress (~15-30s)</span>
            </div>
          ) : (
            <div></div>
          )}

          {/* Buttons */}
          <div className="flex gap-3">
            {onRefresh && (
              <button
                onClick={onRefresh}
                disabled={data.loading}
                className="px-4 py-2 bg-purple-100 hover:bg-purple-200 text-purple-700 rounded-lg transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                <svg className={`w-4 h-4 ${data.loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh
              </button>
            )}
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg transition-colors font-medium"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Progress Bar Component
// ============================================================================

interface ProgressBarProps {
  value: string;
  label: string;
}

function ProgressBar({ value, label }: ProgressBarProps) {
  const config = getIntensityConfig(value);

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1">
        <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full ${config.color} transition-all duration-300 rounded-full`}
            style={{ width: `${config.level}%` }}
          />
        </div>
      </div>
      <span className={`text-sm font-semibold min-w-[100px] text-right ${config.textColor}`}>
        {label}
      </span>
    </div>
  );
}

// ============================================================================
// Field Renderer Component
// ============================================================================

interface FieldRendererProps {
  fieldKey: string;
  value: unknown;
}

function FieldRenderer({ fieldKey, value }: FieldRendererProps) {
  const formattedLabel = formatSegmentCode(fieldKey);
  const isRationaleOrNotes = fieldKey === 'rationale' || fieldKey === 'notes';
  const showProgressBar = PROGRESS_BAR_FIELDS.has(fieldKey) && typeof value === 'string';

  // Handle rationale/notes specially - show at bottom with different styling
  if (isRationaleOrNotes && typeof value === 'string') {
    const label = fieldKey === 'rationale' ? 'Rationale' : 'Notes';
    return (
      <div className="mt-4 pt-3 border-t border-gray-100">
        <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">
          {label}
        </div>
        <p className="text-sm text-gray-600 italic">{value}</p>
      </div>
    );
  }

  // Show progress bar for intensity fields
  if (showProgressBar && typeof value === 'string') {
    return (
      <div>
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
          {formattedLabel}
        </div>
        <ProgressBar value={value} label={capitalizeFirst(value)} />
      </div>
    );
  }

  // Handle boolean values
  if (typeof value === 'boolean') {
    return (
      <div>
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
          {formattedLabel}
        </div>
        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
          value ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
        }`}>
          {value ? 'Yes' : 'No'}
        </span>
      </div>
    );
  }

  // Handle arrays (like emotions list, indicators, etc.)
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return (
        <div>
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
            {formattedLabel}
          </div>
          <span className="text-gray-400 italic text-sm">None</span>
        </div>
      );
    }

    // Check if array contains objects (structured data like emotions_detected, specific_concerns, key_barriers)
    const hasStructuredItems = value.length > 0 && typeof value[0] === 'object' && value[0] !== null;

    if (hasStructuredItems) {
      return (
        <div>
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
            {formattedLabel}
          </div>
          <div className="space-y-2">
            {value.map((item, idx) => {
              const obj = item as Record<string, unknown>;
              // Handle emotions_detected structure
              if ('emotion' in obj) {
                const severity = obj.severity ? String(obj.severity) : 'moderate';
                const clinicalSig = obj.clinical_significance ? String(obj.clinical_significance) : null;
                const evidenceList = Array.isArray(obj.evidence) ? (obj.evidence as string[]) : [];
                const emotionConfig = getIntensityConfig(severity);
                return (
                  <div key={idx} className={`${emotionConfig.bgColor} rounded-lg p-3 border border-gray-200`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className={`font-medium ${emotionConfig.textColor}`}>
                        {String(obj.emotion)}
                      </span>
                      <div className="flex items-center gap-2">
                        {severity && (
                          <span className={`text-xs px-2 py-0.5 rounded-full ${emotionConfig.color} text-white`}>
                            {severity}
                          </span>
                        )}
                        {clinicalSig && (
                          <span className="text-xs text-gray-500">
                            {clinicalSig} significance
                          </span>
                        )}
                      </div>
                    </div>
                    {evidenceList.length > 0 && (
                      <div className="text-xs text-gray-600 mt-1">
                        {evidenceList.map((e, i) => (
                          <div key={i} className="flex items-start gap-1">
                            <span className="text-gray-400">•</span>
                            <span>{e}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              }
              // Handle specific_concerns structure
              if ('concern_type' in obj) {
                const impactOnCompliance = obj.impact_on_compliance ? String(obj.impact_on_compliance) : null;
                const evidence = obj.evidence ? String(obj.evidence) : null;
                return (
                  <div key={idx} className="bg-amber-50 rounded-lg p-3 border border-amber-200">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-amber-700">{String(obj.concern_type)}</span>
                      {impactOnCompliance && (
                        <span className="text-xs text-amber-600">{impactOnCompliance}</span>
                      )}
                    </div>
                    {evidence && (
                      <p className="text-xs text-gray-600 italic">&ldquo;{evidence}&rdquo;</p>
                    )}
                  </div>
                );
              }
              // Handle key_barriers structure
              if ('barrier_type' in obj) {
                const severity = obj.severity ? String(obj.severity) : 'moderate';
                const evidence = obj.evidence ? String(obj.evidence) : null;
                const severityConfig = getIntensityConfig(severity);
                return (
                  <div key={idx} className={`${severityConfig.bgColor} rounded-lg p-3 border border-gray-200`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className={`font-medium ${severityConfig.textColor}`}>{String(obj.barrier_type)}</span>
                      {severity && (
                        <span className={`text-xs px-2 py-0.5 rounded-full ${severityConfig.color} text-white`}>
                          {severity}
                        </span>
                      )}
                    </div>
                    {evidence && (
                      <p className="text-xs text-gray-600 italic">&ldquo;{evidence}&rdquo;</p>
                    )}
                  </div>
                );
              }
              // Fallback for other structured objects
              return (
                <div key={idx} className="bg-gray-50 rounded p-2 text-xs">
                  <pre className="overflow-x-auto text-gray-800">{JSON.stringify(obj, null, 2)}</pre>
                </div>
              );
            })}
          </div>
        </div>
      );
    }

    // Simple array of strings
    return (
      <div>
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
          {formattedLabel}
        </div>
        <div className="flex flex-wrap gap-2">
          {value.map((item, idx) => (
            <span
              key={idx}
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700"
            >
              {String(item)}
            </span>
          ))}
        </div>
      </div>
    );
  }

  // Handle objects
  if (typeof value === 'object' && value !== null) {
    return (
      <div>
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
          {formattedLabel}
        </div>
        <pre className="text-xs bg-gray-50 rounded p-2 overflow-x-auto text-gray-800">
          {JSON.stringify(value, null, 2)}
        </pre>
      </div>
    );
  }

  // Default string/number rendering
  return (
    <div>
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
        {formattedLabel}
      </div>
      <div className="text-sm text-gray-800">{String(value ?? 'N/A')}</div>
    </div>
  );
}

// ============================================================================
// Source Badge Helper
// ============================================================================

function getSourceBadge(source: string): { icon: string; label: string; bgColor: string; textColor: string } {
  switch (source?.toLowerCase()) {
    case 'text_only':
      return { icon: '📝', label: 'Text', bgColor: 'bg-blue-100', textColor: 'text-blue-700' };
    case 'audio_only':
      return { icon: '🎙️', label: 'Audio', bgColor: 'bg-green-100', textColor: 'text-green-700' };
    case 'combined':
      return { icon: '🔗', label: 'Combined', bgColor: 'bg-purple-100', textColor: 'text-purple-700' };
    default:
      return { icon: '📄', label: source || 'Unknown', bgColor: 'bg-gray-100', textColor: 'text-gray-700' };
  }
}

// ============================================================================
// Unified Emotions Section Component
// ============================================================================

interface UnifiedEmotionsSectionProps {
  segments: UnifiedEmotionSegment[];
  congruenceSummary?: CongruenceSummary | null;
}

function UnifiedEmotionsSection({ segments, congruenceSummary }: UnifiedEmotionsSectionProps) {
  if (!segments || segments.length === 0) return null;

  return (
    <div className="bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-lg overflow-hidden">
      <div className="bg-gradient-to-r from-indigo-100 to-purple-100 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">💭</span>
          <div>
            <h3 className="font-semibold text-indigo-800">Emotion Analysis</h3>
            <p className="text-xs text-gray-500">Unified analysis from text and/or audio sources</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="bg-indigo-200 text-indigo-800 px-2 py-1 rounded-full text-xs font-medium">
            {segments.length} segment{segments.length !== 1 ? 's' : ''}
          </span>
          {congruenceSummary?.overall_congruence && (
            <CongruenceBadge
              congruence={congruenceSummary.overall_congruence}
              score={congruenceSummary.congruence_score}
            />
          )}
        </div>
      </div>
      <div className="p-4 space-y-3">
        {segments.map((segment, idx) => (
          <UnifiedEmotionCard key={`${segment.segment_code}-${idx}`} segment={segment} />
        ))}
      </div>
    </div>
  );
}

// Congruence Badge Component
function CongruenceBadge({ congruence, score }: { congruence: string; score?: number }) {
  const getColor = (level: string) => {
    switch (level?.toLowerCase()) {
      case 'high': return { bg: 'bg-green-100', text: 'text-green-700' };
      case 'moderate': return { bg: 'bg-yellow-100', text: 'text-yellow-700' };
      case 'low': return { bg: 'bg-red-100', text: 'text-red-700' };
      default: return { bg: 'bg-gray-100', text: 'text-gray-700' };
    }
  };
  const colors = getColor(congruence);
  return (
    <span className={`${colors.bg} ${colors.text} px-2 py-1 rounded-full text-xs font-medium flex items-center gap-1`}>
      🔗 {congruence}
      {score !== undefined && <span className="opacity-75">({Math.round(score * 100)}%)</span>}
    </span>
  );
}

// Anxiety Summary Component - extracts key info from nested objects
function AnxietySummarySection({ segmentValue }: { segmentValue: Record<string, unknown> }) {
  const preConsultation = segmentValue.pre_consultation as Record<string, unknown> | undefined;
  const postConsultation = segmentValue.post_consultation as Record<string, unknown> | undefined;
  const trajectory = segmentValue.trajectory as Record<string, unknown> | undefined;

  const preLevel = preConsultation?.level as string | undefined;
  const postLevel = postConsultation?.level as string | undefined;
  const trajectoryValue = trajectory?.trajectory as string | undefined;
  const textChange = trajectory?.text_change as string | undefined;
  const audioTrajectory = trajectory?.audio_trajectory as string | undefined;

  // Get color based on level
  const getLevelColor = (level: string | undefined) => {
    if (!level) return 'bg-gray-100 text-gray-600';
    const lower = level.toLowerCase();
    if (lower.includes('severe') || lower.includes('high')) return 'bg-red-100 text-red-700';
    if (lower.includes('moderate') || lower.includes('medium')) return 'bg-amber-100 text-amber-700';
    if (lower.includes('mild') || lower.includes('low')) return 'bg-green-100 text-green-700';
    if (lower.includes('none') || lower.includes('minimal')) return 'bg-emerald-100 text-emerald-700';
    return 'bg-gray-100 text-gray-600';
  };

  // Get color based on trajectory
  const getTrajectoryColor = (traj: string | undefined) => {
    if (!traj) return 'bg-gray-100 text-gray-600';
    const lower = traj.toLowerCase();
    if (lower.includes('worsened') || lower.includes('increased')) return 'bg-red-100 text-red-700';
    if (lower.includes('improved') || lower.includes('decreased')) return 'bg-green-100 text-green-700';
    if (lower.includes('stable') || lower.includes('unchanged')) return 'bg-blue-100 text-blue-700';
    return 'bg-gray-100 text-gray-600';
  };

  if (!preLevel && !postLevel && !trajectoryValue) return null;

  return (
    <div className="bg-gradient-to-r from-purple-50 to-indigo-50 rounded-lg p-4 border border-purple-200 mb-4">
      <div className="text-xs font-semibold text-purple-700 uppercase tracking-wide mb-3">
        📊 Anxiety Summary
      </div>
      <div className="grid grid-cols-3 gap-4">
        {/* Pre-Consultation Level */}
        <div className="text-center">
          <div className="text-xs text-gray-500 mb-1">Pre-Consultation</div>
          <span className={`inline-block px-3 py-1.5 rounded-full text-sm font-semibold ${getLevelColor(preLevel)}`}>
            {preLevel || 'N/A'}
          </span>
        </div>

        {/* Trajectory Arrow */}
        <div className="text-center flex flex-col items-center justify-center">
          <div className="text-xs text-gray-500 mb-1">Trajectory</div>
          <span className={`inline-block px-3 py-1.5 rounded-full text-sm font-semibold ${getTrajectoryColor(trajectoryValue)}`}>
            {trajectoryValue === 'Worsened' && '📈 '}
            {trajectoryValue === 'Improved' && '📉 '}
            {trajectoryValue === 'Stable' && '➡️ '}
            {trajectoryValue || 'N/A'}
          </span>
        </div>

        {/* Post-Consultation Level */}
        <div className="text-center">
          <div className="text-xs text-gray-500 mb-1">Post-Consultation</div>
          <span className={`inline-block px-3 py-1.5 rounded-full text-sm font-semibold ${getLevelColor(postLevel)}`}>
            {postLevel || 'N/A'}
          </span>
        </div>
      </div>

      {/* Text vs Audio comparison for trajectory */}
      {(textChange || audioTrajectory) && (
        <div className="mt-3 pt-3 border-t border-purple-200">
          <div className="text-xs text-gray-500 mb-2">Source Comparison</div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-blue-500">📝</span>
              <span className="text-gray-500">Text:</span>
              <span className={`font-medium px-2 py-0.5 rounded ${getTrajectoryColor(textChange)}`}>
                {textChange || 'N/A'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-500">🎙️</span>
              <span className="text-gray-500">Audio:</span>
              <span className={`font-medium px-2 py-0.5 rounded ${getTrajectoryColor(audioTrajectory)}`}>
                {audioTrajectory || 'N/A'}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Unified Emotion Card Component
function UnifiedEmotionCard({ segment }: { segment: UnifiedEmotionSegment }) {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const sourceBadge = getSourceBadge(segment.source);

  // Check if this is an anxiety segment with nested data
  const isAnxietySegment = segment.segment_code === 'ANXIETY_POST_CONSULTATION' && (
    segment.segment_value.pre_consultation !== undefined ||
    segment.segment_value.post_consultation !== undefined ||
    segment.segment_value.trajectory !== undefined
  );

  // Get ordered fields for display
  const getOrderedFields = (segmentCode: string, data: Record<string, unknown>) => {
    // Map unified segment codes to their corresponding field order config
    const codeToOrderKey: Record<string, string> = {
      'ANXIETY_POST_CONSULTATION': 'TEXT_EMOTION_ANXIETY_POST_CONSULTATION',
      'FINANCIAL_CONCERNS': 'TEXT_EMOTION_FINANCIAL_CONCERNS',
      'OTHER_EMOTIONS_DETECTED': 'TEXT_EMOTION_OTHER_EMOTIONS_DETECTED',
      'TREATMENT_COMPLIANCE_LIKELIHOOD': 'TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD',
      'DOCTOR_COMMUNICATION_STYLE': 'TEXT_EMOTION_DOCTOR_COMMUNICATION_STYLE',
    };

    const orderKey = codeToOrderKey[segmentCode] || segmentCode;
    const order = FIELD_ORDER[orderKey] || [];
    const orderedFields: Array<{ key: string; value: unknown }> = [];
    const remainingFields: Array<{ key: string; value: unknown }> = [];

    // Add fields in specified order
    for (const key of order) {
      if (key in data && !EXCLUDED_FIELDS.has(key)) {
        orderedFields.push({ key, value: data[key] });
      }
    }

    // Add any remaining fields not in order (except excluded and metadata)
    const metadataFields = new Set(['text_level', 'audio_level', 'text_severity', 'audio_severity', 'text_likelihood', 'audio_likelihood']);
    for (const key of Object.keys(data)) {
      if (!order.includes(key) && !EXCLUDED_FIELDS.has(key) && !metadataFields.has(key)) {
        remainingFields.push({ key, value: data[key] });
      }
    }

    return [...orderedFields, ...remainingFields];
  };

  const orderedFields = getOrderedFields(segment.segment_code, segment.segment_value);

  // Check if this is a combined source with text/audio comparison data
  const hasCombinedData = segment.source === 'combined' && (
    segment.segment_value.text_level !== undefined ||
    segment.segment_value.audio_level !== undefined ||
    segment.segment_value.text_severity !== undefined ||
    segment.segment_value.audio_severity !== undefined
  );

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm font-medium text-gray-900">
            {segment.segment_name || formatSegmentCode(segment.segment_code)}
          </span>
          {/* Source Badge */}
          <span className={`text-xs px-2 py-0.5 rounded-full ${sourceBadge.bgColor} ${sourceBadge.textColor} flex items-center gap-1`}>
            {sourceBadge.icon} {sourceBadge.label}
          </span>
          {hasCombinedData && (
            <span className="text-xs px-2 py-0.5 rounded bg-amber-100 text-amber-700">
              📊 Compare
            </span>
          )}
        </div>
        <svg
          className={`w-5 h-5 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {isExpanded && (
        <div className="px-4 pb-4 border-t">
          <div className="mt-3 space-y-4">
            {/* Show anxiety summary at top for anxiety segments */}
            {isAnxietySegment && (
              <AnxietySummarySection segmentValue={segment.segment_value} />
            )}
            {/* Show text/audio comparison if combined source */}
            {hasCombinedData && !isAnxietySegment && (
              <SourceComparisonSection segmentValue={segment.segment_value} />
            )}
            {/* Regular field rendering */}
            {orderedFields.map(({ key, value }) => (
              <FieldRenderer key={key} fieldKey={key} value={value} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Source Comparison Section (for combined mode)
function SourceComparisonSection({ segmentValue }: { segmentValue: Record<string, unknown> }) {
  const comparisons: Array<{ label: string; textVal?: string; audioVal?: string }> = [];

  if (segmentValue.text_level !== undefined || segmentValue.audio_level !== undefined) {
    comparisons.push({
      label: 'Level',
      textVal: segmentValue.text_level as string,
      audioVal: segmentValue.audio_level as string,
    });
  }

  if (segmentValue.text_severity !== undefined || segmentValue.audio_severity !== undefined) {
    comparisons.push({
      label: 'Severity',
      textVal: segmentValue.text_severity as string,
      audioVal: segmentValue.audio_severity as string,
    });
  }

  if (segmentValue.text_likelihood !== undefined || segmentValue.audio_likelihood !== undefined) {
    comparisons.push({
      label: 'Likelihood',
      textVal: segmentValue.text_likelihood as string,
      audioVal: segmentValue.audio_likelihood as string,
    });
  }

  if (comparisons.length === 0) return null;

  return (
    <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
        Source Comparison
      </div>
      <div className="space-y-2">
        {comparisons.map(({ label, textVal, audioVal }) => (
          <div key={label} className="grid grid-cols-2 gap-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-blue-500">📝</span>
              <span className="text-gray-500">{label} (Text):</span>
              <span className="font-medium text-gray-900">{textVal || 'N/A'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-500">🎙️</span>
              <span className="text-gray-500">{label} (Audio):</span>
              <span className="font-medium text-gray-900">{audioVal || 'N/A'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Utility Functions
// ============================================================================

function formatSegmentCode(code: string): string {
  return code
    .replace(/^AUDIO_/, '')
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function capitalizeFirst(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

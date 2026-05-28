'use client';

import React, { useState } from 'react';
import { BACKEND_API_URL } from '@lib/config';

// ============================================================================
// Types
// ============================================================================

export interface TriageSuggestion {
  id?: string; // Suggestion ID from triage_suggestion_log (for feedback)
  category: string;
  suggestion: string;
  priority: string;
  rationale: string;
  source: string;
  related_presentation?: string;
}

export interface TriageSuggestionsData {
  loading: boolean;
  error?: string;
  // Success data
  extraction_id?: string;
  specialty?: string;
  consultation_type?: string;
  critical_actions?: TriageSuggestion[];
  important_considerations?: TriageSuggestion[];
  nice_to_have?: TriageSuggestion[];
  matched_presentations?: string[];
  identified_red_flags?: string[];
  gap_analysis?: {
    risk_level?: string;
    risk_factors?: string[];
    differential_considerations?: string[];
    safety_netting?: string;
    critical_suggestions?: Array<{
      type: string;
      suggestion: string;
      urgency: string;
      rationale: string;
    }>;
    additional_suggestions?: Array<{
      type: string;
      suggestion: string;
      rationale: string;
    }>;
  };
  total_suggestions?: number;
  generated_at?: string;
  processing_time_ms?: number;
}

interface TriageSuggestionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: TriageSuggestionsData;
  extractionId?: string | null;
  onRefresh?: () => void;
  doctorId?: string | null; // Doctor ID for submitting feedback
  enableFeedback?: boolean; // Whether to show feedback buttons
}

// Feedback state type
type FeedbackStatus = 'none' | 'accepted' | 'rejected' | 'maybe' | 'modified' | 'submitting';

interface FeedbackState {
  [suggestionId: string]: FeedbackStatus;
}

// ============================================================================
// Priority Configuration
// ============================================================================

interface PriorityConfig {
  bg: string;
  border: string;
  text: string;
  badge: string;
  icon: string;
}

const PRIORITY_CONFIG: Record<string, PriorityConfig> = {
  critical: {
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-800',
    badge: 'bg-red-600 text-white',
    icon: '🚨',
  },
  important: {
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    text: 'text-orange-800',
    badge: 'bg-orange-500 text-white',
    icon: '⚠️',
  },
  consider: {
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    text: 'text-blue-800',
    badge: 'bg-blue-500 text-white',
    icon: '💡',
  },
};

const CATEGORY_ICONS: Record<string, string> = {
  red_flag: '🚩',
  investigation: '🔬',
  history_question: '📋',
  examination: '🩺',
  diagnosis_consider: '🏥',
  referral: '👨‍⚕️',
  follow_up: '📅',
  psychosocial: '💭',
};

// Human-readable labels for categories
const CATEGORY_LABELS: Record<string, string> = {
  red_flag: 'Red Flag',
  investigation: 'Investigation',
  history_question: 'History',
  examination: 'Examination',
  diagnosis_consider: 'Diagnosis',
  referral: 'Referral',
  follow_up: 'Follow-up',
  psychosocial: 'Psychosocial',
};

// Category colors for prominent display
const CATEGORY_COLORS: Record<string, string> = {
  red_flag: 'bg-red-100 text-red-800 border-red-200',
  investigation: 'bg-blue-100 text-blue-800 border-blue-200',
  history_question: 'bg-purple-100 text-purple-800 border-purple-200',
  examination: 'bg-teal-100 text-teal-800 border-teal-200',
  diagnosis_consider: 'bg-indigo-100 text-indigo-800 border-indigo-200',
  referral: 'bg-orange-100 text-orange-800 border-orange-200',
  follow_up: 'bg-green-100 text-green-800 border-green-200',
  psychosocial: 'bg-pink-100 text-pink-800 border-pink-200',
};

// Source layer labels and colors
const SOURCE_LABELS: Record<string, string> = {
  differential_tree_cache: 'Unizy',
  differential_tree: 'Unizy',
  rag_clinical_conditions: 'STG',
  rag_comorbidity_pathway: 'STG',
  rag_drug_check: 'STG',
  gemini_analysis: 'Med LLM',
  patient_context: 'History',
  red_flag_match: 'Red Flag',
};

const SOURCE_COLORS: Record<string, string> = {
  differential_tree_cache: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  differential_tree: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  rag_clinical_conditions: 'bg-amber-50 text-amber-700 border-amber-200',
  rag_comorbidity_pathway: 'bg-amber-50 text-amber-700 border-amber-200',
  rag_drug_check: 'bg-amber-50 text-amber-700 border-amber-200',
  gemini_analysis: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  patient_context: 'bg-violet-50 text-violet-700 border-violet-200',
  red_flag_match: 'bg-red-50 text-red-700 border-red-200',
};

// ============================================================================
// Risk Level Configuration
// ============================================================================

const RISK_LEVEL_CONFIG: Record<string, { bg: string; text: string; border: string }> = {
  low: { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-300' },
  moderate: { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300' },
  high: { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-300' },
  critical: { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300' },
};

// ============================================================================
// Main Component
// ============================================================================

export function TriageSuggestionsModal({
  isOpen,
  onClose,
  data,
  extractionId,
  onRefresh,
  doctorId,
  enableFeedback = false
}: TriageSuggestionsModalProps) {
  const [feedbackState, setFeedbackState] = useState<FeedbackState>({});

  // Submit feedback to API
  const submitFeedback = async (
    suggestionId: string,
    feedbackType: 'accepted' | 'rejected' | 'maybe' | 'modified',
    rejectionReason?: string,
    modifiedText?: string
  ) => {
    if (!doctorId || !suggestionId) return;

    setFeedbackState(prev => ({ ...prev, [suggestionId]: 'submitting' }));

    try {
      const response = await fetch(`${BACKEND_API_URL}/api/v1/triage/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          suggestion_id: suggestionId,
          doctor_id: doctorId,
          feedback_type: feedbackType,
          rejection_reason: rejectionReason,
          modified_text: modifiedText,
        }),
      });

      if (response.ok) {
        setFeedbackState(prev => ({ ...prev, [suggestionId]: feedbackType }));
      } else {
        console.error('Failed to submit feedback');
        setFeedbackState(prev => ({ ...prev, [suggestionId]: 'none' }));
      }
    } catch (error) {
      console.error('Error submitting feedback:', error);
      setFeedbackState(prev => ({ ...prev, [suggestionId]: 'none' }));
    }
  };

  if (!isOpen) return null;

  const hasCritical = data.critical_actions && data.critical_actions.length > 0;
  const hasImportant = data.important_considerations && data.important_considerations.length > 0;
  const hasNiceToHave = data.nice_to_have && data.nice_to_have.length > 0;
  const hasAnyData = hasCritical || hasImportant || hasNiceToHave;
  const hasRedFlags = data.identified_red_flags && data.identified_red_flags.length > 0;
  const hasGapAnalysis = data.gap_analysis && Object.keys(data.gap_analysis).length > 0;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="bg-gradient-to-r from-teal-200 to-cyan-200 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white bg-opacity-50 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-gray-800" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Clinical Triage Suggestions</h2>
              <div className="flex items-center gap-2 text-gray-700 text-xs">
                {data.specialty && (
                  <span className="bg-teal-600 text-white px-2 py-0.5 rounded">
                    {data.specialty}
                  </span>
                )}
                {extractionId && (
                  <span className="font-mono text-gray-600">ID: {extractionId.slice(0, 8)}...</span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-700 hover:bg-white hover:bg-opacity-50 rounded-full p-2 transition-colors"
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
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-teal-600"></div>
              <p className="mt-4 text-gray-600">Generating triage suggestions...</p>
              <p className="text-sm text-gray-400 mt-1">This may take a few seconds</p>
            </div>
          ) : data.error ? (
            // Show as warning (amber) if triage is disabled, otherwise show as error (red)
            data.error.includes('not enabled') ? (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-center">
                <svg className="w-12 h-12 text-amber-500 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <p className="text-amber-700 font-medium">{data.error}</p>
              </div>
            ) : (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
                <svg className="w-12 h-12 text-red-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-red-700 font-medium">{data.error}</p>
              </div>
            )
          ) : !hasAnyData ? (
            <div className="bg-green-50 border border-green-200 rounded-lg p-8 text-center">
              <svg className="w-16 h-16 text-green-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-green-700 font-medium">No additional suggestions</p>
              <p className="text-green-600 text-sm mt-1">
                The consultation appears comprehensive for the presented complaints.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Risk Level & Matched Presentations */}
              {(hasGapAnalysis || data.matched_presentations?.length) && (
                <div className="grid grid-cols-2 gap-4">
                  {/* Risk Level */}
                  {data.gap_analysis?.risk_level && (
                    <div className={`rounded-lg p-4 border ${RISK_LEVEL_CONFIG[data.gap_analysis.risk_level]?.bg || 'bg-gray-100'} ${RISK_LEVEL_CONFIG[data.gap_analysis.risk_level]?.border || 'border-gray-300'}`}>
                      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                        Risk Level
                      </div>
                      <div className={`text-xl font-bold capitalize ${RISK_LEVEL_CONFIG[data.gap_analysis.risk_level]?.text || 'text-gray-800'}`}>
                        {data.gap_analysis.risk_level}
                      </div>
                    </div>
                  )}

                  {/* Matched Presentations */}
                  {data.matched_presentations && data.matched_presentations.length > 0 && (
                    <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                        Matched Presentations
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {data.matched_presentations.map((pres, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-teal-100 text-teal-800"
                          >
                            {pres.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Red Flags Alert */}
              {hasRedFlags && (
                <div className="bg-red-50 border-2 border-red-300 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-2xl">🚩</span>
                    <h3 className="font-bold text-red-800">Identified Red Flags</h3>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {data.identified_red_flags!.map((flag, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-semibold bg-red-200 text-red-900"
                      >
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* All Suggestions - Combined View with Top 3 initially */}
              <CombinedSuggestionsView
                criticalActions={data.critical_actions || []}
                importantConsiderations={data.important_considerations || []}
                niceToHave={data.nice_to_have || []}
                enableFeedback={enableFeedback && !!doctorId}
                feedbackState={feedbackState}
                onFeedback={submitFeedback}
              />

              {/* Differential Considerations */}
              {data.gap_analysis?.differential_considerations && data.gap_analysis.differential_considerations.length > 0 && (
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-xl">🔍</span>
                    <h3 className="font-semibold text-purple-800">Differential Diagnoses to Consider</h3>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {data.gap_analysis.differential_considerations.map((dx, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800"
                      >
                        {dx}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Safety Netting */}
              {data.gap_analysis?.safety_netting && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">🛡️</span>
                    <h3 className="font-semibold text-amber-800">Safety Netting Advice</h3>
                  </div>
                  <p className="text-sm text-amber-900">{data.gap_analysis.safety_netting}</p>
                </div>
              )}

              {/* Stats */}
              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                <div className="grid grid-cols-4 gap-4 text-center">
                  <div>
                    <div className="text-2xl font-bold text-gray-800">{data.total_suggestions || 0}</div>
                    <div className="text-xs text-gray-500">Total Suggestions</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-red-600">{data.critical_actions?.length || 0}</div>
                    <div className="text-xs text-gray-500">Critical</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-orange-600">{data.important_considerations?.length || 0}</div>
                    <div className="text-xs text-gray-500">Important</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-blue-600">{data.nice_to_have?.length || 0}</div>
                    <div className="text-xs text-gray-500">Consider</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-gray-50 px-6 py-4 border-t flex justify-end items-center">
          {/* Buttons */}
          <div className="flex gap-3">
            {onRefresh && (
              <button
                onClick={onRefresh}
                disabled={data.loading}
                className="px-4 py-2 bg-teal-100 hover:bg-teal-200 text-teal-700 rounded-lg transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
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
// Combined Suggestions View - Shows Top 3 Initially
// ============================================================================

interface CombinedSuggestionsViewProps {
  criticalActions: TriageSuggestion[];
  importantConsiderations: TriageSuggestion[];
  niceToHave: TriageSuggestion[];
  enableFeedback?: boolean;
  feedbackState?: FeedbackState;
  onFeedback?: (
    suggestionId: string,
    feedbackType: 'accepted' | 'rejected' | 'maybe' | 'modified',
    rejectionReason?: string,
    modifiedText?: string
  ) => void;
}

interface TaggedSuggestion extends TriageSuggestion {
  priorityLevel: 'critical' | 'important' | 'consider';
}

function CombinedSuggestionsView({
  criticalActions,
  importantConsiderations,
  niceToHave,
  enableFeedback,
  feedbackState,
  onFeedback
}: CombinedSuggestionsViewProps) {
  const [showAll, setShowAll] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const INITIAL_DISPLAY_COUNT = 3;

  // Combine all suggestions with their priority level and generate stable keys
  const allSuggestions: (TaggedSuggestion & { stableKey: string })[] = [
    ...criticalActions.map((s, i) => ({ ...s, priorityLevel: 'critical' as const, stableKey: s.id || `critical-${i}` })),
    ...importantConsiderations.map((s, i) => ({ ...s, priorityLevel: 'important' as const, stableKey: s.id || `important-${i}` })),
    ...niceToHave.map((s, i) => ({ ...s, priorityLevel: 'consider' as const, stableKey: s.id || `consider-${i}` })),
  ];

  const totalCount = allSuggestions.length;
  const displayedSuggestions = showAll ? allSuggestions : allSuggestions.slice(0, INITIAL_DISPLAY_COUNT);
  const hiddenCount = totalCount - INITIAL_DISPLAY_COUNT;

  const toggleExpanded = (key: string) => {
    setExpandedItems(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  if (totalCount === 0) return null;

  // Priority level labels and colors
  const getPriorityBadge = (level: 'critical' | 'important' | 'consider') => {
    switch (level) {
      case 'critical':
        return <span className="px-1.5 py-0.5 bg-red-100 text-red-700 text-[10px] font-semibold rounded">CRITICAL</span>;
      case 'important':
        return <span className="px-1.5 py-0.5 bg-orange-100 text-orange-700 text-[10px] font-semibold rounded">IMPORTANT</span>;
      case 'consider':
        return <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-[10px] font-semibold rounded">CONSIDER</span>;
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">📋</span>
          <div>
            <h3 className="font-semibold text-gray-800">Triage Suggestions</h3>
            <p className="text-xs text-gray-500">Prioritized recommendations</p>
          </div>
        </div>
        <span className="bg-gray-200 text-gray-700 px-2 py-1 rounded-full text-xs font-medium">
          {totalCount} total
        </span>
      </div>

      <div className="p-4 space-y-3">
        {displayedSuggestions.map((suggestion) => {
          const isExpanded = expandedItems.has(suggestion.stableKey);
          const feedbackKey = suggestion.id || suggestion.stableKey;
          const currentFeedback = feedbackState?.[feedbackKey];
          const hasFeedback = currentFeedback && currentFeedback !== 'none';

          return (
            <div key={suggestion.stableKey} className="bg-gray-50 rounded-lg border border-gray-100 overflow-hidden">
              {/* Main row - clickable to expand */}
              <div className="p-3">
                <div className="flex items-start gap-3">
                  {/* Category badge */}
                  <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-md border text-xs font-semibold flex-shrink-0 ${CATEGORY_COLORS[suggestion.category] || 'bg-gray-100 text-gray-800 border-gray-200'}`}>
                    <span>{CATEGORY_ICONS[suggestion.category] || '•'}</span>
                    <span>{CATEGORY_LABELS[suggestion.category] || suggestion.category}</span>
                  </span>

                  {/* Suggestion content - clickable */}
                  <button
                    onClick={() => toggleExpanded(suggestion.stableKey)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {getPriorityBadge(suggestion.priorityLevel)}
                      {/* Source layer badge */}
                      {suggestion.source && (
                        <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded border ${SOURCE_COLORS[suggestion.source] || 'bg-gray-50 text-gray-600 border-gray-200'}`}>
                          {SOURCE_LABELS[suggestion.source] || suggestion.source}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-900">{suggestion.suggestion}</p>
                  </button>

                  {/* Expand/collapse icon */}
                  <button
                    onClick={() => toggleExpanded(suggestion.stableKey)}
                    className="flex-shrink-0 p-1 hover:bg-gray-200 rounded transition-colors"
                  >
                    <svg
                      className={`w-5 h-5 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>

                {/* Feedback buttons - always in main row */}
                {enableFeedback && (
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-200">
                    <span className="text-xs text-gray-500 mr-2">Feedback:</span>
                    {hasFeedback ? (
                      <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                        currentFeedback === 'accepted' ? 'bg-green-100 text-green-700' :
                        currentFeedback === 'rejected' ? 'bg-red-100 text-red-700' :
                        currentFeedback === 'maybe' ? 'bg-amber-100 text-amber-700' :
                        currentFeedback === 'submitting' ? 'bg-gray-100 text-gray-500 animate-pulse' :
                        'bg-blue-100 text-blue-700'
                      }`}>
                        {currentFeedback === 'accepted' ? '✓ Accepted' :
                         currentFeedback === 'rejected' ? '✗ Declined' :
                         currentFeedback === 'maybe' ? '? Maybe' :
                         currentFeedback === 'submitting' ? 'Saving...' :
                         '✎ Modified'}
                      </span>
                    ) : (
                      <>
                        <button
                          onClick={() => suggestion.id && onFeedback?.(suggestion.id, 'accepted')}
                          disabled={!suggestion.id}
                          className="px-3 py-1 rounded-md bg-green-50 hover:bg-green-100 text-green-700 text-xs font-medium transition-colors border border-green-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => suggestion.id && onFeedback?.(suggestion.id, 'maybe')}
                          disabled={!suggestion.id}
                          className="px-3 py-1 rounded-md bg-amber-50 hover:bg-amber-100 text-amber-700 text-xs font-medium transition-colors border border-amber-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Maybe
                        </button>
                        <button
                          onClick={() => suggestion.id && onFeedback?.(suggestion.id, 'rejected')}
                          disabled={!suggestion.id}
                          className="px-3 py-1 rounded-md bg-red-50 hover:bg-red-100 text-red-700 text-xs font-medium transition-colors border border-red-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Decline
                        </button>
                        {!suggestion.id && (
                          <span className="text-xs text-gray-400 ml-2">(ID not available)</span>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Expanded rationale section */}
              {isExpanded && suggestion.rationale && (
                <div className="px-4 pb-4 border-t border-gray-200 bg-white">
                  <div className="mt-3">
                    <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1 flex items-center gap-1">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Why this suggestion?
                    </div>
                    <p className="text-sm text-gray-700">{suggestion.rationale}</p>
                  </div>
                  {suggestion.related_presentation && (
                    <div className="mt-3">
                      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                        Related Presentation
                      </div>
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-teal-100 text-teal-800">
                        {suggestion.related_presentation.replace(/_/g, ' ')}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {/* Show more/less button */}
        {hiddenCount > 0 && (
          <button
            onClick={() => setShowAll(!showAll)}
            className="w-full py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {showAll ? (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                </svg>
                Show less
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
                Show {hiddenCount} more suggestion{hiddenCount !== 1 ? 's' : ''}
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Suggestion Section Component (kept for potential future use)
// ============================================================================

interface SuggestionSectionProps {
  title: string;
  description: string;
  suggestions: TriageSuggestion[];
  priority: 'critical' | 'important' | 'consider';
  icon: string;
  enableFeedback?: boolean;
  feedbackState?: FeedbackState;
  onFeedback?: (
    suggestionId: string,
    feedbackType: 'accepted' | 'rejected' | 'maybe' | 'modified',
    rejectionReason?: string,
    modifiedText?: string
  ) => void;
}

function SuggestionSection({
  title,
  description,
  suggestions,
  priority,
  icon,
  enableFeedback,
  feedbackState,
  onFeedback
}: SuggestionSectionProps) {
  const [showAll, setShowAll] = useState(false);
  const config = PRIORITY_CONFIG[priority];

  // Show only top 3 unless expanded
  const INITIAL_DISPLAY_COUNT = 3;
  const hasMore = suggestions.length > INITIAL_DISPLAY_COUNT;
  const displayedSuggestions = showAll ? suggestions : suggestions.slice(0, INITIAL_DISPLAY_COUNT);
  const hiddenCount = suggestions.length - INITIAL_DISPLAY_COUNT;

  return (
    <div className={`${config.bg} ${config.border} border rounded-lg overflow-hidden`}>
      <div className={`px-4 py-3 flex items-center justify-between ${config.bg}`}>
        <div className="flex items-center gap-2">
          <span className="text-xl">{icon}</span>
          <div>
            <h3 className={`font-semibold ${config.text}`}>{title}</h3>
            <p className="text-xs text-gray-500">{description}</p>
          </div>
        </div>
        <span className={`${config.badge} px-2 py-1 rounded-full text-xs font-medium`}>
          {suggestions.length} item{suggestions.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="p-4 space-y-3 bg-white bg-opacity-50">
        {displayedSuggestions.map((suggestion, idx) => (
          <SuggestionCard
            key={suggestion.id || idx}
            suggestion={suggestion}
            priority={priority}
            enableFeedback={enableFeedback}
            feedbackStatus={feedbackState?.[suggestion.id || ''] || 'none'}
            onFeedback={onFeedback}
          />
        ))}

        {/* Show more/less button */}
        {hasMore && (
          <button
            onClick={() => setShowAll(!showAll)}
            className={`w-full py-2 text-sm font-medium ${config.text} hover:bg-white hover:bg-opacity-50 rounded-lg transition-colors flex items-center justify-center gap-2`}
          >
            {showAll ? (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                </svg>
                Show less
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
                Show {hiddenCount} more suggestion{hiddenCount !== 1 ? 's' : ''}
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Suggestion Card Component
// ============================================================================

interface SuggestionCardProps {
  suggestion: TriageSuggestion;
  priority: 'critical' | 'important' | 'consider';
  enableFeedback?: boolean;
  feedbackStatus?: FeedbackStatus;
  onFeedback?: (
    suggestionId: string,
    feedbackType: 'accepted' | 'rejected' | 'maybe' | 'modified',
    rejectionReason?: string,
    modifiedText?: string
  ) => void;
}

function SuggestionCard({
  suggestion,
  priority,
  enableFeedback,
  feedbackStatus = 'none',
  onFeedback
}: SuggestionCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const config = PRIORITY_CONFIG[priority];
  const categoryIcon = CATEGORY_ICONS[suggestion.category] || '•';
  const categoryLabel = CATEGORY_LABELS[suggestion.category] || suggestion.category.replace(/_/g, ' ');
  const categoryColor = CATEGORY_COLORS[suggestion.category] || 'bg-gray-100 text-gray-800 border-gray-200';

  const handleFeedback = (type: 'accepted' | 'rejected' | 'maybe') => {
    if (onFeedback && suggestion.id) {
      onFeedback(suggestion.id, type);
    }
  };

  const getFeedbackIndicator = () => {
    switch (feedbackStatus) {
      case 'accepted':
        return <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs font-medium rounded-full">✓ Accepted</span>;
      case 'rejected':
        return <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-medium rounded-full">✗ Declined</span>;
      case 'maybe':
        return <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-medium rounded-full">? Maybe</span>;
      case 'modified':
        return <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-medium rounded-full">✎ Modified</span>;
      case 'submitting':
        return <span className="px-2 py-0.5 bg-gray-100 text-gray-500 text-xs animate-pulse rounded-full">Saving...</span>;
      default:
        return null;
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden group">
      <div className="w-full px-4 py-3 flex items-start justify-between hover:bg-gray-50 transition-colors text-left">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-start gap-3 flex-1"
        >
          {/* Prominent category badge */}
          <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-md border text-xs font-semibold flex-shrink-0 ${categoryColor}`}>
            <span>{categoryIcon}</span>
            <span>{categoryLabel}</span>
          </span>
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium text-gray-900">
              {suggestion.suggestion}
            </span>
            {/* Source layer badge */}
            {suggestion.source && (
              <span className={`ml-2 px-1.5 py-0.5 text-[10px] font-medium rounded border ${SOURCE_COLORS[suggestion.source] || 'bg-gray-50 text-gray-600 border-gray-200'}`}>
                {SOURCE_LABELS[suggestion.source] || suggestion.source}
              </span>
            )}
          </div>
        </button>

        {/* Feedback area */}
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          {/* Show feedback status if already provided */}
          {getFeedbackIndicator()}

          {/* Show feedback buttons if enabled and not already submitted */}
          {enableFeedback && suggestion.id && feedbackStatus === 'none' && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => handleFeedback('accepted')}
                className="px-2 py-1 rounded-md bg-green-50 hover:bg-green-100 text-green-700 text-xs font-medium transition-colors border border-green-200"
                title="Accept this suggestion"
              >
                Accept
              </button>
              <button
                onClick={() => handleFeedback('maybe')}
                className="px-2 py-1 rounded-md bg-amber-50 hover:bg-amber-100 text-amber-700 text-xs font-medium transition-colors border border-amber-200"
                title="Maybe - consider later"
              >
                Maybe
              </button>
              <button
                onClick={() => handleFeedback('rejected')}
                className="px-2 py-1 rounded-md bg-red-50 hover:bg-red-100 text-red-700 text-xs font-medium transition-colors border border-red-200"
                title="Decline this suggestion"
              >
                Decline
              </button>
            </div>
          )}

          {/* Expand/collapse button */}
          <button onClick={() => setIsExpanded(!isExpanded)}>
            <svg
              className={`w-5 h-5 text-gray-400 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      {isExpanded && suggestion.rationale && (
        <div className="px-4 pb-4 border-t border-gray-100">
          <div className="mt-3">
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">
              Rationale
            </div>
            <p className="text-sm text-gray-600">{suggestion.rationale}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default TriageSuggestionsModal;

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import DoctorSelector from './DoctorSelector';
import { useAuth } from '@lib/auth';
import {
  searchPatients,
  getConsultationHistory,
  getPatientPrescreen,
  getExtractionDetails,
  type PatientSearchResult,
  type ConsultationHistoryItem,
  type EmotionSummary,
  type InterventionSummary,
  type ExtractionMetadata,
  type ClinicalTimelineResponse,
  type TimelineChange,
  type EmotionPatternSummary,
  type EmotionPatternItem,
  type PrescreenResponse,
  type ExtractionDetailsResponse,
} from '@lib/patientHistoryApi';

// ============================================================================
// Helper Functions
// ============================================================================

function getSegmentIcon(segmentCode: string): string {
  const code = segmentCode.toLowerCase();
  if (code.includes('prescription') || code.includes('medicine')) return '💊';
  if (code.includes('diagnosis') || code.includes('dx')) return '🩺';
  if (code.includes('complaint') || code.includes('chief')) return '📝';
  if (code.includes('examination') || code.includes('exam') || code.includes('vitals')) return '🔬';
  if (code.includes('investigation') || code.includes('lab') || code.includes('test')) return '🧪';
  if (code.includes('history') || code.includes('past')) return '📚';
  if (code.includes('treatment') || code.includes('plan')) return '📋';
  if (code.includes('follow') || code.includes('advice')) return '📅';
  if (code.includes('emotion') || code.includes('anxiety')) return '💭';
  if (code.includes('caution') || code.includes('warning') || code.includes('allergy')) return '⚠️';
  if (code.includes('summary')) return '📊';
  if (code.includes('intervention')) return '💡';
  if (code.includes('congruence')) return '🔄';
  if (code.includes('compliance')) return '✅';
  if (code.includes('financial')) return '💰';
  if (code.includes('doctor_style') || code.includes('audio_doctor')) return '🎙️';
  return '📄';
}

// Segment priority: lower number = show first (clinical), higher = show later (emotional/analysis)
function getSegmentPriority(segmentCode: string): number {
  const code = segmentCode.toLowerCase();

  // Clinical segments (priority 1-10)
  if (code.includes('chief') || code.includes('complaint')) return 1;
  if (code.includes('diagnosis') || code === 'dx') return 2;
  if (code.includes('history') || code.includes('past')) return 3;
  if (code.includes('examination') || code.includes('exam') || code.includes('vitals')) return 4;
  if (code.includes('investigation') || code.includes('lab') || code.includes('test')) return 5;
  if (code.includes('prescription') || code.includes('medicine') || code.includes('medication')) return 6;
  if (code.includes('treatment') || code.includes('plan')) return 7;
  if (code.includes('follow') || code.includes('advice')) return 8;
  if (code.includes('summary') && !code.includes('emotion')) return 9;
  if (code.includes('caution') || code.includes('warning') || code.includes('allergy')) return 10;

  // Emotional/analysis segments (priority 20-30)
  if (code.includes('anxiety_pre')) return 20;
  if (code.includes('anxiety_post')) return 21;
  if (code.includes('anxiety')) return 22;
  if (code.includes('other_emotion') || code === 'emotions') return 23;
  if (code.includes('financial')) return 24;
  if (code.includes('compliance')) return 25;
  if (code.includes('congruence')) return 26;
  if (code.includes('doctor_style') || code.includes('audio_doctor')) return 27;
  if (code.includes('intervention')) return 28;

  // Unknown segments go in the middle
  return 15;
}

// ============================================================================
// Sub-components
// ============================================================================

interface SectionCardProps {
  title: string;
  icon: string;
  metadata?: ExtractionMetadata | null;
  children: React.ReactNode;
  isExpanded?: boolean;
  onToggle?: () => void;
  isEmpty?: boolean;
}

function SectionCard({ title, icon, metadata, children, isExpanded = true, onToggle, isEmpty = false }: SectionCardProps) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">{icon}</span>
          <h3 className="font-semibold text-gray-900">{title}</h3>
          {isEmpty && (
            <span className="text-xs px-2 py-0.5 bg-gray-200 text-gray-600 rounded">No data</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {metadata && (
            <span className="text-xs text-gray-500">
              {new Date(metadata.created_at).toLocaleDateString()}
              {metadata.doctor_name && ` - ${metadata.doctor_name}`}
            </span>
          )}
          <svg
            className={`w-5 h-5 text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>
      {isExpanded && (
        <div className="p-4">
          {isEmpty ? (
            <p className="text-gray-500 text-sm italic">No data available for this section.</p>
          ) : (
            children
          )}
        </div>
      )}
    </div>
  );
}

interface DataDisplayProps {
  data: any;
  depth?: number;
}

function DataDisplay({ data, depth = 0 }: DataDisplayProps) {
  if (data === null || data === undefined || data === 'N/A' || data === '') {
    return <span className="text-gray-400 italic">Not available</span>;
  }

  if (typeof data === 'string') {
    return <span className="text-gray-800">{data}</span>;
  }

  if (typeof data === 'number' || typeof data === 'boolean') {
    return <span className="text-gray-800">{String(data)}</span>;
  }

  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <span className="text-gray-400 italic">None</span>;
    }

    // Check if it's an array of simple values
    if (data.every(item => typeof item === 'string' || typeof item === 'number')) {
      return (
        <ul className="list-disc list-inside space-y-1">
          {data.map((item, index) => (
            <li key={index} className="text-gray-800">{String(item)}</li>
          ))}
        </ul>
      );
    }

    // Array of objects
    return (
      <div className="space-y-3">
        {data.map((item, index) => (
          <div key={index} className={`${depth > 0 ? 'ml-4' : ''} p-3 bg-gray-50 rounded-lg`}>
            <DataDisplay data={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  if (typeof data === 'object') {
    const entries = Object.entries(data).filter(([_, value]) =>
      value !== null && value !== undefined && value !== 'N/A' && value !== ''
    );

    if (entries.length === 0) {
      return <span className="text-gray-400 italic">No data</span>;
    }

    return (
      <div className={`space-y-2 ${depth > 0 ? 'ml-4' : ''}`}>
        {entries.map(([key, value]) => (
          <div key={key} className="flex flex-col">
            <span className="text-sm font-medium text-gray-600 capitalize">
              {key.replace(/([A-Z])/g, ' $1').replace(/_/g, ' ').trim()}:
            </span>
            <div className="mt-1">
              <DataDisplay data={value} depth={depth + 1} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return <span className="text-gray-800">{String(data)}</span>;
}

interface PrescriptionDisplayProps {
  prescription: any;
}

function PrescriptionDisplay({ prescription }: PrescriptionDisplayProps) {
  // Handle different prescription formats
  if (Array.isArray(prescription)) {
    return (
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Medicine</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Dosage</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Duration</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Remarks</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {prescription.map((med: any, index: number) => (
              <tr key={index}>
                <td className="px-4 py-2 text-sm text-gray-900">{med.name || med.medicine || '-'}</td>
                <td className="px-4 py-2 text-sm text-gray-600">{med.dosage || med.dose || '-'}</td>
                <td className="px-4 py-2 text-sm text-gray-600">{med.durationDays || med.duration || '-'}</td>
                <td className="px-4 py-2 text-sm text-gray-500">{med.remarks || med.notes || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // Handle object format with nested prescription array
  if (prescription && typeof prescription === 'object') {
    if (prescription.prescription && Array.isArray(prescription.prescription)) {
      return <PrescriptionDisplay prescription={prescription.prescription} />;
    }
    // Treatment plan format
    if (prescription.prescription || prescription.medications) {
      return <PrescriptionDisplay prescription={prescription.prescription || prescription.medications} />;
    }
  }

  return <DataDisplay data={prescription} />;
}

interface DiagnosisDisplayProps {
  diagnosis: any;
}

function DiagnosisDisplay({ diagnosis }: DiagnosisDisplayProps) {
  if (Array.isArray(diagnosis)) {
    return (
      <div className="space-y-2">
        {diagnosis.map((dx: any, index: number) => (
          <div key={index} className="flex items-start gap-2 p-2 bg-blue-50 rounded">
            <span className={`px-2 py-0.5 text-xs rounded ${
              dx.type === 'Primary' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'
            }`}>
              {dx.type || (index === 0 ? 'Primary' : 'Secondary')}
            </span>
            <div>
              <p className="font-medium text-gray-900">{dx.name || dx.diagnosis || dx}</p>
              {dx.code && <p className="text-xs text-gray-500">ICD: {dx.code}</p>}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (typeof diagnosis === 'string') {
    return <p className="text-gray-900">{diagnosis}</p>;
  }

  return <DataDisplay data={diagnosis} />;
}

interface InterventionDisplayProps {
  interventions: InterventionSummary[];
}

function InterventionDisplay({ interventions }: InterventionDisplayProps) {
  const sortedInterventions = [...interventions].sort((a, b) => b.priority_score - a.priority_score);

  return (
    <div className="space-y-3">
      {sortedInterventions.map((intervention) => (
        <div
          key={intervention.id}
          className={`p-3 rounded-lg border ${
            intervention.is_top_3 ? 'border-orange-300 bg-orange-50' : 'border-gray-200 bg-gray-50'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              {intervention.is_top_3 && (
                <span className="px-2 py-0.5 text-xs bg-orange-500 text-white rounded">Priority</span>
              )}
              <span className={`px-2 py-0.5 text-xs rounded ${
                intervention.priority === 'high' ? 'bg-red-100 text-red-700' :
                intervention.priority === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                'bg-green-100 text-green-700'
              }`}>
                {intervention.priority}
              </span>
              <span className="px-2 py-0.5 text-xs bg-gray-200 text-gray-600 rounded">
                {intervention.category}
              </span>
            </div>
            <span className="text-xs text-gray-500">Score: {intervention.priority_score}</span>
          </div>
          <h4 className="font-medium text-gray-900 mt-2">{intervention.name}</h4>
          <p className="text-sm text-gray-600 mt-1">{intervention.description}</p>
          {intervention.trigger_reason && (
            <p className="text-xs text-gray-500 mt-2 italic">Reason: {intervention.trigger_reason}</p>
          )}
        </div>
      ))}
    </div>
  );
}

interface EmotionDisplayProps {
  emotionSummary: EmotionSummary;
}

function EmotionDisplay({ emotionSummary }: EmotionDisplayProps) {
  const sections = [
    { key: 'anxiety_pre_consultation', label: 'Pre-Consultation Anxiety', icon: '😰' },
    { key: 'anxiety_post_consultation', label: 'Post-Consultation Anxiety', icon: '😌' },
    { key: 'audio_anxiety', label: 'Voice Analysis', icon: '🎤' },
    { key: 'other_emotions', label: 'Other Emotions', icon: '🎭' },
    { key: 'financial_concerns', label: 'Financial Concerns', icon: '💰' },
    { key: 'compliance_likelihood', label: 'Treatment Compliance', icon: '📋' },
    { key: 'congruence_analysis', label: 'Text-Audio Congruence', icon: '🔄' },
  ];

  const hasAnyData = sections.some(s => emotionSummary[s.key as keyof EmotionSummary]);

  if (!hasAnyData) {
    return <p className="text-gray-500 italic">No emotion analysis data available.</p>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {sections.map(({ key, label, icon }) => {
        const data = emotionSummary[key as keyof EmotionSummary];
        if (!data) return null;

        return (
          <div key={key} className="p-3 bg-purple-50 rounded-lg border border-purple-200">
            <div className="flex items-center gap-2 mb-2">
              <span>{icon}</span>
              <h4 className="font-medium text-purple-900">{label}</h4>
            </div>
            <DataDisplay data={data} />
          </div>
        );
      })}
    </div>
  );
}

// ============================================================================
// Emotion Pattern Summary Components (for Summary view)
// ============================================================================

interface EmotionPatternSummaryDisplayProps {
  patternSummary: EmotionPatternSummary;
}

function EmotionPatternSummaryDisplay({ patternSummary }: EmotionPatternSummaryDisplayProps) {
  if (!patternSummary.has_emotion_data || patternSummary.patterns.length === 0) {
    return (
      <p className="text-gray-500 text-sm italic">
        No emotion analysis data from recent consultations.
      </p>
    );
  }

  const getTrendIcon = (trend: string | null) => {
    switch (trend) {
      case 'improving': return <span className="text-green-600">↗</span>;
      case 'worsening': return <span className="text-red-600">↘</span>;
      case 'stable': return <span className="text-gray-500">→</span>;
      default: return null;
    }
  };

  const getTrendLabel = (trend: string | null) => {
    switch (trend) {
      case 'improving': return 'Improving';
      case 'worsening': return 'Worsening';
      case 'stable': return 'Stable';
      default: return '';
    }
  };

  const getValueColor = (label: string, value: string) => {
    const valueLower = value.toLowerCase();
    // For anxiety and concerns: High = bad (red), Low = good (green)
    if (label.includes('Anxiety') || label.includes('Concerns')) {
      if (valueLower.includes('high') || valueLower.includes('severe')) return 'text-red-700 bg-red-50';
      if (valueLower.includes('moderate') || valueLower.includes('medium')) return 'text-yellow-700 bg-yellow-50';
      if (valueLower.includes('low') || valueLower.includes('mild') || valueLower.includes('none')) return 'text-green-700 bg-green-50';
    }
    // For compliance: High = good (green), Low = bad (red)
    if (label.includes('Compliance')) {
      if (valueLower.includes('high') || valueLower.includes('likely')) return 'text-green-700 bg-green-50';
      if (valueLower.includes('moderate') || valueLower.includes('medium')) return 'text-yellow-700 bg-yellow-50';
      if (valueLower.includes('low') || valueLower.includes('unlikely')) return 'text-red-700 bg-red-50';
    }
    return 'text-gray-700 bg-gray-50';
  };

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500 mb-2">
        Based on last {patternSummary.visits_analyzed} consultation{patternSummary.visits_analyzed !== 1 ? 's' : ''}
      </p>
      <div className="space-y-2">
        {patternSummary.patterns.map((pattern, idx) => (
          <div
            key={idx}
            className="flex items-center justify-between p-2 rounded-lg border border-gray-100"
          >
            <span className="text-sm text-gray-700 font-medium">{pattern.label}</span>
            <div className="flex items-center gap-2">
              <span className={`text-sm px-2 py-0.5 rounded ${getValueColor(pattern.label, pattern.value)}`}>
                {pattern.value}
              </span>
              {pattern.trend && (
                <span className="flex items-center gap-1 text-xs">
                  {getTrendIcon(pattern.trend)}
                  <span className="text-gray-500">{getTrendLabel(pattern.trend)}</span>
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

interface TopInterventionsDisplayProps {
  interventions: InterventionSummary[];
}

function TopInterventionsDisplay({ interventions }: TopInterventionsDisplayProps) {
  if (!interventions || interventions.length === 0) {
    return (
      <p className="text-gray-500 text-sm italic">
        No recommended interventions from recent consultation.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {interventions.map((intervention, idx) => (
        <div
          key={intervention.id}
          className={`p-3 rounded-lg border ${
            intervention.priority === 'high'
              ? 'border-orange-200 bg-orange-50'
              : intervention.priority === 'medium'
              ? 'border-yellow-200 bg-yellow-50'
              : 'border-gray-200 bg-gray-50'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-gray-400">#{idx + 1}</span>
              <span className={`px-2 py-0.5 text-xs rounded ${
                intervention.priority === 'high' ? 'bg-red-100 text-red-700' :
                intervention.priority === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                'bg-green-100 text-green-700'
              }`}>
                {intervention.priority}
              </span>
              <span className="px-2 py-0.5 text-xs bg-gray-200 text-gray-600 rounded">
                {intervention.category}
              </span>
            </div>
          </div>
          <h4 className="font-medium text-gray-900 mt-1">{intervention.name}</h4>
          <p className="text-sm text-gray-600 mt-1">{intervention.description}</p>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// Clinical Timeline Components
// ============================================================================

interface ClinicalTimelineDisplayProps {
  timeline: ClinicalTimelineResponse;
}

// Helper to get change badge styling
function getChangeBadgeStyle(change: TimelineChange): { bg: string; text: string; icon: string } {
  switch (change.type) {
    case 'first_time_diagnosis':
      return { bg: 'bg-red-100', text: 'text-red-800', icon: '🆕' };
    case 'recurring_diagnosis':
      return { bg: 'bg-orange-100', text: 'text-orange-800', icon: '🔄' };
    case 'medication_added':
      return { bg: 'bg-blue-100', text: 'text-blue-800', icon: '💊+' };
    case 'medication_removed':
      return { bg: 'bg-gray-100', text: 'text-gray-800', icon: '💊-' };
    case 'medication_changed':
      return { bg: 'bg-purple-100', text: 'text-purple-800', icon: '💊↔' };
    case 'complaint_resolved':
      return { bg: 'bg-green-100', text: 'text-green-800', icon: '✓' };
    case 'complaint_not_mentioned':
      return { bg: 'bg-gray-50', text: 'text-gray-500', icon: '?' };
    case 'complaint_new':
      return { bg: 'bg-amber-100', text: 'text-amber-800', icon: '⚠' };
    default:
      return { bg: 'bg-gray-100', text: 'text-gray-800', icon: '•' };
  }
}

// Helper to get human-readable change type label
function getChangeLabel(type: string): string {
  switch (type) {
    case 'first_time_diagnosis': return 'First Time';
    case 'recurring_diagnosis': return 'Recurring';
    case 'medication_added': return 'Added';
    case 'medication_removed': return 'Stopped';
    case 'medication_changed': return 'Changed';
    case 'complaint_resolved': return 'Resolved';
    case 'complaint_not_mentioned': return 'Not Mentioned';
    case 'complaint_new': return 'New';
    default: return type;
  }
}

function ClinicalTimelineDisplay({ timeline }: ClinicalTimelineDisplayProps) {
  const [expandedVisit, setExpandedVisit] = useState<string | null>(null);

  if (!timeline.timeline || timeline.timeline.length === 0) {
    return (
      <div className="text-center py-6 text-gray-500">
        <p>No visit history available for timeline analysis.</p>
        <p className="text-sm mt-1">At least 2 visits are needed to show changes.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <div className="bg-indigo-50 p-2 rounded-lg text-center">
          <p className="text-xs text-indigo-600">Visits</p>
          <p className="text-lg font-bold text-indigo-900">{timeline.summary.total_visits}</p>
        </div>
        <div className="bg-red-50 p-2 rounded-lg text-center">
          <p className="text-xs text-red-600">First Time Dx</p>
          <p className="text-lg font-bold text-red-900">{timeline.summary.first_time_diagnoses}</p>
        </div>
        <div className="bg-orange-50 p-2 rounded-lg text-center">
          <p className="text-xs text-orange-600">Recurring Dx</p>
          <p className="text-lg font-bold text-orange-900">{timeline.summary.recurring_diagnoses}</p>
        </div>
        <div className="bg-blue-50 p-2 rounded-lg text-center">
          <p className="text-xs text-blue-600">Med Changes</p>
          <p className="text-lg font-bold text-blue-900">{timeline.summary.medication_changes}</p>
        </div>
        <div className="bg-green-50 p-2 rounded-lg text-center">
          <p className="text-xs text-green-600">Resolved</p>
          <p className="text-lg font-bold text-green-900">{timeline.summary.resolved_complaints}</p>
        </div>
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200" />

        {/* Visit nodes */}
        <div className="space-y-4">
          {timeline.timeline.map((visit, idx) => {
            const isExpanded = expandedVisit === visit.extraction_id;
            const hasChanges = visit.changes.length > 0;
            const significantChanges = visit.changes.filter(c => c.confidence === 'high' || c.confidence === 'medium');

            return (
              <div key={visit.extraction_id} className="relative pl-10">
                {/* Node dot */}
                <div
                  className={`absolute left-2 w-5 h-5 rounded-full border-2 ${
                    visit.has_significant_changes
                      ? 'bg-red-500 border-red-600'
                      : hasChanges
                      ? 'bg-blue-500 border-blue-600'
                      : 'bg-gray-300 border-gray-400'
                  }`}
                />

                {/* Visit card */}
                <div
                  className={`border rounded-lg overflow-hidden ${
                    visit.has_significant_changes
                      ? 'border-red-200 bg-red-50/30'
                      : hasChanges
                      ? 'border-blue-200 bg-blue-50/30'
                      : 'border-gray-200 bg-gray-50/30'
                  }`}
                >
                  {/* Header */}
                  <button
                    onClick={() => setExpandedVisit(isExpanded ? null : visit.extraction_id)}
                    className="w-full px-3 py-2 flex items-center justify-between hover:bg-gray-50/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">
                        {new Date(visit.visit_date).toLocaleDateString('en-US', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric'
                        })}
                      </span>
                      {visit.consultation_type && (
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                          {visit.consultation_type}
                        </span>
                      )}
                      {visit.doctor_name && (
                        <span className="text-xs text-gray-500">
                          Dr. {visit.doctor_name}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {hasChanges && (
                        <span className="text-xs text-gray-500">
                          {visit.changes.length} change{visit.changes.length !== 1 ? 's' : ''}
                        </span>
                      )}
                      <span className="text-gray-400">{isExpanded ? '▼' : '▶'}</span>
                    </div>
                  </button>

                  {/* Changes preview (always visible if has significant changes) */}
                  {significantChanges.length > 0 && !isExpanded && (
                    <div className="px-3 pb-2 flex flex-wrap gap-1">
                      {significantChanges.slice(0, 4).map((change, cIdx) => {
                        const style = getChangeBadgeStyle(change);
                        return (
                          <span
                            key={cIdx}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded ${style.bg} ${style.text}`}
                          >
                            <span>{style.icon}</span>
                            <span className="font-medium">{change.name}</span>
                          </span>
                        );
                      })}
                      {significantChanges.length > 4 && (
                        <span className="text-xs text-gray-500 px-1">
                          +{significantChanges.length - 4} more
                        </span>
                      )}
                    </div>
                  )}

                  {/* Expanded content */}
                  {isExpanded && (
                    <div className="px-3 pb-3 border-t border-gray-100 mt-1 pt-2 space-y-3">
                      {/* Changes by category */}
                      {visit.changes.length > 0 ? (
                        <div className="space-y-2">
                          {/* Diagnosis changes */}
                          {visit.changes.filter(c => c.category === 'diagnosis').length > 0 && (
                            <div>
                              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Diagnoses</p>
                              <div className="flex flex-wrap gap-1">
                                {visit.changes.filter(c => c.category === 'diagnosis').map((change, cIdx) => {
                                  const style = getChangeBadgeStyle(change);
                                  return (
                                    <div
                                      key={cIdx}
                                      className={`inline-flex items-center gap-1 px-2 py-1 text-sm rounded ${style.bg} ${style.text}`}
                                      title={change.details || undefined}
                                    >
                                      <span>{style.icon}</span>
                                      <span>{change.name}</span>
                                      <span className="text-xs opacity-75">({getChangeLabel(change.type)})</span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Medication changes */}
                          {visit.changes.filter(c => c.category === 'medication').length > 0 && (
                            <div>
                              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Medications</p>
                              <div className="flex flex-wrap gap-1">
                                {visit.changes.filter(c => c.category === 'medication').map((change, cIdx) => {
                                  const style = getChangeBadgeStyle(change);
                                  return (
                                    <div
                                      key={cIdx}
                                      className={`inline-flex items-center gap-1 px-2 py-1 text-sm rounded ${style.bg} ${style.text}`}
                                      title={change.details || undefined}
                                    >
                                      <span>{style.icon}</span>
                                      <span>{change.name}</span>
                                      <span className="text-xs opacity-75">({getChangeLabel(change.type)})</span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Complaint changes */}
                          {visit.changes.filter(c => c.category === 'complaint').length > 0 && (
                            <div>
                              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Complaints</p>
                              <div className="flex flex-wrap gap-1">
                                {visit.changes.filter(c => c.category === 'complaint').map((change, cIdx) => {
                                  const style = getChangeBadgeStyle(change);
                                  return (
                                    <div
                                      key={cIdx}
                                      className={`inline-flex items-center gap-1 px-2 py-1 text-sm rounded ${style.bg} ${style.text}`}
                                      title={change.details || undefined}
                                    >
                                      <span>{style.icon}</span>
                                      <span>{change.name}</span>
                                      <span className="text-xs opacity-75">
                                        ({getChangeLabel(change.type)})
                                        {change.confidence === 'low' && ' ?'}
                                      </span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="text-sm text-gray-500 italic">No significant changes from previous visit</p>
                      )}

                      {/* Visit details */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 pt-2 border-t border-gray-100">
                        {/* Diagnoses */}
                        <div>
                          <p className="text-xs font-medium text-gray-400 mb-1">All Diagnoses</p>
                          {visit.diagnoses.length > 0 ? (
                            <ul className="text-xs text-gray-600 space-y-0.5">
                              {visit.diagnoses.map((dx, dIdx) => (
                                <li key={dIdx}>• {dx}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-xs text-gray-400 italic">None recorded</p>
                          )}
                        </div>

                        {/* Complaints */}
                        <div>
                          <p className="text-xs font-medium text-gray-400 mb-1">All Complaints</p>
                          {visit.complaints.length > 0 ? (
                            <ul className="text-xs text-gray-600 space-y-0.5">
                              {visit.complaints.map((c, cIdx) => (
                                <li key={cIdx}>• {c}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-xs text-gray-400 italic">None recorded</p>
                          )}
                        </div>

                        {/* Medications */}
                        <div>
                          <p className="text-xs font-medium text-gray-400 mb-1">All Medications</p>
                          {visit.medications.length > 0 ? (
                            <ul className="text-xs text-gray-600 space-y-0.5">
                              {visit.medications.map((med, mIdx) => (
                                <li key={mIdx}>• {med.name} {med.dosage && `(${med.dosage})`}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-xs text-gray-400 italic">None recorded</p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="mt-4 p-3 bg-gray-50 rounded-lg">
        <p className="text-xs font-medium text-gray-500 mb-2">Legend</p>
        <div className="flex flex-wrap gap-3 text-xs text-gray-700">
          <div className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-full bg-red-500" />
            <span className="text-gray-700">Significant changes</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-full bg-blue-500" />
            <span className="text-gray-700">Minor changes</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-full bg-gray-300" />
            <span className="text-gray-700">No changes</span>
          </div>
          <span className="text-gray-400">|</span>
          <span className="bg-red-100 text-red-800 px-1 rounded">🆕 First Time</span>
          <span className="bg-orange-100 text-orange-800 px-1 rounded">🔄 Recurring</span>
          <span className="bg-green-100 text-green-800 px-1 rounded">✓ Resolved</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function PatientHistoryScreen() {
  const { getAccessToken } = useAuth();

  // State
  const [selectedDoctorId, setSelectedDoctorId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<PatientSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedPatient, setSelectedPatient] = useState<PatientSearchResult | null>(null);

  // Doctor's patients list (for dropdown when doctor is selected)
  const [doctorPatients, setDoctorPatients] = useState<PatientSearchResult[]>([]);
  const [isLoadingDoctorPatients, setIsLoadingDoctorPatients] = useState(false);

  // Patient history data
  const [consultationHistory, setConsultationHistory] = useState<ConsultationHistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Section expansion state (for Recent Consultations sidebar)
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    consultations: false,
  });

  // View mode
  const [viewMode, setViewMode] = useState<'prescreen' | 'consult_details'>('prescreen');

  // Prescreen data
  const [prescreenData, setPrescreenData] = useState<PrescreenResponse | null>(null);
  const [isLoadingPrescreen, setIsLoadingPrescreen] = useState(false);

  // Selected consultation details (for Consult Details tab)
  const [selectedConsultation, setSelectedConsultation] = useState<ConsultationHistoryItem | null>(null);
  const [consultationDetails, setConsultationDetails] = useState<ExtractionDetailsResponse | null>(null);
  const [isLoadingConsultationDetails, setIsLoadingConsultationDetails] = useState(false);

  // Consultation dropdown
  const [isConsultationDropdownOpen, setIsConsultationDropdownOpen] = useState(false);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsConsultationDropdownOpen(false);
      }
    };
    if (isConsultationDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isConsultationDropdownOpen]);

  // Load patients when doctor is selected
  useEffect(() => {
    const loadDoctorPatients = async () => {
      if (!selectedDoctorId) {
        setDoctorPatients([]);
        return;
      }

      try {
        setIsLoadingDoctorPatients(true);
        // Load all patients for this doctor (empty query returns all)
        const response = await searchPatients('', selectedDoctorId, 1, 100, getAccessToken());
        setDoctorPatients(response.patients);
      } catch (err: any) {
        console.error('Failed to load doctor patients:', err);
        setDoctorPatients([]);
      } finally {
        setIsLoadingDoctorPatients(false);
      }
    };

    loadDoctorPatients();
  }, [selectedDoctorId]);

  // Debounced search (only when no doctor selected)
  useEffect(() => {
    if (selectedDoctorId) {
      // When doctor is selected, use dropdown instead of search
      setSearchResults([]);
      return;
    }

    const timer = setTimeout(() => {
      if (searchQuery.trim()) {
        handleSearch();
      } else {
        setSearchResults([]);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, selectedDoctorId]);

  const handleSearch = async () => {
    try {
      setIsSearching(true);
      setError(null);
      const response = await searchPatients(searchQuery, selectedDoctorId || undefined, 1, 20, getAccessToken());
      setSearchResults(response.patients);
    } catch (err: any) {
      setError(err.message || 'Search failed');
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSelectPatient = async (patient: PatientSearchResult) => {
    setSelectedPatient(patient);
    setSearchQuery('');
    setSearchResults([]);
    // Clear prescreen data when switching patients
    setPrescreenData(null);
    // Use external patient_id (not database UUID) for API calls
    await loadPatientHistory(patient.patient_id);
    // Always load prescreen data since we only have prescreen view
    if (selectedDoctorId) {
      loadPrescreenData(patient.patient_id);
    }
  };

  const loadPatientHistory = async (patientId: string) => {
    try {
      setIsLoadingHistory(true);
      setError(null);

      // Load consultation history for sidebar
      const accessToken = getAccessToken();
      const consultations = await getConsultationHistory(patientId, selectedDoctorId || undefined, 1, 10, accessToken);
      setConsultationHistory(consultations.consultations);
    } catch (err: any) {
      setError(err.message || 'Failed to load patient history');
      setConsultationHistory([]);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  const clearPatient = () => {
    setSelectedPatient(null);
    setConsultationHistory([]);
    setPrescreenData(null);
    setSelectedConsultation(null);
    setConsultationDetails(null);
    setViewMode('prescreen');
  };

  // Load prescreen data when tab is clicked
  const loadPrescreenData = async (patientId: string) => {
    if (!selectedDoctorId) {
      setError('Please select a doctor to view prescreen data');
      return;
    }

    try {
      setIsLoadingPrescreen(true);
      setError(null);
      const prescreen = await getPatientPrescreen(patientId, selectedDoctorId, getAccessToken());
      setPrescreenData(prescreen);
    } catch (err: any) {
      setError(err.message || 'Failed to load prescreen data');
      setPrescreenData(null);
    } finally {
      setIsLoadingPrescreen(false);
    }
  };

  // Load prescreen data when patient is selected
  const handleViewModeChange = (mode: 'prescreen' | 'consult_details') => {
    setViewMode(mode);
    if (mode === 'prescreen' && selectedPatient && !prescreenData && !isLoadingPrescreen) {
      // Use external patient_id (not database UUID) for API calls
      loadPrescreenData(selectedPatient.patient_id);
    }
  };

  // Load consultation details when a consultation is clicked
  const loadConsultationDetails = async (consultation: ConsultationHistoryItem) => {
    try {
      setIsLoadingConsultationDetails(true);
      setError(null);
      setSelectedConsultation(consultation);
      setViewMode('consult_details');

      const details = await getExtractionDetails(consultation.extraction_id, true, getAccessToken());
      setConsultationDetails(details);
    } catch (err: any) {
      setError(err.message || 'Failed to load consultation details');
      setConsultationDetails(null);
    } finally {
      setIsLoadingConsultationDetails(false);
    }
  };

  // Format date helper
  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Unknown';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Patient History</h1>
              <p className="text-sm text-gray-500 mt-1">
                View patient medical history, prescriptions, and context
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Panel - Search & Patient Info */}
          <div className="lg:col-span-1 space-y-4">
            {/* Doctor Selector */}
            <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
              <DoctorSelector
                selectedDoctorId={selectedDoctorId}
                onDoctorSelect={(doctorId) => {
                  setSelectedDoctorId(doctorId);
                  // Clear patient selection when doctor changes
                  setSelectedPatient(null);
                  setConsultationHistory([]);
                  setPrescreenData(null);
                  setSearchResults([]);
                  setSearchQuery('');
                }}
              />
              {selectedDoctorId && (
                <p className="text-xs text-gray-500 mt-2">
                  Showing patients for selected doctor only
                </p>
              )}
            </div>

            {/* Patient Selection */}
            <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Select Patient
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={selectedDoctorId ? "Type to filter patients..." : "Search by name or patient ID..."}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                />
                {(isSearching || isLoadingDoctorPatients) && (
                  <div className="absolute right-3 top-2.5">
                    <svg className="animate-spin h-5 w-5 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                  </div>
                )}
              </div>

              {/* Patient Dropdown - When doctor is selected, show filtered list from doctorPatients */}
              {selectedDoctorId && doctorPatients.length > 0 && (
                <div className="mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                  {doctorPatients
                    .filter(patient => {
                      if (!searchQuery.trim()) return true;
                      const query = searchQuery.toLowerCase();
                      return (
                        (patient.full_name?.toLowerCase().includes(query)) ||
                        (patient.patient_id?.toLowerCase().includes(query))
                      );
                    })
                    .map((patient) => (
                      <button
                        key={patient.id}
                        onClick={() => handleSelectPatient(patient)}
                        className={`w-full px-4 py-3 text-left hover:bg-gray-50 border-b border-gray-100 last:border-b-0 ${
                          selectedPatient?.id === patient.id ? 'bg-blue-50' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-medium text-gray-900">
                              {patient.full_name || patient.patient_id}
                            </p>
                            <p className="text-sm text-gray-500">
                              ID: {patient.patient_id}
                              {patient.gender && ` | ${patient.gender}`}
                              {patient.hospital_name && ` | ${patient.hospital_name}`}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm text-gray-600">
                              {patient.consultation_count} visits
                            </p>
                            {patient.last_visit_date && (
                              <p className="text-xs text-gray-400">
                                Last: {formatDate(patient.last_visit_date)}
                              </p>
                            )}
                          </div>
                        </div>
                      </button>
                    ))}
                  {doctorPatients.filter(patient => {
                    if (!searchQuery.trim()) return true;
                    const query = searchQuery.toLowerCase();
                    return (
                      (patient.full_name?.toLowerCase().includes(query)) ||
                      (patient.patient_id?.toLowerCase().includes(query))
                    );
                  }).length === 0 && (
                    <p className="px-4 py-3 text-sm text-gray-500 italic">No patients match your search</p>
                  )}
                </div>
              )}

              {/* Show empty state when doctor selected but no patients */}
              {selectedDoctorId && !isLoadingDoctorPatients && doctorPatients.length === 0 && (
                <p className="mt-2 text-sm text-gray-500 italic">No patients found for this doctor</p>
              )}

              {/* Search Results Dropdown - When no doctor selected, show search results */}
              {!selectedDoctorId && searchResults.length > 0 && (
                <div className="mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                  {searchResults.map((patient) => (
                    <button
                      key={patient.id}
                      onClick={() => handleSelectPatient(patient)}
                      className="w-full px-4 py-3 text-left hover:bg-gray-50 border-b border-gray-100 last:border-b-0"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-medium text-gray-900">
                            {patient.full_name || patient.patient_id}
                          </p>
                          <p className="text-sm text-gray-500">
                            ID: {patient.patient_id}
                            {patient.gender && ` | ${patient.gender}`}
                            {patient.hospital_name && ` | ${patient.hospital_name}`}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm text-gray-600">
                            {patient.consultation_count} visits
                          </p>
                          {patient.last_visit_date && (
                            <p className="text-xs text-gray-400">
                              Last: {formatDate(patient.last_visit_date)}
                            </p>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Panel - Patient History Details */}
          <div className="lg:col-span-2 space-y-4">
            {isLoadingHistory ? (
              <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
                <svg className="animate-spin h-8 w-8 text-blue-500 mx-auto mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <p className="text-gray-600">Loading patient history...</p>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-center gap-2 text-red-800">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="font-medium">Error</span>
                </div>
                <p className="mt-2 text-red-700">{error}</p>
              </div>
            ) : !selectedPatient ? (
              <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
                <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <span className="text-3xl">🔍</span>
                </div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">
                  Search for a Patient
                </h3>
                <p className="text-gray-500">
                  Enter a patient name or ID in the search box to view their medical history.
                </p>
              </div>
            ) : selectedPatient ? (
              <>
                {/* Tab Navigation */}
                <div className="flex items-center justify-between bg-white rounded-lg border border-gray-200 p-1">
                  <div className="flex gap-1">
                    <button
                      onClick={() => handleViewModeChange('prescreen')}
                      className={`px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-2 ${
                        viewMode === 'prescreen'
                          ? 'bg-purple-100 text-purple-700'
                          : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      <span>📋</span>
                      PreScreen
                    </button>
                    {selectedConsultation && (
                      <div className="flex items-center">
                        <button
                          onClick={() => handleViewModeChange('consult_details')}
                          className={`px-4 py-2 rounded-l-md text-sm font-medium transition-colors flex items-center gap-2 ${
                            viewMode === 'consult_details'
                              ? 'bg-blue-100 text-blue-700'
                              : 'text-gray-600 hover:bg-gray-100'
                          }`}
                        >
                          <span>📄</span>
                          Consult Details
                        </button>
                        <button
                          onClick={() => {
                            setSelectedConsultation(null);
                            setConsultationDetails(null);
                            setViewMode('prescreen');
                          }}
                          className={`px-2 py-2 rounded-r-md text-sm transition-colors ${
                            viewMode === 'consult_details'
                              ? 'bg-blue-100 text-blue-500 hover:text-blue-700'
                              : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
                          }`}
                          title="Close consultation details"
                        >
                          ×
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {viewMode === 'prescreen' && (
                      <button
                        onClick={() => loadPrescreenData(selectedPatient.patient_id)}
                        className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1 px-2"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        Refresh
                      </button>
                    )}
                    {/* Recent Consultations Dropdown */}
                    {consultationHistory.length > 0 && (
                      <div className="relative" ref={dropdownRef}>
                        <button
                          onClick={() => setIsConsultationDropdownOpen(!isConsultationDropdownOpen)}
                          className="px-3 py-2 text-sm font-medium text-gray-700 bg-gray-50 hover:bg-gray-100 rounded-md flex items-center gap-2 border border-gray-200"
                        >
                          <span>📅</span>
                          Consultations ({consultationHistory.length})
                          <svg className={`w-4 h-4 transition-transform ${isConsultationDropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                        {isConsultationDropdownOpen && (
                          <div className="absolute right-0 mt-1 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-50 max-h-96 overflow-y-auto">
                            <div className="px-3 py-2 border-b border-gray-100 bg-gray-50">
                              <p className="text-xs font-medium text-gray-500 uppercase">Recent Consultations</p>
                            </div>
                            {consultationHistory.map((consultation) => (
                              <button
                                key={consultation.extraction_id}
                                onClick={() => {
                                  loadConsultationDetails(consultation);
                                  setIsConsultationDropdownOpen(false);
                                }}
                                className={`w-full text-left px-3 py-2 hover:bg-blue-50 transition-colors border-b border-gray-50 last:border-b-0 ${
                                  selectedConsultation?.extraction_id === consultation.extraction_id
                                    ? 'bg-blue-50'
                                    : ''
                                }`}
                              >
                                <div className="flex items-start justify-between">
                                  <div>
                                    <p className="text-sm font-medium text-gray-900">
                                      {consultation.consultation_type_name || 'Consultation'}
                                    </p>
                                    <p className="text-xs text-gray-500">
                                      {formatDate(consultation.created_at)}
                                    </p>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    {consultation.is_edited && (
                                      <span className="px-1.5 py-0.5 text-xs bg-yellow-100 text-yellow-700 rounded">
                                        Edited
                                      </span>
                                    )}
                                  </div>
                                </div>
                                {consultation.primary_diagnosis && (
                                  <p className="mt-1 text-xs text-gray-600 truncate">
                                    Dx: {consultation.primary_diagnosis}
                                  </p>
                                )}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* PreScreen View */}
                {viewMode === 'prescreen' && (
                  <div className="space-y-4">
                    {isLoadingPrescreen ? (
                      <div className="flex items-center justify-center py-12 bg-white rounded-lg border border-gray-200">
                        <svg className="animate-spin h-8 w-8 text-purple-500 mr-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span className="text-gray-600">Loading prescreen data...</span>
                      </div>
                    ) : !selectedDoctorId ? (
                      <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                        <span className="text-4xl">👨‍⚕️</span>
                        <p className="mt-3 text-gray-600">Please select a doctor to view prescreen data.</p>
                      </div>
                    ) : prescreenData ? (
                      <>
                        {/* Prescreen Header */}
                        <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <span className="text-2xl">📋</span>
                              <div>
                                <h3 className="font-semibold text-purple-900">Pre-Consultation Summary</h3>
                                <p className="text-sm text-purple-700">
                                  {prescreenData.consultation_count} consultations • Last visit: {prescreenData.last_visit_date || 'N/A'}
                                </p>
                              </div>
                            </div>
                            {prescreenData.has_prescreen && (
                              <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full">
                                Nurse Assessment Available
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Warning Factors (CAUTION) */}
                        <SectionCard
                          title="Patient Warning Factors"
                          icon="⚠️"
                          isExpanded={true}
                          isEmpty={!prescreenData.warning_factors}
                        >
                          {prescreenData.warning_factors ? (
                            <div className="space-y-3">
                              {prescreenData.warning_factors_date && (
                                <p className="text-xs text-gray-500">From consultation on {prescreenData.warning_factors_date}</p>
                              )}
                              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                                <DataDisplay data={prescreenData.warning_factors} />
                              </div>
                            </div>
                          ) : (
                            <p className="text-gray-500 italic">No warning factors recorded for this patient.</p>
                          )}
                        </SectionCard>

                        {/* Past Diagnosis Summary (SUMMARY) */}
                        <SectionCard
                          title="Past Diagnosis Summary"
                          icon="🩺"
                          isExpanded={true}
                          isEmpty={!prescreenData.past_diagnosis_summary}
                        >
                          {prescreenData.past_diagnosis_summary ? (
                            <div className="space-y-3">
                              {prescreenData.past_diagnosis_summary_date && (
                                <p className="text-xs text-gray-500">From consultation on {prescreenData.past_diagnosis_summary_date}</p>
                              )}
                              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                                <DataDisplay data={prescreenData.past_diagnosis_summary} />
                              </div>
                            </div>
                          ) : (
                            <p className="text-gray-500 italic">No past diagnosis summary available.</p>
                          )}
                        </SectionCard>

                        {/* Emotion Pattern Summary */}
                        <SectionCard
                          title="Emotion Pattern (Last 3 Visits)"
                          icon="💭"
                          isExpanded={true}
                          isEmpty={!prescreenData.emotion_pattern_summary?.has_emotion_data}
                        >
                          {prescreenData.emotion_pattern_summary?.has_emotion_data ? (
                            <EmotionPatternSummaryDisplay patternSummary={prescreenData.emotion_pattern_summary} />
                          ) : (
                            <p className="text-gray-500 italic">No emotion analysis data available.</p>
                          )}
                        </SectionCard>

                        {/* Top Interventions */}
                        <SectionCard
                          title="Top Recommended Interventions"
                          icon="💡"
                          isExpanded={true}
                          isEmpty={!prescreenData.top_interventions || prescreenData.top_interventions.length === 0}
                        >
                          {prescreenData.top_interventions && prescreenData.top_interventions.length > 0 ? (
                            <TopInterventionsDisplay interventions={prescreenData.top_interventions} />
                          ) : (
                            <p className="text-gray-500 italic">No intervention recommendations available.</p>
                          )}
                        </SectionCard>

                        {/* Clinical Timeline */}
                        <SectionCard
                          title="Clinical Timeline (Last 5 Visits)"
                          icon="📈"
                          isExpanded={true}
                          isEmpty={!prescreenData.clinical_timeline || prescreenData.clinical_timeline.visit_count === 0}
                        >
                          {prescreenData.clinical_timeline && prescreenData.clinical_timeline.visit_count > 0 ? (
                            <ClinicalTimelineDisplay
                              timeline={{
                                patient: prescreenData.patient,
                                timeline: prescreenData.clinical_timeline.timeline as any,
                                summary: prescreenData.clinical_timeline.summary,
                                visit_count: prescreenData.clinical_timeline.visit_count
                              }}
                            />
                          ) : (
                            <p className="text-gray-500 italic">No clinical timeline data available.</p>
                          )}
                        </SectionCard>

                        {/* Last Prescription */}
                        <SectionCard
                          title="Last Prescription"
                          icon="💊"
                          isExpanded={true}
                          isEmpty={!prescreenData.last_prescription}
                        >
                          {prescreenData.last_prescription ? (
                            <div className="space-y-2">
                              {prescreenData.last_prescription_date && (
                                <p className="text-xs text-gray-500 mb-2">From consultation on {prescreenData.last_prescription_date}</p>
                              )}
                              <PrescriptionDisplay prescription={prescreenData.last_prescription} />
                            </div>
                          ) : (
                            <p className="text-gray-500 italic">No prescription data available.</p>
                          )}
                        </SectionCard>

                        {/* Prescreen Template Data (if available) */}
                        {prescreenData.has_prescreen && prescreenData.prescreen_data && (
                          <SectionCard
                            title="Nurse Assessment Data"
                            icon="📝"
                            metadata={prescreenData.prescreen_metadata}
                            isExpanded={true}
                          >
                            <div className="bg-gray-50 rounded-lg p-4">
                              <DataDisplay data={prescreenData.prescreen_data} />
                            </div>
                          </SectionCard>
                        )}
                      </>
                    ) : (
                      <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                        <span className="text-4xl">📋</span>
                        <p className="mt-3 text-gray-600">No nurse assessment data available for this patient.</p>
                        <p className="text-sm text-gray-400 mt-1">Nurse assessment data will appear here when available.</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Consult Details View */}
                {viewMode === 'consult_details' && (
                  <div className="space-y-4">
                    {isLoadingConsultationDetails ? (
                      <div className="flex items-center justify-center py-12 bg-white rounded-lg border border-gray-200">
                        <svg className="animate-spin h-8 w-8 text-blue-500 mr-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span className="text-gray-600">Loading consultation details...</span>
                      </div>
                    ) : consultationDetails ? (
                      <>
                        {/* Consultation Header */}
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <span className="text-2xl">📄</span>
                              <div>
                                <h3 className="font-semibold text-blue-900">
                                  {selectedConsultation?.consultation_type_name || 'Consultation'} Details
                                </h3>
                                <p className="text-sm text-blue-700">
                                  {formatDate(consultationDetails.created_at)}
                                  {selectedConsultation?.doctor_name && ` • Dr. ${selectedConsultation.doctor_name}`}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {consultationDetails.is_edited && (
                                <span className="px-2 py-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded-full">
                                  Edited ({consultationDetails.edit_count}x)
                                </span>
                              )}
                              <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                                {consultationDetails.segment_count} segments
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Render each segment - filter out empty/deleted, sort by priority */}
                        {consultationDetails.segments && consultationDetails.segments.length > 0 ? (
                          consultationDetails.segments
                            .filter((segment) => {
                              // Filter out deleted segments and empty segment_value
                              if (segment.is_deleted) return false;
                              if (!segment.segment_value) return false;
                              if (typeof segment.segment_value === 'object' && Object.keys(segment.segment_value).length === 0) return false;
                              return true;
                            })
                            .sort((a, b) => getSegmentPriority(a.segment_code || '') - getSegmentPriority(b.segment_code || ''))
                            .map((segment, index) => {
                              const segmentCode = segment.segment_code || '';
                              const isPrescription = segmentCode.toLowerCase().includes('prescription');

                              return (
                                <SectionCard
                                  key={segmentCode || index}
                                  title={segmentCode.replace(/_/g, ' ')}
                                  icon={getSegmentIcon(segmentCode)}
                                  isExpanded={true}
                                  isEmpty={false}
                                >
                                  {isPrescription ? (
                                    <PrescriptionDisplay prescription={segment.segment_value} />
                                  ) : (
                                    <DataDisplay data={segment.segment_value} />
                                  )}
                                </SectionCard>
                              );
                            })
                        ) : consultationDetails.extraction_data && Object.keys(consultationDetails.extraction_data).length > 0 ? (
                          // Fallback: render extraction_data if no segments
                          <SectionCard
                            title="Extraction Data"
                            icon="📋"
                            isExpanded={true}
                          >
                            <DataDisplay data={consultationDetails.extraction_data} />
                          </SectionCard>
                        ) : (
                          <div className="text-center py-8 bg-white rounded-lg border border-gray-200">
                            <span className="text-3xl">📭</span>
                            <p className="mt-2 text-gray-600">No segment data available for this consultation.</p>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                        <span className="text-4xl">📄</span>
                        <p className="mt-3 text-gray-600">Select a consultation from the list to view details.</p>
                      </div>
                    )}
                  </div>
                )}

              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export default PatientHistoryScreen;

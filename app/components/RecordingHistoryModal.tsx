'use client';

import React, { useState, useEffect } from 'react';
import {
  listDoctorRecordings,
  listNurseRecordings,
  reprocessRecording,
  RecordingInfo,
  ReprocessRequest,
} from '../../lib/recordingsApi';
import { searchPatients, PatientSearchResult } from '../../lib/patientHistoryApi';
import { ActivatedTemplate, ProcessingMode } from '../../lib/types';
import { AudioPlayerModal } from './AudioPlayerModal';
import { ExtractionViewerModal, type ExtractionViewerMode } from './ExtractionViewerModal';

// Info passed when reprocess starts (for progress tracking)
export interface ReprocessStartedInfo {
  submissionId: string;
  sessionId: string;
  patientId: string;
  patientName: string;
  templateCode: string;
  templateName: string;
  consultationTypeCode: string;
}

interface RecordingHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  doctorId?: string;
  nurseId?: string;
  templates: ActivatedTemplate[];
  processingModes: ProcessingMode[];
  accessToken: string | null;
  onReprocessStarted?: (info: ReprocessStartedInfo) => void;
}

export function RecordingHistoryModal({
  isOpen,
  onClose,
  doctorId,
  nurseId,
  templates,
  processingModes,
  accessToken,
  onReprocessStarted,
}: RecordingHistoryModalProps) {
  const entityId = doctorId || nurseId;
  const entityType = doctorId ? 'doctor' : 'nurse';
  // State
  const [recordings, setRecordings] = useState<RecordingInfo[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [patientFilter, setPatientFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('SUBMITTED');  // SUBMITTED or RECORDING
  const [datePreset, setDatePreset] = useState<string>('all');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const pageSize = 20;

  // Patient dropdown state
  const [patientsList, setPatientsList] = useState<PatientSearchResult[]>([]);
  const [loadingPatients, setLoadingPatients] = useState(false);

  // Reprocess form state
  const [selectedRecording, setSelectedRecording] = useState<RecordingInfo | null>(null);
  const [reprocessMode, setReprocessMode] = useState<'new_extraction' | 'reprocess_transcript'>('new_extraction');
  const [reprocessTemplate, setReprocessTemplate] = useState<string>('');
  const [reprocessProcessingMode, setReprocessProcessingMode] = useState<string>('default');
  const [reprocessExtractionMode, setReprocessExtractionMode] = useState<'core' | 'additional' | 'full'>('full');
  const [reprocessing, setReprocessing] = useState(false);
  const [reprocessError, setReprocessError] = useState<string | null>(null);
  const [reprocessSuccess, setReprocessSuccess] = useState<string | null>(null);

  // Audio playback state
  const [audioPlaybackRecording, setAudioPlaybackRecording] = useState<RecordingInfo | null>(null);
  const [audioPlaybackType, setAudioPlaybackType] = useState<'original' | 'processed'>('original');

  // Transcript/Extraction viewer state
  const [viewerRecording, setViewerRecording] = useState<RecordingInfo | null>(null);
  const [viewerMode, setViewerMode] = useState<ExtractionViewerMode>('extraction');

  // Load patients for dropdown when modal opens
  useEffect(() => {
    if (isOpen && entityId) {
      loadPatients();
    }
  }, [isOpen, entityId]);

  // Load recordings when modal opens or filters change
  useEffect(() => {
    if (isOpen && entityId) {
      loadRecordings();
    }
  }, [isOpen, entityId, page, patientFilter, statusFilter, datePreset, dateFrom, dateTo]);

  // Set default template when templates load
  useEffect(() => {
    if (templates.length > 0 && !reprocessTemplate) {
      setReprocessTemplate(templates[0].template_code);
    }
  }, [templates]);

  const loadPatients = async () => {
    if (entityType === 'nurse') {
      // For nurse mode, load patients from nurse's recordings (no patient search endpoint for nurses)
      setLoadingPatients(true);
      try {
        const result = entityId
          ? await listNurseRecordings(entityId, { limit: 200 }, accessToken)
          : { recordings: [] };
        const seen = new Map<string, PatientSearchResult>();
        for (const rec of result.recordings) {
          if (rec.patient_id && !seen.has(rec.patient_id)) {
            seen.set(rec.patient_id, {
              id: rec.patient_id,
              patient_id: rec.patient_identifier || '',
              full_name: rec.patient_name || 'Unknown',
              date_of_birth: null,
              gender: null,
              consultation_count: 0,
              last_visit_date: rec.consultation_datetime || null,
            });
          }
        }
        setPatientsList(Array.from(seen.values()));
      } catch (err: any) {
        console.error('Failed to load nurse patients:', err);
        setPatientsList([]);
      } finally {
        setLoadingPatients(false);
      }
      return;
    }

    setLoadingPatients(true);
    try {
      const response = await searchPatients('', doctorId || undefined, 1, 100, accessToken);
      setPatientsList(response.patients || []);
    } catch (err: any) {
      console.error('Failed to load patients:', err);
      setPatientsList([]);
    } finally {
      setLoadingPatients(false);
    }
  };

  // Helper to calculate date range from preset
  const getDateRangeFromPreset = (preset: string): { from?: string; to?: string } => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    switch (preset) {
      case 'today':
        return { from: today.toISOString(), to: new Date(today.getTime() + 24 * 60 * 60 * 1000).toISOString() };
      case 'yesterday': {
        const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
        return { from: yesterday.toISOString(), to: today.toISOString() };
      }
      case 'this_week': {
        const startOfWeek = new Date(today);
        startOfWeek.setDate(today.getDate() - today.getDay());
        return { from: startOfWeek.toISOString() };
      }
      case 'last_7_days': {
        const last7Days = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
        return { from: last7Days.toISOString() };
      }
      case 'this_month': {
        const startOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
        return { from: startOfMonth.toISOString() };
      }
      case 'last_30_days': {
        const last30Days = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
        return { from: last30Days.toISOString() };
      }
      case 'custom':
        return { from: dateFrom || undefined, to: dateTo || undefined };
      default:
        return {};
    }
  };

  const loadRecordings = async () => {
    if (!entityId) return;
    setLoading(true);
    setError(null);
    try {
      const dateRange = getDateRangeFromPreset(datePreset);
      const params = {
        patient_id: patientFilter && patientFilter.includes('-') ? patientFilter : undefined,
        patient_identifier: patientFilter && !patientFilter.includes('-') ? patientFilter : undefined,
        status: statusFilter,
        date_from: dateRange.from,
        date_to: dateRange.to,
        limit: pageSize,
        offset: page * pageSize,
      };
      const result = entityType === 'nurse'
        ? await listNurseRecordings(entityId, params, accessToken)
        : await listDoctorRecordings(entityId, params, accessToken);
      setRecordings(result.recordings);
      setTotalCount(result.total_count);
    } catch (err: any) {
      setError(err.message || 'Failed to load recordings');
    } finally {
      setLoading(false);
    }
  };

  const handleReprocess = async () => {
    if (!selectedRecording || !reprocessTemplate) return;

    setReprocessing(true);
    setReprocessError(null);
    setReprocessSuccess(null);

    try {
      const request: ReprocessRequest = {
        mode: reprocessMode,
        template_code: reprocessTemplate,
        processing_mode: reprocessProcessingMode,
        extraction_mode: reprocessExtractionMode,
      };

      const result = await reprocessRecording(
        selectedRecording.session_id,
        request,
        accessToken
      );

      setReprocessSuccess(
        `${result.message}${result.fallback_used ? ' (Fallback to new extraction - no transcript found)' : ''}`
      );

      // Notify parent with full info for progress tracking
      if (onReprocessStarted) {
        const selectedTemplateInfo = templates.find(t => t.template_code === reprocessTemplate);
        onReprocessStarted({
          submissionId: result.submission_id,
          sessionId: selectedRecording.session_id,
          patientId: selectedRecording.patient_identifier || selectedRecording.patient_id || 'Unknown',
          patientName: selectedRecording.patient_name || 'Unknown Patient',
          templateCode: reprocessTemplate,
          templateName: selectedTemplateInfo?.template_name || reprocessTemplate,
          consultationTypeCode: selectedTemplateInfo?.consultation_type_code || 'OP',
        });
      }

      // Reset selection after success
      setSelectedRecording(null);
    } catch (err: any) {
      setReprocessError(err.message || 'Failed to start reprocessing');
    } finally {
      setReprocessing(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString();
  };

  // Handler for selecting a recording - auto-switches mode for RECORDING status
  const handleSelectRecording = (recording: RecordingInfo) => {
    setSelectedRecording(recording);
    // Default the template dropdown to the recording's original template
    if (recording.template_code && templates.some(t => t.template_code === recording.template_code)) {
      setReprocessTemplate(recording.template_code);
    }
    // For abandoned recordings (RECORDING status), force new_extraction mode
    if (recording.status === 'RECORDING') {
      setReprocessMode('new_extraction');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={onClose}
        />

        {/* Modal */}
        <div className="relative inline-block w-full max-w-6xl my-8 text-left align-middle bg-white rounded-2xl shadow-xl transform transition-all">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 rounded-t-2xl">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">📜</span>
                <div>
                  <h2 className="text-xl font-bold text-white">Recording History</h2>
                  <p className="text-blue-200 text-sm">
                    {totalCount} recordings available for reprocessing
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="text-white/80 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="p-6 max-h-[70vh] overflow-y-auto">
            {/* Success/Error Messages */}
            {reprocessSuccess && (
              <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700">
                {reprocessSuccess}
              </div>
            )}
            {reprocessError && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700">
                {reprocessError}
              </div>
            )}

            {/* Filters */}
            <div className="mb-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
              {/* Patient Filter */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Filter by Patient
                </label>
                {loadingPatients ? (
                  <div className="flex items-center py-2">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500 mr-2"></div>
                    <span className="text-gray-500 text-sm">Loading patients...</span>
                  </div>
                ) : patientsList.length > 0 ? (
                  <select
                    value={patientFilter}
                    onChange={(e) => {
                      setPatientFilter(e.target.value);
                      setPage(0);
                    }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900"
                  >
                    <option value="">All patients</option>
                    {patientsList.map((patient) => (
                      <option key={patient.id} value={patient.id}>
                        {patient.patient_id}
                        {patient.full_name ? ` - ${patient.full_name}` : ''}
                        {patient.hospital_name ? ` (${patient.hospital_name})` : ''}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={patientFilter}
                    onChange={(e) => {
                      setPatientFilter(e.target.value);
                      setPage(0);
                    }}
                    placeholder="Enter patient ID or MRN"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                )}
              </div>

              {/* Status Filter */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Recording Status
                </label>
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setPage(0);
                    setSelectedRecording(null);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900"
                >
                  <option value="SUBMITTED">Completed Recordings</option>
                  <option value="RECORDING">Abandoned Recordings</option>
                  <option value="validation_failed">Quality Rejected</option>
                </select>
                {statusFilter === 'RECORDING' && (
                  <p className="text-xs text-amber-600 mt-1">
                    Abandoned recordings with available audio chunks
                  </p>
                )}
                {statusFilter === 'validation_failed' && (
                  <p className="text-xs text-red-600 mt-1">
                    Recordings rejected due to audio quality issues
                  </p>
                )}
              </div>

              {/* Date Preset Filter */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Date Range
                </label>
                <select
                  value={datePreset}
                  onChange={(e) => {
                    setDatePreset(e.target.value);
                    if (e.target.value !== 'custom') {
                      setDateFrom('');
                      setDateTo('');
                    }
                    setPage(0);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900"
                >
                  <option value="all">All Time</option>
                  <option value="today">Today</option>
                  <option value="yesterday">Yesterday</option>
                  <option value="this_week">This Week</option>
                  <option value="last_7_days">Last 7 Days</option>
                  <option value="this_month">This Month</option>
                  <option value="last_30_days">Last 30 Days</option>
                  <option value="custom">Custom Range</option>
                </select>
              </div>

              {/* Custom Date From */}
              {datePreset === 'custom' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    From Date
                  </label>
                  <input
                    type="date"
                    value={dateFrom ? dateFrom.split('T')[0] : ''}
                    onChange={(e) => {
                      setDateFrom(e.target.value ? new Date(e.target.value + 'T00:00:00').toISOString() : '');
                      setPage(0);
                    }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                  />
                </div>
              )}

              {/* Custom Date To */}
              {datePreset === 'custom' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    To Date
                  </label>
                  <input
                    type="date"
                    value={dateTo ? dateTo.split('T')[0] : ''}
                    onChange={(e) => {
                      setDateTo(e.target.value ? new Date(e.target.value + 'T23:59:59').toISOString() : '');
                      setPage(0);
                    }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                  />
                </div>
              )}

              {/* Refresh Button */}
              <div className={datePreset === 'custom' ? 'lg:col-span-4 md:col-span-2' : ''}>
                <button
                  onClick={loadRecordings}
                  disabled={loading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {loading ? 'Loading...' : 'Refresh'}
                </button>
              </div>
            </div>

            {/* Error State */}
            {error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
                {error}
              </div>
            )}

            {/* Loading State */}
            {loading && (
              <div className="flex justify-center items-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
            )}

            {/* Recordings Table */}
            {!loading && recordings.length > 0 && (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Select</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Patient</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Template</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data Available</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {recordings.map((recording, index) => (
                      <tr
                        key={recording.session_id || `recording-${index}`}
                        className={`${
                          recording.is_merged ? '' : 'hover:bg-gray-50 cursor-pointer'
                        } ${
                          !recording.is_merged && selectedRecording?.session_id === recording.session_id
                            ? 'bg-blue-50'
                            : ''
                        }`}
                        onClick={recording.is_merged ? undefined : () => handleSelectRecording(recording)}
                      >
                        <td className="px-4 py-3">
                          {recording.is_merged ? (
                            <span className="text-xs text-gray-300">—</span>
                          ) : (
                            <input
                              type="radio"
                              checked={selectedRecording?.session_id === recording.session_id}
                              onChange={() => handleSelectRecording(recording)}
                              className="h-4 w-4 text-blue-600"
                            />
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-sm font-medium text-gray-900">
                            {recording.patient_name || 'Unknown'}
                          </div>
                          <div className="text-xs text-gray-500">
                            {recording.patient_identifier || '-'}
                          </div>
                          <div className="text-xs text-gray-400 font-mono">
                            sessId: {recording.session_id.slice(0, 8)}...
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-500">
                          {formatDate(recording.consultation_datetime)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-sm text-gray-900">
                            {recording.template_name || recording.template_code || '-'}
                          </div>
                          <div className="text-xs text-gray-500">
                            {recording.processing_mode || '-'}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {recording.is_merged ? (
                            <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-indigo-100 text-indigo-800">
                              Merged
                            </span>
                          ) : (
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                              recording.status === 'SUBMITTED'
                                ? 'bg-green-100 text-green-800'
                                : recording.status === 'RECORDING'
                                ? 'bg-amber-100 text-amber-800'
                                : recording.status === 'validation_failed'
                                ? 'bg-red-100 text-red-800'
                                : 'bg-yellow-100 text-yellow-800'
                            }`}>
                              {recording.status === 'RECORDING' ? 'Abandoned' : recording.status === 'validation_failed' ? 'Quality Rejected' : recording.status}
                            </span>
                          )}
                          {recording.status === 'validation_failed' && recording.error_message && (
                            <p className="text-xs text-red-600 mt-1 max-w-[200px] truncate" title={recording.error_message}>
                              {recording.error_message}
                            </p>
                          )}
                          {recording.audio_quality && (
                            <span className={`inline-flex px-2 py-0.5 mt-1 text-xs font-medium rounded-full ${
                              recording.audio_quality.overall_quality === 'good'
                                ? 'bg-green-50 text-green-700'
                                : recording.audio_quality.overall_quality === 'fair'
                                ? 'bg-yellow-50 text-yellow-700'
                                : 'bg-red-50 text-red-700'
                            }`}>
                              Quality: {recording.audio_quality.overall_quality}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-2">
                            {recording.status === 'RECORDING' && recording.chunk_count > 0 && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">
                                {recording.chunk_count} Chunks
                              </span>
                            )}
                            {recording.status !== 'RECORDING' && recording.has_audio && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (recording.last_submission_id) {
                                    setAudioPlaybackType('original');
                                    setAudioPlaybackRecording(recording);
                                  }
                                }}
                                disabled={!recording.last_submission_id}
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                                  recording.last_submission_id
                                    ? 'bg-blue-100 text-blue-800 hover:bg-blue-200'
                                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                }`}
                                title={recording.last_submission_id ? 'Play audio recording' : 'No submission ID available'}
                              >
                                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M8 5v14l11-7z"/>
                                </svg>
                                Audio
                              </button>
                            )}
                            {recording.status !== 'RECORDING' && recording.has_processed_audio && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (recording.last_submission_id) {
                                    setAudioPlaybackType('processed');
                                    setAudioPlaybackRecording(recording);
                                  }
                                }}
                                disabled={!recording.last_submission_id}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800 hover:bg-emerald-200"
                                title="Play silence-removed audio"
                              >
                                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M8 5v14l11-7z"/>
                                </svg>
                                Processed
                              </button>
                            )}
                            {recording.has_transcript && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (recording.last_extraction_id) {
                                    setViewerMode('transcript');
                                    setViewerRecording(recording);
                                  }
                                }}
                                disabled={!recording.last_extraction_id}
                                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                                  recording.last_extraction_id
                                    ? 'bg-purple-100 text-purple-800 hover:bg-purple-200 cursor-pointer'
                                    : 'bg-purple-50 text-purple-400 cursor-not-allowed'
                                }`}
                                title={recording.last_extraction_id ? 'View transcript' : 'No extraction id available'}
                              >
                                Transcript
                              </button>
                            )}
                            {recording.has_extraction && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (recording.last_extraction_id) {
                                    setViewerMode('extraction');
                                    setViewerRecording(recording);
                                  }
                                }}
                                disabled={!recording.last_extraction_id}
                                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                                  recording.last_extraction_id
                                    ? 'bg-green-100 text-green-800 hover:bg-green-200 cursor-pointer'
                                    : 'bg-green-50 text-green-400 cursor-not-allowed'
                                }`}
                                title={recording.last_extraction_id ? 'View extraction (and EHR payload if available)' : 'No extraction id available'}
                              >
                                Extraction
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Empty State */}
            {!loading && recordings.length === 0 && !error && (
              <div className="text-center py-12 text-gray-500">
                No recordings found.
              </div>
            )}

            {/* Pagination */}
            {totalCount > pageSize && (
              <div className="mt-4 flex justify-between items-center">
                <button
                  onClick={() => setPage(Math.max(0, page - 1))}
                  disabled={page === 0}
                  className="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="text-sm text-gray-600">
                  Page {page + 1} of {Math.ceil(totalCount / pageSize)}
                </span>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={(page + 1) * pageSize >= totalCount}
                  className="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            )}

            {/* Reprocess Form */}
            {selectedRecording && (
              <div className="mt-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Reprocess Recording
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  Patient: {selectedRecording.patient_name || selectedRecording.patient_identifier || 'Unknown'} |
                  Date: {formatDate(selectedRecording.consultation_datetime)}
                </p>

                {selectedRecording.status === 'validation_failed' && (
                  <div className={`mb-4 p-3 border rounded-lg text-sm ${selectedRecording.chunk_count > 0 ? 'bg-yellow-50 border-yellow-200 text-yellow-800' : 'bg-red-50 border-red-200 text-red-700'}`}>
                    {selectedRecording.chunk_count > 0 ? (
                      <>
                        <strong>Warning:</strong> This recording failed quality validation but has {selectedRecording.chunk_count} audio chunks available. You can try reprocessing.
                        {selectedRecording.error_message && (
                          <span> Original error: {selectedRecording.error_message}</span>
                        )}
                      </>
                    ) : (
                      <>
                        <strong>Cannot reprocess:</strong> This recording was rejected due to audio quality issues.
                        {selectedRecording.error_message && (
                          <span> Reason: {selectedRecording.error_message}</span>
                        )}
                      </>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                  {/* Reprocess Mode */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Reprocess Mode
                    </label>
                    <select
                      value={reprocessMode}
                      onChange={(e) => setReprocessMode(e.target.value as 'new_extraction' | 'reprocess_transcript')}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white text-gray-900"
                    >
                      <option
                        value="new_extraction"
                        disabled={!selectedRecording.has_audio && selectedRecording.chunk_count === 0}
                      >
                        Full Extraction {!selectedRecording.has_audio && selectedRecording.chunk_count === 0 && '(No audio)'}
                      </option>
                      <option
                        value="reprocess_transcript"
                        disabled={!selectedRecording.has_transcript || selectedRecording.status === 'RECORDING'}
                      >
                        Reprocess Transcript {selectedRecording.status === 'RECORDING'
                          ? '(Not available for abandoned)'
                          : !selectedRecording.has_transcript
                            ? '(No transcript)'
                            : ''}
                      </option>
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      {selectedRecording.status === 'RECORDING'
                        ? 'Abandoned recordings require full re-extraction from audio chunks'
                        : reprocessMode === 'reprocess_transcript'
                          ? 'Fast: Uses existing transcript'
                          : 'Full: Re-transcribes audio'}
                    </p>
                  </div>

                  {/* Template */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Template
                    </label>
                    <select
                      value={reprocessTemplate}
                      onChange={(e) => setReprocessTemplate(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white text-gray-900"
                    >
                      {templates.map((t, index) => (
                        <option key={t.id || `template-${index}`} value={t.template_code}>
                          {t.template_name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Processing Mode */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Processing Mode
                    </label>
                    <select
                      value={reprocessProcessingMode}
                      onChange={(e) => setReprocessProcessingMode(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white text-gray-900"
                    >
                      {processingModes.map((mode, index) => (
                        <option key={mode.mode_code || `mode-${index}`} value={mode.mode_code}>
                          {mode.mode_name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Extraction Mode */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Extraction Mode
                    </label>
                    <select
                      value={reprocessExtractionMode}
                      onChange={(e) => setReprocessExtractionMode(e.target.value as 'core' | 'additional' | 'full')}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white text-gray-900"
                    >
                      <option value="full">Full (Core + Additional)</option>
                      <option value="core">Core Only</option>
                      <option value="additional">Additional Only</option>
                    </select>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex justify-end gap-3">
                  <button
                    onClick={() => setSelectedRecording(null)}
                    className="px-4 py-2 text-sm bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleReprocess}
                    disabled={reprocessing || (selectedRecording.status === 'validation_failed' && selectedRecording.chunk_count === 0) || (!selectedRecording.has_audio && selectedRecording.chunk_count === 0 && reprocessMode === 'new_extraction')}
                    className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                  >
                    {reprocessing && (
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    )}
                    {reprocessing ? 'Starting...' : 'Start Reprocessing'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Audio Player Modal */}
      {audioPlaybackRecording && audioPlaybackRecording.last_submission_id && (
        <AudioPlayerModal
          isOpen={!!audioPlaybackRecording}
          onClose={() => { setAudioPlaybackRecording(null); setAudioPlaybackType('original'); }}
          submissionId={audioPlaybackRecording.last_submission_id}
          patientName={audioPlaybackRecording.patient_name || audioPlaybackRecording.patient_identifier || 'Unknown Patient'}
          consultationDate={audioPlaybackRecording.consultation_datetime}
          accessToken={accessToken}
          audioType={audioPlaybackType}
        />
      )}

      {/* Transcript / Extraction Viewer Modal */}
      <ExtractionViewerModal
        isOpen={!!viewerRecording}
        onClose={() => setViewerRecording(null)}
        extractionId={viewerRecording?.last_extraction_id ?? null}
        mode={viewerMode}
        accessToken={accessToken}
        patientName={viewerRecording?.patient_name ?? viewerRecording?.patient_identifier ?? null}
        consultationDatetime={viewerRecording?.consultation_datetime ?? null}
      />
    </div>
  );
}

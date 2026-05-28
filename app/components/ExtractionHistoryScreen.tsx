'use client';

/**
 * Extraction History Screen
 *
 * Displays a list of past extractions with LLM usage data.
 * Features:
 * - Paginated list of extractions
 * - LLM token usage and cost summary per extraction
 * - Click to view full extraction details
 * - Filter by doctor and consultation type
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { authGet } from '@lib/apiClient';
import ExtractionPhotosSection from './ExtractionPhotosSection';

// Types
interface LLMUsageItem {
  id: string;
  call_type: string;
  call_subtype?: string;
  model: string;
  prompt_token_count?: number;
  cached_content_token_count?: number;
  candidates_token_count?: number;
  total_token_count?: number;
  input_cost_usd?: number;
  output_cost_usd?: number;
  cache_savings_usd?: number;
  total_cost_usd?: number;
  api_duration_seconds?: number;
  cache_hit?: boolean;
  cache_hit_ratio?: number;
  response_status?: string;
  created_at: string;
}

interface ExtractionHistoryItem {
  extraction_id: string;
  session_id?: string;
  submission_id?: string;
  consultation_type_id: string;
  consultation_type_name?: string;
  template_code?: string;
  doctor_id?: string;
  doctor_name?: string;
  patient_id?: string;
  extraction_mode: string;
  segment_count: number;
  is_edited: boolean;
  edit_count: number;
  created_at: string;
  // Retry indicator
  is_retry: boolean;
  retry_number?: number;  // 1 for first retry, 2 for second, etc.
  recording_duration_seconds?: number;
  stitching_time_seconds?: number;
  transcription_time_seconds?: number;
  extraction_time_seconds?: number;
  total_processing_time_seconds?: number;
  total_llm_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cached_tokens: number;
  total_cost_usd: number;
  total_cache_savings_usd: number;
  llm_usage?: LLMUsageItem[];
}

interface ExtractionDetails {
  extraction_id: string;
  session_id?: string;
  consultation_type_id: string;
  consultation_type_name?: string;
  template_code?: string;
  doctor_id?: string;
  doctor_name?: string;
  patient_id?: string;
  extraction_mode: string;
  segment_count: number;
  is_edited: boolean;
  edit_count: number;
  created_at: string;
  transcript_text?: string;
  extraction_data?: Record<string, unknown>;
  stitching_time_seconds?: number;
  transcription_time_seconds?: number;
  extraction_time_seconds?: number;
  total_processing_time_seconds?: number;
  llm_usage_summary: {
    total_calls: number;
    total_input_tokens: number;
    total_output_tokens: number;
    total_cached_tokens: number;
    total_cost_usd: number;
    total_cache_savings_usd: number;
    avg_cache_hit_ratio: number;
  };
  llm_usage: LLMUsageItem[];
}

interface Doctor {
  id: string;
  full_name: string;
}

interface ConsultationType {
  id: string;
  type_name: string;
}

export function ExtractionHistoryScreen() {
  const { getAccessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [extractions, setExtractions] = useState<ExtractionHistoryItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [hasMore, setHasMore] = useState(false);

  // Filters
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [consultationTypes, setConsultationTypes] = useState<ConsultationType[]>([]);
  const [selectedDoctorId, setSelectedDoctorId] = useState<string>('');
  const [selectedConsultationTypeId, setSelectedConsultationTypeId] = useState<string>('');

  // Detail view
  const [selectedExtraction, setSelectedExtraction] = useState<ExtractionDetails | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  // Load filters on mount
  useEffect(() => {
    loadFilters();
  }, []);

  // Load extractions when filters or page change
  useEffect(() => {
    loadExtractions();
  }, [page, selectedDoctorId, selectedConsultationTypeId]);

  const loadFilters = async () => {
    try {
      const accessToken = getAccessToken();

      // Load doctors
      const docRes = await authGet('/api/v1/doctors', accessToken);
      if (docRes.ok) {
        const docData = await docRes.json();
        setDoctors(docData.doctors || []);
      }

      // Load consultation types
      const ctRes = await authGet('/api/v1/summary/consultation-types', accessToken);
      if (ctRes.ok) {
        const ctData = await ctRes.json();
        setConsultationTypes(ctData.consultation_types || []);
      }
    } catch (err) {
      console.error('Failed to load filters:', err);
    }
  };

  const loadExtractions = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
      });

      if (selectedDoctorId) {
        params.append('doctor_id', selectedDoctorId);
      }
      if (selectedConsultationTypeId) {
        params.append('consultation_type_id', selectedConsultationTypeId);
      }

      const res = await authGet(`/api/v1/extractions/history?${params}`, getAccessToken());

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();
      setExtractions(data.extractions || []);
      setTotalCount(data.total_count || 0);
      setHasMore(data.has_more || false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load extractions');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, selectedDoctorId, selectedConsultationTypeId]); // getAccessToken is stable from useAuth

  const loadExtractionDetails = async (extractionId: string) => {
    setLoadingDetails(true);

    try {
      const res = await authGet(
        `/api/v1/extractions/history/${extractionId}/details`,
        getAccessToken()
      );

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();
      setSelectedExtraction(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load extraction details');
    } finally {
      setLoadingDetails(false);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatCost = (cost: number) => {
    if (cost < 0.01) {
      return `$${cost.toFixed(4)}`;
    }
    return `$${cost.toFixed(2)}`;
  };

  const formatTokens = (tokens: number) => {
    if (tokens >= 1000) {
      return `${(tokens / 1000).toFixed(1)}K`;
    }
    return tokens.toString();
  };

  const formatDuration = (seconds?: number) => {
    if (seconds === undefined || seconds === null) return '-';
    return `${seconds.toFixed(1)}s`;
  };

  const handleFilterChange = () => {
    setPage(1); // Reset to first page when filters change
  };

  // Render extraction list
  const renderExtractionList = () => (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-6">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-sm text-slate-400 mb-1">Doctor</label>
          <select
            value={selectedDoctorId}
            onChange={(e) => {
              setSelectedDoctorId(e.target.value);
              handleFilterChange();
            }}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Doctors</option>
            {doctors.map((doc) => (
              <option key={doc.id} value={doc.id}>
                {doc.full_name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 min-w-[200px]">
          <label className="block text-sm text-slate-400 mb-1">Consultation Type</label>
          <select
            value={selectedConsultationTypeId}
            onChange={(e) => {
              setSelectedConsultationTypeId(e.target.value);
              handleFilterChange();
            }}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Types</option>
            {consultationTypes.map((ct) => (
              <option key={ct.id} value={ct.id}>
                {ct.type_name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-end">
          <button
            onClick={() => loadExtractions()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Results count */}
      <div className="text-sm text-slate-400 mb-4">
        Showing {extractions.length} of {totalCount} extractions
      </div>

      {/* Extraction cards */}
      {loading ? (
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-2 text-slate-400">Loading extractions...</p>
        </div>
      ) : extractions.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          No extractions found. Complete a recording to see history here.
        </div>
      ) : (
        <div className="space-y-3">
          {extractions.map((ext) => (
            <div
              key={ext.extraction_id}
              onClick={() => loadExtractionDetails(ext.extraction_id)}
              className="bg-slate-700/50 rounded-lg p-4 border border-slate-600 hover:border-blue-500 cursor-pointer transition-colors"
            >
              <div className="flex flex-wrap justify-between items-start gap-4">
                {/* Left: Basic info */}
                <div className="flex-1 min-w-[200px]">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-white font-medium">
                      {ext.consultation_type_name || ext.template_code || 'Unknown Type'}
                    </span>
                    {ext.is_retry && (
                      <span className="px-2 py-0.5 bg-blue-600/30 text-blue-400 text-xs rounded">
                        Retry {ext.retry_number && ext.retry_number > 1 ? `#${ext.retry_number}` : ''}
                      </span>
                    )}
                    {ext.is_edited && (
                      <span className="px-2 py-0.5 bg-yellow-600/30 text-yellow-400 text-xs rounded">
                        Edited ({ext.edit_count}x)
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-slate-400">
                    {ext.doctor_name || 'Unknown Doctor'} • {formatDate(ext.created_at)}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {ext.extraction_mode} mode • {ext.segment_count} segments
                    {ext.recording_duration_seconds != null && ext.recording_duration_seconds > 0 && (
                      <span> • {(ext.recording_duration_seconds / 60).toFixed(1)} min</span>
                    )}
                  </div>
                  <div className="text-xs text-slate-600 mt-1 font-mono">
                    E:{ext.extraction_id.slice(0, 8)}
                    {ext.session_id && <span> • S:{ext.session_id.slice(0, 8)}</span>}
                    {ext.submission_id && <span> • Sub:{ext.submission_id.slice(0, 8)}</span>}
                  </div>
                </div>

                {/* Middle: Recording Duration */}
                <div className="min-w-[100px]">
                  <div className="text-xs text-slate-500 mb-1">Recording</div>
                  <div className="text-sm text-blue-400">
                    {ext.recording_duration_seconds != null && ext.recording_duration_seconds > 0
                      ? ext.recording_duration_seconds >= 3600
                        ? `${(ext.recording_duration_seconds / 3600).toFixed(1)} hrs`
                        : `${(ext.recording_duration_seconds / 60).toFixed(1)} min`
                      : '-'}
                  </div>
                </div>

                {/* Middle: Processing times */}
                <div className="min-w-[120px]">
                  <div className="text-xs text-slate-500 mb-1">Processing Time</div>
                  <div className="text-sm text-slate-300">
                    {formatDuration(ext.total_processing_time_seconds)}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Trans: {formatDuration(ext.transcription_time_seconds)} |
                    Ext: {formatDuration(ext.extraction_time_seconds)}
                  </div>
                </div>

                {/* Right: LLM Usage */}
                <div className="min-w-[150px] text-right">
                  <div className="text-xs text-slate-500 mb-1">LLM Usage</div>
                  <div className="text-sm">
                    <span className="text-green-400">{formatCost(ext.total_cost_usd)}</span>
                    {ext.total_cache_savings_usd > 0 && (
                      <span className="text-xs text-emerald-500 ml-1">
                        (saved {formatCost(ext.total_cache_savings_usd)})
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {formatTokens(ext.total_input_tokens)} in / {formatTokens(ext.total_output_tokens)} out
                  </div>
                  <div className="text-xs text-slate-500">
                    {ext.total_llm_calls} API calls
                    {ext.total_cached_tokens > 0 && (
                      <span className="text-cyan-400 ml-1">
                        ({formatTokens(ext.total_cached_tokens)} cached)
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalCount > pageSize && (
        <div className="flex justify-center gap-2 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white transition-colors"
          >
            Previous
          </button>
          <span className="px-4 py-2 text-slate-400">
            Page {page} of {Math.ceil(totalCount / pageSize)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasMore}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );

  // Render extraction details
  const renderExtractionDetails = () => {
    if (!selectedExtraction) return null;

    const ext = selectedExtraction;

    return (
      <div className="space-y-6">
        {/* Header with back button */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => setSelectedExtraction(null)}
            className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors"
          >
            &larr; Back
          </button>
          <h2 className="text-xl font-semibold text-white">
            {ext.consultation_type_name || ext.template_code || 'Extraction Details'}
          </h2>
        </div>

        {/* Metadata */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-slate-700/50 rounded-lg p-3">
            <div className="text-xs text-slate-500">Doctor</div>
            <div className="text-sm text-white">{ext.doctor_name || 'Unknown'}</div>
          </div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <div className="text-xs text-slate-500">Created</div>
            <div className="text-sm text-white">{formatDate(ext.created_at)}</div>
          </div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <div className="text-xs text-slate-500">Mode</div>
            <div className="text-sm text-white">{ext.extraction_mode}</div>
          </div>
        </div>

        {/* LLM Usage Summary */}
        <div className="bg-slate-700/50 rounded-lg p-4">
          <h3 className="text-lg font-medium text-white mb-3">LLM Usage Summary</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-slate-500">Total Cost</div>
              <div className="text-lg text-green-400 font-medium">
                {formatCost(ext.llm_usage_summary.total_cost_usd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Cache Savings</div>
              <div className="text-lg text-emerald-400 font-medium">
                {formatCost(ext.llm_usage_summary.total_cache_savings_usd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Input Tokens</div>
              <div className="text-lg text-blue-400 font-medium">
                {formatTokens(ext.llm_usage_summary.total_input_tokens)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Output Tokens</div>
              <div className="text-lg text-purple-400 font-medium">
                {formatTokens(ext.llm_usage_summary.total_output_tokens)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Cached Tokens</div>
              <div className="text-lg text-cyan-400 font-medium">
                {formatTokens(ext.llm_usage_summary.total_cached_tokens)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">API Calls</div>
              <div className="text-lg text-white font-medium">
                {ext.llm_usage_summary.total_calls}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Avg Cache Hit</div>
              <div className="text-lg text-yellow-400 font-medium">
                {ext.llm_usage_summary.avg_cache_hit_ratio}%
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Processing Time</div>
              <div className="text-lg text-orange-400 font-medium">
                {formatDuration(ext.total_processing_time_seconds)}
              </div>
            </div>
          </div>
        </div>

        {/* LLM API Calls */}
        <div className="bg-slate-700/50 rounded-lg p-4">
          <h3 className="text-lg font-medium text-white mb-3">API Calls Breakdown</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 border-b border-slate-600">
                  <th className="text-left py-2 px-2">Type</th>
                  <th className="text-left py-2 px-2">Model</th>
                  <th className="text-right py-2 px-2">Input</th>
                  <th className="text-right py-2 px-2">Output</th>
                  <th className="text-right py-2 px-2">Cached</th>
                  <th className="text-right py-2 px-2">Cost</th>
                  <th className="text-right py-2 px-2">Duration</th>
                  <th className="text-center py-2 px-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {ext.llm_usage.map((usage) => (
                  <tr key={usage.id} className="border-b border-slate-700/50 text-slate-300">
                    <td className="py-2 px-2">
                      <div className="font-medium text-white">{usage.call_type}</div>
                      {usage.call_subtype && (
                        <div className="text-xs text-slate-500">{usage.call_subtype}</div>
                      )}
                    </td>
                    <td className="py-2 px-2 text-slate-400">{usage.model}</td>
                    <td className="py-2 px-2 text-right text-blue-400">
                      {formatTokens(usage.prompt_token_count || 0)}
                    </td>
                    <td className="py-2 px-2 text-right text-purple-400">
                      {formatTokens(usage.candidates_token_count || 0)}
                    </td>
                    <td className="py-2 px-2 text-right">
                      {usage.cache_hit ? (
                        <span className="text-cyan-400">
                          {formatTokens(usage.cached_content_token_count || 0)}
                          <span className="text-xs ml-1">
                            ({usage.cache_hit_ratio?.toFixed(0)}%)
                          </span>
                        </span>
                      ) : (
                        <span className="text-slate-500">-</span>
                      )}
                    </td>
                    <td className="py-2 px-2 text-right text-green-400">
                      {formatCost(usage.total_cost_usd || 0)}
                    </td>
                    <td className="py-2 px-2 text-right text-orange-400">
                      {formatDuration(usage.api_duration_seconds)}
                    </td>
                    <td className="py-2 px-2 text-center">
                      {usage.response_status === 'success' ? (
                        <span className="text-green-500">&#10003;</span>
                      ) : (
                        <span className="text-red-500">&#10007;</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Transcript */}
        {ext.transcript_text && (
          <div className="bg-slate-700/50 rounded-lg p-4">
            <h3 className="text-lg font-medium text-white mb-3">Transcript</h3>
            <div className="max-h-60 overflow-y-auto">
              <p className="text-sm text-slate-300 whitespace-pre-wrap">{ext.transcript_text}</p>
            </div>
          </div>
        )}

        {/* Extraction Data */}
        {ext.extraction_data && (
          <div className="bg-slate-700/50 rounded-lg p-4">
            <h3 className="text-lg font-medium text-white mb-3">Extraction Data</h3>
            <div className="max-h-96 overflow-y-auto">
              <pre className="text-xs text-slate-300 overflow-x-auto">
                {JSON.stringify(ext.extraction_data, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Photo attachments */}
        {ext.extraction_id && (
          <ExtractionPhotosSection extractionId={ext.extraction_id} />
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Error display */}
      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded-lg">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-4 text-red-400 hover:text-red-200"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Loading overlay for details */}
      {loadingDetails && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
            <p className="mt-2 text-slate-300">Loading details...</p>
          </div>
        </div>
      )}

      {/* Main content */}
      {selectedExtraction ? renderExtractionDetails() : renderExtractionList()}
    </div>
  );
}

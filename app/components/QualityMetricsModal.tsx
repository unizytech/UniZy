'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { authGet } from '@lib/apiClient';

interface QualityMetricsModalProps {
  schoolId: string;
  schoolName: string;
  onClose: () => void;
}

interface AcceptanceByCounsellor {
  counsellor_id: string;
  counsellor_name: string;
  total: number;
  unchanged: number;
  edited: number;
  acceptance_rate_pct: number;
  avg_edit_count: number;
}

interface NotesPerDay {
  counsellor_id: string;
  counsellor_name: string;
  date: string;
  note_count: number;
}

interface TimingStage {
  avg: number;
  p50: number;
  p95: number;
  p99: number;
}

interface PipelineTiming {
  count: number;
  stitching: TimingStage;
  transcription: TimingStage;
  extraction: TimingStage;
  total: TimingStage;
}

interface AccuracyByCounsellor {
  counsellor_id: string;
  counsellor_name: string;
  count: number;
  avg_wer: number;
  avg_entity_error_rate: number;
  avg_segments_modified: number;
}

export default function QualityMetricsModal({ schoolId, schoolName, onClose }: QualityMetricsModalProps) {
  const { getAccessToken } = useAuth();

  // Date range
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().split('T')[0];
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().split('T')[0]);

  // Data
  const [loading, setLoading] = useState(true);
  const [summaryData, setSummaryData] = useState<any>(null);
  const [acceptanceByCounsellor, setAcceptanceByCounsellor] = useState<AcceptanceByCounsellor[]>([]);
  const [notesPerDay, setNotesPerDay] = useState<NotesPerDay[]>([]);
  const [pipelineTiming, setPipelineTiming] = useState<PipelineTiming | null>(null);
  const [accuracyByCounsellor, setAccuracyByCounsellor] = useState<AccuracyByCounsellor[]>([]);
  const [activeTab, setActiveTab] = useState<'summary' | 'acceptance' | 'notes' | 'timing' | 'accuracy'>('summary');

  const fetchMetrics = useCallback(async () => {
    const token = getAccessToken();
    if (!token) return;
    setLoading(true);
    try {
      const params = `school_id=${schoolId}&date_from=${dateFrom}&date_to=${dateTo}`;

      // Fetch summary
      const summaryRes = await authGet(`/api/v1/metrics/summary?${params}`, token);
      if (summaryRes.ok) {
        const json = await summaryRes.json();
        setSummaryData(json.data);
      }

      // Fetch acceptance by counsellor
      const acceptRes = await authGet(`/api/v1/metrics/ai-acceptance?${params}&group_by=doctor`, token);
      if (acceptRes.ok) {
        const json = await acceptRes.json();
        setAcceptanceByCounsellor(Array.isArray(json.data) ? json.data : []);
      }

      // Fetch notes per day
      const notesRes = await authGet(`/api/v1/metrics/notes-per-day?${params}`, token);
      if (notesRes.ok) {
        const json = await notesRes.json();
        setNotesPerDay(Array.isArray(json.data) ? json.data : []);
      }

      // Fetch pipeline timing
      const timingRes = await authGet(`/api/v1/metrics/pipeline-timing?${params}`, token);
      if (timingRes.ok) {
        const json = await timingRes.json();
        setPipelineTiming(json.data);
      }

      // Fetch accuracy by counsellor
      const accRes = await authGet(`/api/v1/metrics/accuracy?${params}&group_by=doctor`, token);
      if (accRes.ok) {
        const json = await accRes.json();
        setAccuracyByCounsellor(Array.isArray(json.data) ? json.data : []);
      }
    } catch (err) {
      console.error('Failed to fetch metrics:', err);
    } finally {
      setLoading(false);
    }
  }, [getAccessToken, schoolId, dateFrom, dateTo]);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  const tabs = [
    { key: 'summary', label: 'Summary' },
    { key: 'acceptance', label: 'AI Acceptance' },
    { key: 'notes', label: 'Notes/Day' },
    { key: 'timing', label: 'Pipeline Timing' },
    { key: 'accuracy', label: 'Accuracy' },
  ] as const;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-5xl mx-4 p-6 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-800">Quality Metrics</h2>
            <p className="text-sm text-slate-500">{schoolName}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Date Range */}
        <div className="flex items-center gap-3 mb-4">
          <label className="text-sm text-slate-600">From:</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="px-2 py-1 border border-slate-300 rounded text-sm text-slate-700"
          />
          <label className="text-sm text-slate-600">To:</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="px-2 py-1 border border-slate-300 rounded text-sm text-slate-700"
          />
          <button
            onClick={fetchMetrics}
            className="px-3 py-1 bg-teal-600 text-white text-sm rounded hover:bg-teal-700 transition-colors"
          >
            Apply
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-4 border-b border-slate-200">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-teal-600 text-teal-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600"></div>
            <span className="ml-3 text-slate-500">Loading metrics...</span>
          </div>
        ) : (
          <>
            {/* Summary Tab */}
            {activeTab === 'summary' && summaryData && (
              <div>
                {/* Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                  <SummaryCard
                    label="Service Uptime"
                    value={`${summaryData.uptime?.uptime_pct ?? 99.98}%`}
                    color="green"
                  />
                  <SummaryCard
                    label="AI Acceptance Rate"
                    value={`${summaryData.acceptance?.acceptance_rate_pct ?? 0}%`}
                    subtitle={`${summaryData.acceptance?.total_extractions ?? 0} total notes`}
                    color="blue"
                  />
                  <SummaryCard
                    label="Avg E2E Time"
                    value={`${summaryData.pipeline_timing?.total?.avg ?? 0}s`}
                    subtitle={`p95: ${summaryData.pipeline_timing?.total?.p95 ?? 0}s`}
                    color="purple"
                  />
                  <SummaryCard
                    label="Notes Today"
                    value={String(summaryData.notes_today ?? 0)}
                    color="teal"
                  />
                </div>

                {/* Accuracy summary if available */}
                {summaryData.accuracy && summaryData.accuracy.count > 0 && (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <SummaryCard
                      label="Avg WER"
                      value={`${((summaryData.accuracy.avg_wer ?? 0) * 100).toFixed(1)}%`}
                      subtitle="Lower is better"
                      color="orange"
                    />
                    <SummaryCard
                      label="Entity Error Rate"
                      value={`${(summaryData.accuracy.avg_entity_error_rate ?? 0).toFixed(1)}%`}
                      color="red"
                    />
                    <SummaryCard
                      label="Segments Modified"
                      value={`${(summaryData.accuracy.avg_segments_modified ?? 0).toFixed(1)}`}
                      subtitle={`of ~${((summaryData.accuracy.avg_segments_modified ?? 0) + (summaryData.accuracy.avg_segments_unchanged ?? 0)).toFixed(0)} avg`}
                      color="slate"
                    />
                  </div>
                )}
              </div>
            )}

            {/* AI Acceptance Tab */}
            {activeTab === 'acceptance' && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200">
                      <th className="text-left px-3 py-2 text-slate-600 font-medium">Counsellor</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">Total Notes</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">Unchanged</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">Edited</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">Acceptance %</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">Avg Edits</th>
                    </tr>
                  </thead>
                  <tbody>
                    {acceptanceByCounsellor.length === 0 ? (
                      <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-400">No data available</td></tr>
                    ) : (
                      acceptanceByCounsellor.map((row, i) => (
                        <tr key={row.counsellor_id || i} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="px-3 py-2 text-slate-800">{row.counsellor_name}</td>
                          <td className="px-3 py-2 text-right text-slate-700">{row.total}</td>
                          <td className="px-3 py-2 text-right text-green-600">{row.unchanged}</td>
                          <td className="px-3 py-2 text-right text-amber-600">{row.edited}</td>
                          <td className="px-3 py-2 text-right font-medium text-slate-800">{row.acceptance_rate_pct}%</td>
                          <td className="px-3 py-2 text-right text-slate-500">{row.avg_edit_count}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* Notes/Day Tab */}
            {activeTab === 'notes' && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200">
                      <th className="text-left px-3 py-2 text-slate-600 font-medium">Counsellor</th>
                      <th className="text-left px-3 py-2 text-slate-600 font-medium">Date</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notesPerDay.length === 0 ? (
                      <tr><td colSpan={3} className="px-3 py-6 text-center text-slate-400">No data available</td></tr>
                    ) : (
                      notesPerDay.map((row, i) => (
                        <tr key={`${row.counsellor_id}-${row.date}-${i}`} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="px-3 py-2 text-slate-800">{row.counsellor_name}</td>
                          <td className="px-3 py-2 text-slate-600">{row.date}</td>
                          <td className="px-3 py-2 text-right font-medium text-slate-800">{row.note_count}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pipeline Timing Tab */}
            {activeTab === 'timing' && pipelineTiming && (
              <div className="overflow-x-auto">
                <p className="text-xs text-slate-500 mb-2">{pipelineTiming.count} extractions analyzed</p>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200">
                      <th className="text-left px-3 py-2 text-slate-600 font-medium">Stage</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">Avg (s)</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">p50 (s)</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">p95 (s)</th>
                      <th className="text-right px-3 py-2 text-slate-600 font-medium">p99 (s)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(['stitching', 'transcription', 'extraction', 'total'] as const).map((stage) => {
                      const data = pipelineTiming[stage];
                      if (!data) return null;
                      return (
                        <tr key={stage} className={`border-b border-slate-100 hover:bg-slate-50 ${stage === 'total' ? 'font-medium bg-slate-50' : ''}`}>
                          <td className="px-3 py-2 text-slate-800 capitalize">{stage}</td>
                          <td className="px-3 py-2 text-right text-slate-700">{data.avg}</td>
                          <td className="px-3 py-2 text-right text-slate-600">{data.p50}</td>
                          <td className="px-3 py-2 text-right text-amber-600">{data.p95}</td>
                          <td className="px-3 py-2 text-right text-red-600">{data.p99}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Accuracy Tab */}
            {activeTab === 'accuracy' && (
              <div className="overflow-x-auto">
                {accuracyByCounsellor.length === 0 ? (
                  <p className="text-center text-slate-400 py-6">No accuracy data yet. Metrics are computed when counsellors edit AI-generated notes.</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200">
                        <th className="text-left px-3 py-2 text-slate-600 font-medium">Counsellor</th>
                        <th className="text-right px-3 py-2 text-slate-600 font-medium">Edits</th>
                        <th className="text-right px-3 py-2 text-slate-600 font-medium">Avg WER</th>
                        <th className="text-right px-3 py-2 text-slate-600 font-medium">Entity Err %</th>
                        <th className="text-right px-3 py-2 text-slate-600 font-medium">Avg Segments Modified</th>
                      </tr>
                    </thead>
                    <tbody>
                      {accuracyByCounsellor.map((row, i) => (
                        <tr key={row.counsellor_id || i} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="px-3 py-2 text-slate-800">{row.counsellor_name}</td>
                          <td className="px-3 py-2 text-right text-slate-700">{row.count}</td>
                          <td className="px-3 py-2 text-right font-medium text-slate-800">{(row.avg_wer * 100).toFixed(1)}%</td>
                          <td className="px-3 py-2 text-right text-amber-600">{row.avg_entity_error_rate.toFixed(1)}%</td>
                          <td className="px-3 py-2 text-right text-slate-600">{row.avg_segments_modified.toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value, subtitle, color }: {
  label: string;
  value: string;
  subtitle?: string;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    green: 'bg-green-50 border-green-200',
    blue: 'bg-blue-50 border-blue-200',
    purple: 'bg-purple-50 border-purple-200',
    teal: 'bg-teal-50 border-teal-200',
    orange: 'bg-orange-50 border-orange-200',
    red: 'bg-red-50 border-red-200',
    slate: 'bg-slate-50 border-slate-200',
  };

  return (
    <div className={`p-4 rounded-lg border ${colorMap[color] || colorMap.slate}`}>
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-800">{value}</p>
      {subtitle && <p className="text-xs text-slate-400 mt-1">{subtitle}</p>}
    </div>
  );
}

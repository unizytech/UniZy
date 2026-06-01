'use client';

/**
 * POC Metrics Screen
 *
 * Admin screen for downloading/viewing the POC evaluation metrics:
 *   - Tracker (per-consultation)
 *   - Aggregate (per-day rollup)
 *   - Doctor_All (timings per session for selected counsellor)
 *   - Attendant_Nurse (timings per session for selected assistant)
 *
 * Filters: School + (optional) Counsellor + (optional) Assistant + start/end date.
 * Download: single .xlsx with all 4 sheets via /api/v1/poc-metrics/export.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@lib/auth';
import { authGet } from '@lib/apiClient';
import {
  fetchTracker, fetchAggregate, fetchTimings, downloadPocMetricsExcel,
  type TrackerResponse, type AggregateResponse, type TimingsResponse,
  type PocMetricsFilters, type MetricCode,
} from '@lib/pocMetricsApi';
import { getCounsellors, type Counsellor } from '@/services/counsellorApi';
import { PocMetricsDetailModal } from './PocMetricsDetailModal';

// Column label (Tracker) → drill-down metric code
const TRACKER_COL_TO_METRIC: Record<string, MetricCode> = {
  'Rx error, if any': 'rx_error',
  'Diagnosis error, if any': 'diagnosis_error',
  'Investigation error, if any': 'investigation_error',
  'Dates error, if any': 'dates_error',
  'Additive edits, if any': 'additive_edits',
  'Major edits, if any': 'major_edits',
  'Minor edits, if any': 'minor_edits',
};

// Aggregate metric label → drill-down code
const AGG_METRIC_TO_CODE: Record<string, MetricCode> = {
  'Minor edits (count)': 'minor_edits',
  'Major edits (count)': 'major_edits',
  'Additive edits (count)': 'additive_edits',
  'Wrong drug / dose (count)': 'rx_error',
  'Wrong diagnosis (count)': 'diagnosis_error',
  'Wrong lab value / units (count)': 'investigation_error',
  'Wrong dates / duration (count)': 'dates_error',
  'WER (%)': 'wer',
};

interface DrillDown {
  metric: MetricCode;
  sessionId?: string;
  scopeLabel: string;
}

interface School { id: string; school_name: string; school_code?: string }
interface Assistant { id: string; full_name: string; email?: string; school_id?: string }

type Tab = 'tracker' | 'aggregate' | 'doctor_all' | 'attendant_nurse';

const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

export function PocMetricsScreen() {
  const { getAccessToken } = useAuth();

  const [hospitals, setSchools] = useState<School[]>([]);
  const [doctors, setCounsellors] = useState<Counsellor[]>([]);
  const [nurses, setAssistants] = useState<Assistant[]>([]);
  const [hospitalId, setSchoolId] = useState<string>('');
  const [doctorId, setCounsellorId] = useState<string | null>(null);
  const [nurseId, setAssistantId] = useState<string>('');
  const [startDate, setStartDate] = useState<string>(today());
  const [endDate, setEndDate] = useState<string>(today());

  const [tab, setTab] = useState<Tab>('tracker');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tracker, setTracker] = useState<TrackerResponse | null>(null);
  const [aggregate, setAggregate] = useState<AggregateResponse | null>(null);
  const [timings, setTimings] = useState<TimingsResponse | null>(null);
  const [drillDown, setDrillDown] = useState<DrillDown | null>(null);

  const filters: PocMetricsFilters | null = useMemo(() => {
    if (!hospitalId || !startDate || !endDate) return null;
    return {
      hospitalId,
      doctorId: doctorId || undefined,
      nurseId: nurseId || undefined,
      startDate,
      endDate,
    };
  }, [hospitalId, doctorId, nurseId, startDate, endDate]);

  // Load schools + assistants once
  useEffect(() => {
    (async () => {
      const token = getAccessToken();
      if (!token) return;
      // Schools: GET /api/v1/counsellors/schools → { success, schools: [...] }
      try {
        const res = await authGet('/api/v1/counsellors/schools', token);
        if (res.ok) {
          const data = await res.json();
          const list = Array.isArray(data?.schools) ? data.schools : (Array.isArray(data) ? data : []);
          setSchools(list);
        }
      } catch { /* ignore */ }
      // Assistants: GET /api/v1/assistants → { success, assistants: [...] }
      try {
        const res = await authGet('/api/v1/assistants?active_only=true', token);
        if (res.ok) {
          const data = await res.json();
          const list = Array.isArray(data?.assistants) ? data.assistants : (Array.isArray(data) ? data : []);
          setAssistants(list);
        }
      } catch { /* ignore */ }
      // Counsellors
      try {
        const list = await getCounsellors(true, token);
        setCounsellors(Array.isArray(list) ? list : []);
      } catch { /* ignore */ }
    })();
  }, [getAccessToken]);

  const doctorsForSchool = useMemo(() => {
    if (!Array.isArray(doctors)) return [];
    if (!hospitalId) return doctors;
    return doctors.filter(d => !d.school_id || d.school_id === hospitalId);
  }, [doctors, hospitalId]);

  const nursesForSchool = useMemo(() => {
    if (!Array.isArray(nurses)) return [];
    if (!hospitalId) return nurses;
    return nurses.filter(n => !n.school_id || n.school_id === hospitalId);
  }, [nurses, hospitalId]);

  const fetchAll = useCallback(async () => {
    if (!filters) return;
    setLoading(true);
    setError(null);
    const token = getAccessToken();
    try {
      const [t, a, tm] = await Promise.all([
        fetchTracker(filters, token),
        fetchAggregate(filters, token),
        fetchTimings(filters, token),
      ]);
      setTracker(t);
      setAggregate(a);
      setTimings(tm);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load metrics');
    } finally {
      setLoading(false);
    }
  }, [filters, getAccessToken]);

  const onDownload = async () => {
    if (!filters) return;
    setExporting(true);
    setError(null);
    try {
      await downloadPocMetricsExcel(filters, getAccessToken());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  // --- Summary cards ---
  const totalConsultations = tracker?.count ?? 0;
  const avgDuration = useMemo(() => {
    if (!tracker?.rows?.length) return 0;
    const sum = tracker.rows.reduce((s, r) => s + (r['Consult Duration (min)'] || 0), 0);
    return +(sum / tracker.rows.length).toFixed(2);
  }, [tracker]);
  const avgReportGen = useMemo(() => {
    if (!tracker?.rows?.length) return 0;
    const vals = tracker.rows.map(r => r['Report Gen. Time (sec)']).filter((v): v is number => v !== null);
    if (!vals.length) return 0;
    return +(vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(2);
  }, [tracker]);
  const totalErrors = useMemo(() => {
    if (!tracker?.rows?.length) return 0;
    return tracker.rows.reduce((s, r) =>
      s + (r['Rx error, if any'] || 0)
        + (r['Diagnosis error, if any'] || 0)
        + (r['Investigation error, if any'] || 0)
        + (r['Dates error, if any'] || 0), 0);
  }, [tracker]);

  const inputCls = "w-full bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500";
  const labelCls = "block text-sm font-medium text-slate-300 mb-1";

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6">
      <h1 className="text-2xl font-semibold text-white">POC Metrics</h1>

      {/* ---- Filters ---- */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div>
            <label className={labelCls}>School</label>
            <select
              value={hospitalId}
              onChange={(e) => {
                setSchoolId(e.target.value);
                setCounsellorId(null);
                setAssistantId('');
              }}
              className={inputCls}
            >
              <option value="">Select school...</option>
              {hospitals.map(h => (
                <option key={h.id} value={h.id}>{h.school_name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelCls}>Counsellor (optional)</label>
            <select
              value={doctorId || ''}
              onChange={(e) => setCounsellorId(e.target.value || null)}
              disabled={!hospitalId}
              className={`${inputCls} disabled:opacity-50`}
            >
              <option value="">— all counsellors —</option>
              {doctorsForSchool.map(d => (
                <option key={d.id} value={d.id}>
                  {d.full_name}{d.specialization ? ` (${d.specialization})` : ''}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelCls}>Assistant (optional)</label>
            <select
              value={nurseId}
              onChange={(e) => setAssistantId(e.target.value)}
              disabled={!hospitalId}
              className={`${inputCls} disabled:opacity-50`}
            >
              <option value="">— none —</option>
              {nursesForSchool.map(n => (
                <option key={n.id} value={n.id}>{n.full_name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelCls}>Start date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className={inputCls}
            />
          </div>

          <div>
            <label className={labelCls}>End date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className={inputCls}
            />
          </div>
        </div>

        {/* Quick presets + action buttons */}
        <div className="mt-4 flex flex-wrap gap-2 items-center">
          <span className="text-sm text-slate-400">Quick:</span>
          <button onClick={() => { setStartDate(today()); setEndDate(today()); }}
            className="px-3 py-1 text-xs bg-slate-700 text-slate-200 rounded hover:bg-slate-600">Today</button>
          <button onClick={() => { setStartDate(daysAgo(6)); setEndDate(today()); }}
            className="px-3 py-1 text-xs bg-slate-700 text-slate-200 rounded hover:bg-slate-600">Last 7 days</button>
          <button onClick={() => { setStartDate(daysAgo(29)); setEndDate(today()); }}
            className="px-3 py-1 text-xs bg-slate-700 text-slate-200 rounded hover:bg-slate-600">Last 30 days</button>
          <div className="flex-1" />
          <button onClick={fetchAll} disabled={!filters || loading}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Loading...' : 'Load'}
          </button>
          <button onClick={onDownload} disabled={!filters || exporting}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50">
            {exporting ? 'Exporting...' : 'Download Excel'}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-900/30 border border-red-800 rounded">
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {/* Summary cards */}
      {tracker && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card label="Total sessions" value={totalConsultations} />
          <Card label="Avg duration (min)" value={avgDuration} />
          <Card label="Avg report gen (sec)" value={avgReportGen} />
          <Card label="Total entity errors" value={totalErrors} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-700">
        {(['tracker', 'aggregate', 'doctor_all', 'attendant_nurse'] as Tab[]).map(t => (
          <button key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium ${
              tab === t
                ? 'border-b-2 border-blue-500 text-blue-400'
                : 'text-slate-400 hover:text-white'
            }`}>
            {({
              tracker: 'Tracker',
              aggregate: 'Aggregate',
              doctor_all: 'Doctor_All',
              attendant_nurse: 'Attendant_Nurse',
            } as Record<Tab, string>)[t]}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="overflow-auto bg-slate-800 border border-slate-700 rounded-lg">
        {tab === 'tracker' && tracker && (
          <DataTable
            columns={tracker.columns}
            rows={tracker.rows as unknown as Array<Record<string, unknown>>}
            onCellClick={(col, row) => {
              const code = TRACKER_COL_TO_METRIC[col];
              if (!code) return;
              const n = Number(row[col] ?? 0);
              if (!n || n <= 0) return;
              const sid = String(row['Session ID'] ?? '');
              setDrillDown({
                metric: code,
                sessionId: sid || undefined,
                scopeLabel: `Session ${sid.slice(0, 8)}`,
              });
            }}
          />
        )}
        {tab === 'aggregate' && aggregate && (
          <AggregateTable
            data={aggregate}
            onCellClick={(metricLabel, dateIso, value) => {
              const code = AGG_METRIC_TO_CODE[metricLabel];
              if (!code) return;
              const n = Number(value ?? 0);
              if (!n || n <= 0) return;
              setDrillDown({
                metric: code,
                scopeLabel: `${dateIso}`,
              });
            }}
          />
        )}
        {tab === 'doctor_all' && timings && <DataTable columns={timings.columns} rows={timings.doctor_all as unknown as Array<Record<string, unknown>>} />}
        {tab === 'attendant_nurse' && timings && <DataTable columns={timings.columns} rows={timings.attendant_nurse as unknown as Array<Record<string, unknown>>} />}
        {!tracker && !loading && (
          <p className="p-8 text-center text-slate-400">
            Pick a school + date range and click Load.
          </p>
        )}
      </div>

      {drillDown && filters && (
        <PocMetricsDetailModal
          open={true}
          onClose={() => setDrillDown(null)}
          metric={drillDown.metric}
          filters={
            // Scope by date too when it's an aggregate click
            drillDown.sessionId
              ? filters
              : { ...filters, startDate: drillDown.scopeLabel, endDate: drillDown.scopeLabel }
          }
          sessionId={drillDown.sessionId}
          scopeLabel={drillDown.scopeLabel}
          getToken={async () => getAccessToken()}
        />
      )}
    </div>
  );
}

function Card({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-slate-700/50 border border-slate-600 p-4 rounded-lg">
      <div className="text-xs uppercase text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-white">{value}</div>
    </div>
  );
}

function DataTable({
  columns, rows, onCellClick,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  onCellClick?: (column: string, row: Record<string, unknown>) => void;
}) {
  if (!rows || rows.length === 0) {
    return <p className="p-8 text-center text-slate-400">No rows.</p>;
  }
  return (
    <table className="min-w-full text-sm">
      <thead className="bg-slate-900 sticky top-0">
        <tr>
          {columns.map(c => (
            <th key={c} className="px-3 py-2 text-left font-medium text-slate-300 border-b border-slate-700 whitespace-nowrap">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-slate-700/60 hover:bg-slate-700/40">
            {columns.map(c => {
              const clickable = !!onCellClick && c in TRACKER_COL_TO_METRIC && Number(r[c] ?? 0) > 0;
              return (
                <td
                  key={c}
                  className={`px-3 py-2 whitespace-nowrap ${
                    clickable ? 'text-blue-400 hover:text-blue-300 cursor-pointer underline' : 'text-slate-200'
                  }`}
                  onClick={clickable ? () => onCellClick!(c, r) : undefined}
                >
                  {formatCell(r[c])}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AggregateTable({
  data, onCellClick,
}: {
  data: AggregateResponse;
  onCellClick?: (metricLabel: string, dateIso: string, value: unknown) => void;
}) {
  if (!data.rows || data.rows.length === 0) {
    return <p className="p-8 text-center text-slate-400">No aggregate data.</p>;
  }
  return (
    <table className="min-w-full text-sm">
      <thead className="bg-slate-900 sticky top-0">
        <tr>
          <th className="px-3 py-2 text-left font-medium text-slate-300 border-b border-slate-700">Category</th>
          <th className="px-3 py-2 text-left font-medium text-slate-300 border-b border-slate-700">Metric</th>
          {data.dates.map((d, i) => (
            <th key={d} className="px-3 py-2 text-right font-medium text-slate-300 border-b border-slate-700 whitespace-nowrap">
              Day {i + 1}<br /><span className="text-xs font-normal text-slate-400">{d}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.rows.map((r, i) => {
          const code = AGG_METRIC_TO_CODE[r.metric as string];
          return (
            <tr key={i} className="border-b border-slate-700/60 hover:bg-slate-700/40">
              <td className="px-3 py-2 text-slate-400">{r.category}</td>
              <td className="px-3 py-2 font-medium text-white">{r.metric}</td>
              {data.dates.map(d => {
                const v = r[d];
                const clickable = !!onCellClick && !!code && Number(v ?? 0) > 0;
                return (
                  <td
                    key={d}
                    className={`px-3 py-2 text-right ${
                      clickable ? 'text-blue-400 hover:text-blue-300 cursor-pointer underline' : 'text-slate-200'
                    }`}
                    onClick={clickable ? () => onCellClick!(r.metric as string, d, v) : undefined}
                  >
                    {formatCell(v)}
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

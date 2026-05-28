/**
 * POC Metrics API client
 * Typed wrappers around /api/v1/poc-metrics/* endpoints.
 */

import { authGet } from '@lib/apiClient';

export interface PocMetricsFilters {
  hospitalId: string;
  startDate: string; // YYYY-MM-DD
  endDate: string;   // YYYY-MM-DD
  doctorId?: string;
  nurseId?: string;
}

export interface TrackerRow {
  Date: string;
  Name: string;
  'Consult ID/No/Time': string;
  'Session ID': string;
  'Consult Duration (min)': number;
  'No of Speakers': number;
  'Report Generated? (Y/N)': 'Y' | 'N';
  'Error, if any': string;
  'Report Gen. Time (sec)': number | null;
  'Edited? (Y/N)': 'Y' | 'N';
  'Rx error, if any': number;
  'Diagnosis error, if any': number;
  'Investigation error, if any': number;
  'Dates error, if any': number;
  'Additive edits, if any': number;
  'Major edits, if any': number;
  'Minor edits, if any': number;
  'Feedback, if any': string;
  'Comments, if any': string;
}

export interface TrackerResponse {
  columns: string[];
  rows: TrackerRow[];
  count: number;
}

export interface AggregateRow {
  category: string;
  metric: string;
  [dateKey: string]: string | number;
}

export interface AggregateResponse {
  dates: string[];
  metrics: Array<{ category: string; metric: string }>;
  rows: AggregateRow[];
}

export interface TimingRow {
  ist_time: string;
  sess: string;
  recorded_by: 'doctor' | 'nurse';
  template: string;
  audio_s: number;
  total_chunks: number;
  pj_status: string;
  stitch_s: number | null;
  transcribe_s: number | null;
  extract_s: number | null;
  total_pipe_s: number | null;
  pipe_to_audio_ratio: number | null;
  error: string;
}

export interface TimingsResponse {
  columns: string[];
  doctor_all: TimingRow[];
  attendant_nurse: TimingRow[];
}

function buildParams(f: PocMetricsFilters): URLSearchParams {
  const p = new URLSearchParams({
    hospital_id: f.hospitalId,
    start_date: f.startDate,
    end_date: f.endDate,
  });
  if (f.doctorId) p.append('doctor_id', f.doctorId);
  if (f.nurseId) p.append('nurse_id', f.nurseId);
  return p;
}

export async function fetchTracker(
  f: PocMetricsFilters,
  token: string | null,
): Promise<TrackerResponse> {
  const res = await authGet(`/api/v1/poc-metrics/tracker?${buildParams(f)}`, token);
  if (!res.ok) throw new Error(`tracker failed: ${res.status}`);
  return res.json();
}

export async function fetchAggregate(
  f: PocMetricsFilters,
  token: string | null,
): Promise<AggregateResponse> {
  const res = await authGet(`/api/v1/poc-metrics/aggregate?${buildParams(f)}`, token);
  if (!res.ok) throw new Error(`aggregate failed: ${res.status}`);
  return res.json();
}

export async function fetchTimings(
  f: PocMetricsFilters,
  token: string | null,
): Promise<TimingsResponse> {
  const res = await authGet(`/api/v1/poc-metrics/timings?${buildParams(f)}`, token);
  if (!res.ok) throw new Error(`timings failed: ${res.status}`);
  return res.json();
}

export type MetricCode =
  | 'major_edits' | 'minor_edits' | 'additive_edits'
  | 'rx_error' | 'diagnosis_error' | 'investigation_error' | 'dates_error'
  | 'wer';

export interface DetailRow {
  session_id: string;
  name: string;
  segment: string;
  magnitude?: 'major' | 'minor';
  additive?: boolean;
  word_change_pct?: number;
  diff?: string[];
  kind?: string;
  item?: string;
  // WER detail fields
  errors?: number;
  subs_ai_error?: number;
  dels_ai_error?: number;
  ins_ai_error?: number;
  ai_word_count?: number;
  wer?: number;
}

export interface DetailResponse {
  metric: MetricCode;
  session_id: string | null;
  rows: DetailRow[];
  count: number;
}

export async function fetchMetricDetail(
  f: PocMetricsFilters,
  metric: MetricCode,
  sessionId: string | undefined,
  token: string | null,
): Promise<DetailResponse> {
  const params = buildParams(f);
  params.append('metric', metric);
  if (sessionId) params.append('session_id', sessionId);
  const res = await authGet(`/api/v1/poc-metrics/detail?${params}`, token);
  if (!res.ok) throw new Error(`detail failed: ${res.status}`);
  return res.json();
}

export async function downloadPocMetricsExcel(
  f: PocMetricsFilters,
  token: string | null,
): Promise<void> {
  const res = await authGet(`/api/v1/poc-metrics/export?${buildParams(f)}`, token);
  if (!res.ok) throw new Error(`export failed: ${res.status}`);
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `poc_metrics_${f.startDate}_to_${f.endDate}.xlsx`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

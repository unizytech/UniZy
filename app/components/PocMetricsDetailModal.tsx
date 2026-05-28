'use client';

/**
 * POC Metrics Detail Modal
 *
 * Opens when a user clicks a non-zero count in the Tracker or Aggregate
 * tables. Shows one row per underlying edit / error, with a short
 * "orig → edited" diff snippet per row. Scope is controlled by the caller:
 *   - Tracker click → single session
 *   - Aggregate click → all sessions in the filter for that metric/day
 */

import React, { useEffect, useState } from 'react';
import { fetchMetricDetail, type DetailRow, type MetricCode, type PocMetricsFilters } from '@lib/pocMetricsApi';

const METRIC_LABEL: Record<MetricCode, string> = {
  major_edits: 'Major edits',
  minor_edits: 'Minor edits',
  additive_edits: 'Additive edits',
  rx_error: 'Rx errors',
  diagnosis_error: 'Diagnosis errors',
  investigation_error: 'Investigation errors',
  dates_error: 'Date errors',
  wer: 'WER breakdown',
};

interface Props {
  open: boolean;
  onClose: () => void;
  metric: MetricCode;
  filters: PocMetricsFilters;
  sessionId?: string;      // undefined for Aggregate clicks
  scopeLabel?: string;     // e.g. "Day 1 (2026-04-21)" or "Consultation <short>"
  getToken: () => Promise<string | null>;
}

export function PocMetricsDetailModal({
  open, onClose, metric, filters, sessionId, scopeLabel, getToken,
}: Props) {
  const [rows, setRows] = useState<DetailRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const token = await getToken();
        const res = await fetchMetricDetail(filters, metric, sessionId, token);
        if (!cancelled) setRows(res.rows);
      } catch (e) {
        if (!cancelled) setError((e as Error).message || 'Failed to load detail');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, metric, sessionId, filters, getToken]);

  if (!open) return null;

  const title = `${METRIC_LABEL[metric]}${scopeLabel ? ` — ${scopeLabel}` : ''}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-800 border border-slate-700 rounded-lg max-w-4xl w-full max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-2xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {loading && <p className="text-slate-400 text-sm">Loading…</p>}
          {error && <p className="text-red-400 text-sm">{error}</p>}
          {!loading && !error && rows.length === 0 && (
            <p className="text-slate-400 text-sm">No detail rows.</p>
          )}
          {!loading && !error && rows.length > 0 && (
            <DetailTable rows={rows} metric={metric} showSession={!sessionId} />
          )}
        </div>

        <div className="p-3 border-t border-slate-700 text-right text-xs text-slate-400">
          {rows.length > 0 && `${rows.length} ${rows.length === 1 ? 'row' : 'rows'}`}
        </div>
      </div>
    </div>
  );
}

function DetailTable({
  rows, metric, showSession,
}: { rows: DetailRow[]; metric: MetricCode; showSession: boolean }) {
  // WER metric has a different shape (per-segment stats, no diff)
  if (metric === 'wer') {
    return (
      <table className="min-w-full text-sm">
        <thead className="bg-slate-900 sticky top-0">
          <tr>
            {showSession && <Th>Session</Th>}
            {showSession && <Th>Name</Th>}
            <Th>Segment</Th>
            <Th>Errors</Th>
            <Th>Subs</Th>
            <Th>Dels</Th>
            <Th>Ins</Th>
            <Th>AI words</Th>
            <Th>Seg WER</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-slate-700/60 hover:bg-slate-700/40">
              {showSession && <Td mono>{r.session_id.slice(0, 8)}</Td>}
              {showSession && <Td>{r.name}</Td>}
              <Td>{r.segment}</Td>
              <Td>{r.errors}</Td>
              <Td>{r.subs_ai_error}</Td>
              <Td>{r.dels_ai_error}</Td>
              <Td>{r.ins_ai_error}</Td>
              <Td>{r.ai_word_count}</Td>
              <Td>{r.wer !== undefined ? (r.wer * 100).toFixed(1) + '%' : ''}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <table className="min-w-full text-sm">
      <thead className="bg-slate-900 sticky top-0">
        <tr>
          {showSession && <Th>Session</Th>}
          {showSession && <Th>Name</Th>}
          <Th>Segment</Th>
          {metric.includes('_error') && metric !== 'dates_error' && <Th>Kind</Th>}
          {metric.includes('_error') && metric !== 'dates_error' && <Th>Item</Th>}
          {(metric === 'major_edits' || metric === 'minor_edits' || metric === 'additive_edits') && (
            <Th>Magnitude</Th>
          )}
          <Th>Diff (original → edited)</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-slate-700/60 hover:bg-slate-700/40 align-top">
            {showSession && <Td mono>{r.session_id.slice(0, 8)}</Td>}
            {showSession && <Td>{r.name}</Td>}
            <Td>{r.segment}</Td>
            {metric.includes('_error') && metric !== 'dates_error' && <Td>{r.kind || ''}</Td>}
            {metric.includes('_error') && metric !== 'dates_error' && <Td>{r.item || ''}</Td>}
            {(metric === 'major_edits' || metric === 'minor_edits' || metric === 'additive_edits') && (
              <Td>
                <span className={r.magnitude === 'major' ? 'text-orange-400' : 'text-slate-300'}>
                  {r.magnitude || ''}
                </span>
                {r.additive ? <span className="ml-2 text-blue-400">+additive</span> : null}
              </Td>
            )}
            <Td>
              <div className="space-y-0.5">
                {(r.diff || []).map((line, idx) => (
                  <div key={idx} className="text-xs text-slate-200 font-mono whitespace-pre-wrap">
                    {line}
                  </div>
                ))}
              </div>
            </Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2 text-left font-medium text-slate-300 border-b border-slate-700 whitespace-nowrap">
      {children}
    </th>
  );
}

function Td({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <td className={`px-3 py-2 text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}>
      {children}
    </td>
  );
}

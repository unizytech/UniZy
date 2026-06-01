'use client';

/**
 * Compare tab — repurposed for EHR-payload comparison.
 *
 * Given an extraction ID, fetches:
 *   - The original AI extraction
 *   - The latest edited extraction
 *   - The formatted EHR payload that was sent to the school EHR API
 *
 * and renders them side-by-side so admins can verify the formatter
 * produced the correct wire shape from the counsellor's edits.
 *
 * Backend: GET /api/v1/extractions/{extraction_id}/ehr-payload
 */

import React, { useMemo, useState } from 'react';
import { useAuth } from '@lib/auth';
import { authGet } from '@lib/apiClient';

interface EhrPayloadResponse {
  extraction_id: string;
  ehr_payload: Record<string, unknown> | null;
  edited_extraction: Record<string, unknown> | null;
  original_extraction: Record<string, unknown> | null;
  edit_count: number;
  last_edited_at: string | null;
  last_edited_by: string | null;
  edited_by_type: string | null;
  form_type: string | null;
}

const ErrorBanner = ({ error }: { error: string | null }) => {
  if (!error) return null;
  return (
    <div className="w-full bg-red-900/50 text-red-300 border border-red-700 rounded-lg p-3 mt-4">
      <p>{error}</p>
    </div>
  );
};

const JsonPanel = ({
  title,
  subtitle,
  data,
  emptyHint,
  highlight,
}: {
  title: string;
  subtitle?: string;
  data: unknown;
  emptyHint?: string;
  highlight?: 'blue' | 'green' | 'orange';
}) => {
  const headerColor =
    highlight === 'green'
      ? 'border-green-700 bg-green-900/30'
      : highlight === 'orange'
      ? 'border-orange-700 bg-orange-900/30'
      : 'border-blue-700 bg-blue-900/30';

  const isEmpty =
    data === null ||
    data === undefined ||
    (typeof data === 'object' && Object.keys(data as object).length === 0);

  return (
    <div className={`rounded-lg border ${headerColor} flex flex-col min-h-0`}>
      <div className="px-4 py-2 border-b border-gray-700">
        <div className="text-sm font-semibold text-white">{title}</div>
        {subtitle && (
          <div className="text-xs text-gray-400 mt-0.5">{subtitle}</div>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto bg-gray-950 rounded-b-lg">
        {isEmpty ? (
          <div className="p-4 text-sm text-gray-500 italic">
            {emptyHint || 'No data'}
          </div>
        ) : (
          <pre className="p-3 text-xs text-gray-200 font-mono whitespace-pre-wrap break-words">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
};

export default function CompareTranscriptTab() {
  const { getAccessToken } = useAuth();
  const [extractionId, setExtractionId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<EhrPayloadResponse | null>(null);

  const handleFetch = async () => {
    const id = extractionId.trim();
    if (!id) {
      setError('Enter an extraction ID first.');
      return;
    }
    setError(null);
    setLoading(true);
    setData(null);
    try {
      const token = await getAccessToken();
      const resp = await authGet(
        `/api/v1/extractions/${encodeURIComponent(id)}/ehr-payload`,
        token,
      );
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        throw new Error(
          detail?.detail ||
            `Request failed: ${resp.status} ${resp.statusText}`,
        );
      }
      const json: EhrPayloadResponse = await resp.json();
      setData(json);
    } catch (e) {
      setError((e as Error).message || 'Failed to fetch EHR payload.');
    } finally {
      setLoading(false);
    }
  };

  const meta = useMemo(() => {
    if (!data) return null;
    return [
      { label: 'Edit count', value: String(data.edit_count) },
      { label: 'Form type', value: data.form_type || '—' },
      {
        label: 'Last edited at',
        value: data.last_edited_at
          ? new Date(data.last_edited_at).toLocaleString()
          : '—',
      },
      { label: 'Edited by type', value: data.edited_by_type || '—' },
      { label: 'Last edited by', value: data.last_edited_by || '—' },
    ];
  }, [data]);

  return (
    <div className="w-full h-full flex flex-col p-4 gap-4 min-h-0">
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-bold text-white">
          Compare — extraction vs. EHR payload
        </h2>
        <p className="text-sm text-gray-400">
          Enter an extraction UUID to view the original AI extraction, the
          counsellor&apos;s latest edits, and the formatted payload that was sent to
          the school EHR API. Useful for verifying that the formatter
          projected counsellor edits into the correct EHR wire shape.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center">
        <input
          type="text"
          value={extractionId}
          onChange={(e) => setExtractionId(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleFetch();
          }}
          placeholder="extraction id (UUID)"
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-600"
        />
        <button
          onClick={handleFetch}
          disabled={loading || !extractionId.trim()}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
        >
          {loading ? 'Loading…' : 'Fetch'}
        </button>
      </div>

      <ErrorBanner error={error} />

      {meta && (
        <div className="flex flex-wrap gap-4 text-xs bg-gray-900 border border-gray-800 rounded-lg p-3">
          {meta.map((m) => (
            <div key={m.label}>
              <span className="text-gray-500">{m.label}: </span>
              <span className="text-gray-200 font-mono">{m.value}</span>
            </div>
          ))}
        </div>
      )}

      {data && (
        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-3 gap-3">
          <JsonPanel
            title="Original AI extraction"
            subtitle="original_extraction_json"
            data={data.original_extraction}
            highlight="blue"
            emptyHint="No original extraction stored."
          />
          <JsonPanel
            title="Edited extraction"
            subtitle={`edited_extraction_json · ${data.edit_count} edit(s)`}
            data={data.edited_extraction}
            highlight="orange"
            emptyHint="Never edited — frontend would have used original."
          />
          <JsonPanel
            title="EHR payload (sent to school)"
            subtitle={`ehr_payload_json${
              data.form_type ? ` · ${data.form_type}` : ''
            }`}
            data={data.ehr_payload}
            highlight="green"
            emptyHint="No EHR payload was generated for this extraction (template may not have a formatter)."
          />
        </div>
      )}

      {!data && !loading && !error && (
        <div className="flex-1 min-h-0 flex items-center justify-center text-gray-500 text-sm">
          Enter an extraction UUID above and press Fetch.
        </div>
      )}
    </div>
  );
}

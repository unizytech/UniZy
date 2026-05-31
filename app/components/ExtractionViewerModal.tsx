'use client';

import React, { useEffect, useState } from 'react';
import { getExtractionViewerData, ExtractionViewerData } from '../../lib/recordingsApi';

export type ExtractionViewerMode = 'transcript' | 'extraction';

interface ExtractionViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
  extractionId: string | null;
  mode: ExtractionViewerMode;
  accessToken: string | null;
  patientName?: string | null;
  consultationDatetime?: string | null;
}

function JsonBlock({ data }: { data: unknown }) {
  let pretty: string;
  try {
    pretty = JSON.stringify(data, null, 2);
  } catch {
    pretty = String(data);
  }
  return (
    <pre className="text-xs text-gray-800 bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-auto max-h-[60vh] whitespace-pre-wrap font-mono">
      {pretty}
    </pre>
  );
}

export function ExtractionViewerModal({
  isOpen,
  onClose,
  extractionId,
  mode,
  accessToken,
  patientName,
  consultationDatetime,
}: ExtractionViewerModalProps) {
  const [data, setData] = useState<ExtractionViewerData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !extractionId) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getExtractionViewerData(extractionId, accessToken)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e?.message || 'Failed to load'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [isOpen, extractionId, accessToken]);

  if (!isOpen) return null;

  const title = mode === 'transcript' ? 'Transcript' : 'Extraction';
  const extraction = data?.edited_extraction || data?.original_extraction || null;
  const showEhrBox = mode === 'extraction' && data?.ehr_payload && Object.keys(data.ehr_payload).length > 0;

  return (
    <div className="fixed inset-0 z-[60] overflow-y-auto">
      <div className="min-h-screen px-4 flex items-center justify-center">
        <div className="fixed inset-0 bg-gray-500 bg-opacity-75" onClick={onClose} />

        <div className="relative inline-block w-full max-w-4xl my-8 text-left align-middle bg-white rounded-2xl shadow-xl">
          {/* Header */}
          <div className="bg-gradient-to-r from-slate-700 to-slate-800 px-6 py-4 rounded-t-2xl flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-white">{title}</h2>
              <p className="text-slate-200 text-sm">
                {patientName || 'Unknown student'}
                {consultationDatetime ? ` · ${new Date(consultationDatetime).toLocaleString()}` : ''}
                {data?.is_merged ? ' · Merged' : ''}
                {mode === 'extraction' && data?.edit_count ? ` · Edited ${data.edit_count}x` : ''}
              </p>
            </div>
            <button onClick={onClose} className="text-white/80 hover:text-white">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Body */}
          <div className="p-6 max-h-[75vh] overflow-y-auto">
            {loading && (
              <div className="flex justify-center items-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-600"></div>
              </div>
            )}

            {error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {error}
              </div>
            )}

            {!loading && !error && data && mode === 'transcript' && (
              data.transcript_text ? (
                <pre className="text-sm text-gray-800 bg-gray-50 border border-gray-200 rounded-lg p-4 whitespace-pre-wrap leading-relaxed">
                  {data.transcript_text}
                </pre>
              ) : (
                <div className="text-center py-12 text-gray-500 text-sm">
                  No transcript available for this recording.
                </div>
              )
            )}

            {!loading && !error && data && mode === 'extraction' && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    Extraction JSON
                    {data.edited_extraction ? ' (edited)' : ' (original)'}
                  </h3>
                  {extraction ? (
                    <JsonBlock data={extraction} />
                  ) : (
                    <div className="text-sm text-gray-500">No extraction data.</div>
                  )}
                </div>

                {showEhrBox && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">
                      EHR Payload
                      {data.form_type ? ` · ${data.form_type}` : ''}
                    </h3>
                    <p className="text-xs text-gray-500 mb-2">
                      Formatted payload sent (or to be sent) to the school EHR API.
                    </p>
                    <JsonBlock data={data.ehr_payload} />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

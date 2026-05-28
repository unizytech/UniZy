'use client';

/**
 * Examination Fields Modal — read-only viewer for the per-template
 * EXAMINATION_<SITE> segment (prompt + JSON schema).
 */

import React, { useEffect, useState } from 'react';
import { useAuth } from '@lib/auth';
import type { Template } from '@lib/types';
import {
  ExaminationSegment,
  getExaminationSegment,
} from '@/services/radiologyConfigApi';

interface Props {
  template: Template;
  onClose: () => void;
}

export function ExaminationFieldsModal({ template, onClose }: Props) {
  const { getAccessToken } = useAuth();
  const [segment, setSegment] = useState<ExaminationSegment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const seg = await getExaminationSegment(template.id, getAccessToken());
        if (!cancelled) setSegment(seg);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [template.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] overflow-y-auto">
        <div className="bg-slate-700 text-white p-6 rounded-t-lg sticky top-0 z-10">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">Examination Fields</h2>
              <p className="text-slate-200 text-sm mt-1">
                {template.template_name} ({template.template_code})
              </p>
            </div>
            <button onClick={onClose} className="text-white hover:bg-slate-800 rounded-lg p-2 transition-colors" title="Close">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-500" />
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">{error}</div>
          ) : !segment ? (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-yellow-900">
              No EXAMINATION_* segment is attached to this template.
            </div>
          ) : (
            <div className="space-y-6">
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide">Segment code</div>
                <div className="font-mono text-sm text-gray-900">{segment.segment_code}</div>
                {segment.segment_name && (
                  <div className="text-sm text-gray-700 mt-1">{segment.segment_name}</div>
                )}
              </div>

              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Extraction prompt</div>
                <pre className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-xs text-gray-800 whitespace-pre-wrap font-mono overflow-x-auto">
                  {segment.prompt_section_text || '(empty)'}
                </pre>
              </div>

              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">JSON schema</div>
                <SchemaTable schema={segment.schema_definition_json} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SchemaTable({ schema }: { schema: Record<string, unknown> | null }) {
  if (!schema) return <div className="text-sm text-gray-500">(no schema)</div>;

  const properties = (schema as { properties?: Record<string, { type?: string; description?: string; enum?: unknown[] }> }).properties;
  if (!properties || typeof properties !== 'object') {
    return (
      <pre className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-xs text-gray-800 whitespace-pre-wrap font-mono overflow-x-auto">
        {JSON.stringify(schema, null, 2)}
      </pre>
    );
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-xs text-gray-600 uppercase tracking-wide">
          <tr>
            <th className="text-left px-4 py-2">Field</th>
            <th className="text-left px-4 py-2">Type</th>
            <th className="text-left px-4 py-2">Description</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {Object.entries(properties).map(([key, def]) => (
            <tr key={key}>
              <td className="px-4 py-2 font-mono text-xs text-gray-900">{key}</td>
              <td className="px-4 py-2 text-xs text-gray-700">
                {def.type || ''}
                {def.enum && def.enum.length > 0 && (
                  <span className="ml-1 text-gray-500">({def.enum.join('|')})</span>
                )}
              </td>
              <td className="px-4 py-2 text-xs text-gray-700">{def.description || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

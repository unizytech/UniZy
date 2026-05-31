'use client';

/**
 * QA Results Table Component
 *
 * Displays search results in a tabular format with pagination.
 */

import React, { useState } from 'react';
import type { QASearchResult } from '@lib/types';

// ============================================================================
// Types
// ============================================================================

interface QAResultsTableProps {
  results: QASearchResult[];
  totalCount: number;
  pageSize?: number;
  referencedIds?: string[];  // Extraction IDs that were referenced in narrative
}

// ============================================================================
// Component
// ============================================================================

export default function QAResultsTable({
  results,
  totalCount,
  pageSize = 10,
  referencedIds = [],
}: QAResultsTableProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  // Check if a result is referenced in the narrative
  const isReferenced = (extractionId: string) => (referencedIds ?? []).includes(extractionId);

  // Pagination
  const totalPages = Math.ceil(results.length / pageSize);
  const startIdx = (currentPage - 1) * pageSize;
  const endIdx = startIdx + pageSize;
  const displayResults = results.slice(startIdx, endIdx);

  return (
    <div className="space-y-4">
      {/* Results Count */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          Showing {startIdx + 1}-{Math.min(endIdx, results.length)} of {totalCount} results
        </p>
      </div>

      {/* Table */}
      <div className="border border-gray-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Student
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Counsellor
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Date
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Match
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-12">

                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {displayResults.map((result) => {
                const referenced = isReferenced(result.extraction_id);
                return (
                <React.Fragment key={result.extraction_id}>
                  <tr
                    className={`hover:bg-gray-50 cursor-pointer ${
                      expandedRow === result.extraction_id ? 'bg-gray-50' : ''
                    } ${referenced ? 'bg-green-50 border-l-4 border-l-green-500' : ''}`}
                    onClick={() =>
                      setExpandedRow(
                        expandedRow === result.extraction_id
                          ? null
                          : result.extraction_id
                      )
                    }
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {referenced && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700" title="Referenced in answer">
                            ✓
                          </span>
                        )}
                        <div>
                          <p className="text-sm font-medium text-gray-900">
                            {result.patient_name || 'Unknown Student'}
                          </p>
                          {result.patient_external_id && (
                            <p className="text-xs text-gray-500">
                              ID: {result.patient_external_id}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-sm text-gray-700">
                        {result.doctor_name || 'N/A'}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {result.consultation_type_name || 'Session'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-sm text-gray-600">
                        {formatDate(result.created_at)}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <SimilarityBadge score={result.similarity_score} />
                    </td>
                    <td className="px-4 py-3">
                      <svg
                        className={`w-5 h-5 text-gray-400 transition-transform ${
                          expandedRow === result.extraction_id
                            ? 'rotate-180'
                            : ''
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 9l-7 7-7-7"
                        />
                      </svg>
                    </td>
                  </tr>

                  {/* Expanded Content */}
                  {expandedRow === result.extraction_id && (
                    <tr>
                      <td colSpan={6} className="px-4 py-4 bg-gray-50">
                        <div className="space-y-3">
                          {/* Matched Segment */}
                          {result.matched_segment_code && (
                            <div>
                              <span className="text-xs font-medium text-gray-500 uppercase">
                                Matched Segment:
                              </span>
                              <span className="ml-2 text-sm text-gray-700">
                                {result.matched_segment_code}
                              </span>
                            </div>
                          )}

                          {/* Content Preview */}
                          {result.matched_content_preview && (
                            <div>
                              <span className="text-xs font-medium text-gray-500 uppercase block mb-1">
                                Matched Content:
                              </span>
                              <p className="text-sm text-gray-700 bg-white p-3 rounded border border-gray-200">
                                {result.matched_content_preview}
                              </p>
                            </div>
                          )}

                          {/* Extraction Data Preview */}
                          {result.extraction_data && (
                            <div>
                              <span className="text-xs font-medium text-gray-500 uppercase block mb-1">
                                Key Insights:
                              </span>
                              <div className="bg-white p-3 rounded border border-gray-200">
                                <ExtractionDataPreview data={result.extraction_data} />
                              </div>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
              })}

              {displayResults.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-gray-500"
                  >
                    No results found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <div className="flex items-center gap-1">
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
              <button
                key={page}
                onClick={() => setCurrentPage(page)}
                className={`w-8 h-8 text-sm font-medium rounded-lg ${
                  currentPage === page
                    ? 'bg-rose-600 text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                {page}
              </button>
            ))}
          </div>
          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Sub-Components
// ============================================================================

function SimilarityBadge({ score }: { score: number }) {
  const percentage = Math.round(score * 100);
  const color =
    percentage >= 80
      ? 'bg-green-100 text-green-700'
      : percentage >= 60
      ? 'bg-yellow-100 text-yellow-700'
      : 'bg-gray-100 text-gray-600';

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${color}`}
    >
      {percentage}%
    </span>
  );
}

function ExtractionDataPreview({ data }: { data: Record<string, any> }) {
  // Show key medical fields
  const keyFields = [
    { key: 'chief_complaint', label: 'Chief Complaint' },
    { key: 'diagnosis', label: 'Diagnosis' },
    { key: 'primary_diagnosis', label: 'Primary Diagnosis' },
    { key: 'medications', label: 'Medications' },
    { key: 'prescriptions', label: 'Prescriptions' },
    { key: 'investigations', label: 'Investigations' },
  ];

  const displayItems = keyFields
    .filter((field) => data[field.key])
    .slice(0, 3);

  if (displayItems.length === 0) {
    return <p className="text-sm text-gray-500 italic">No preview available</p>;
  }

  return (
    <dl className="grid grid-cols-1 gap-2">
      {displayItems.map((field) => (
        <div key={field.key}>
          <dt className="text-xs font-medium text-gray-500">{field.label}</dt>
          <dd className="text-sm text-gray-700 mt-0.5">
            {formatFieldValue(data[field.key])}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(date);
  } catch {
    return dateStr;
  }
}

function formatFieldValue(value: any): string {
  if (Array.isArray(value)) {
    if (value.length === 0) return '-';
    if (typeof value[0] === 'object') {
      return value.map((v) => v.name || v.medication || JSON.stringify(v)).join(', ');
    }
    return value.join(', ');
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value);
  }
  return String(value || '-');
}

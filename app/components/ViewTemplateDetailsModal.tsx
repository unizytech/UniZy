'use client';

/**
 * View Template Details Modal (Read-Only)
 *
 * Shows segment configurations for common templates without allowing edits.
 * Doctors can view the configuration but must clone to make changes.
 */

import { useState, useEffect } from 'react';
import { getTemplateSegments, handleApiError } from '@lib/summaryApi';
import type { Template } from '@lib/types';

interface ViewTemplateDetailsModalProps {
  template: Template;
  onClose: () => void;
  onClone?: () => void;
}

interface SegmentConfig {
  segment_id: string;
  segment_code: string;
  segment_name?: string;
  category: 'core' | 'additional' | 'excluded';
  display_order: number;
  brevity_level: string;
  terminology_style: string;
  segment_definitions?: {
    segment_name: string;
    description?: string;
    prompt_section_text?: string;
  };
}

export function ViewTemplateDetailsModal({
  template,
  onClose,
  onClone,
}: ViewTemplateDetailsModalProps) {
  const [segments, setSegments] = useState<SegmentConfig[]>([]);
  const [selectedSegment, setSelectedSegment] = useState<SegmentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'core' | 'additional' | 'excluded'>('core');

  useEffect(() => {
    loadSegments();
  }, [template.template_code]);

  const loadSegments = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await getTemplateSegments(template.template_code);
      setSegments(response.segments || []);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const coreSegments = segments.filter(s => s.category === 'core').sort((a, b) => a.display_order - b.display_order);
  const additionalSegments = segments.filter(s => s.category === 'additional').sort((a, b) => a.display_order - b.display_order);
  const excludedSegments = segments.filter(s => s.category === 'excluded').sort((a, b) => a.display_order - b.display_order);

  const currentSegments = activeTab === 'core' ? coreSegments : activeTab === 'additional' ? additionalSegments : excludedSegments;

  const formatBrevityLevel = (level: string) => {
    return level.charAt(0).toUpperCase() + level.slice(1);
  };

  const formatTerminologyStyle = (style: string) => {
    return style.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="bg-gray-600 text-white p-6 rounded-t-lg sticky top-0 z-10">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-2xl font-bold">View Template Details (Read-Only)</h2>
              <p className="text-gray-100 text-sm mt-1">
                {template.template_name} ({template.template_code})
              </p>
            </div>
            <div className="flex items-center gap-2">
              {onClone && (
                <button
                  onClick={onClone}
                  className="bg-blue-500 text-white px-4 py-2 rounded-lg font-medium hover:bg-blue-600 transition-colors"
                >
                  Clone to Customize
                </button>
              )}
              <button
                onClick={onClose}
                className="bg-white text-gray-600 px-4 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
              >
                Close
              </button>
            </div>
          </div>

          <div className="bg-yellow-100 border border-yellow-300 rounded-lg p-3 text-yellow-900">
            <div className="flex items-start">
              <svg className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
              <div>
                <p className="text-sm font-semibold">Read-Only Template</p>
                <p className="text-xs mt-1">
                  This template is read-only (either a common template or shared with view-only access).
                  You can view the configuration but cannot edit it. Click "Clone to Customize" to create your own editable copy.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6">
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-600 mx-auto mb-4"></div>
                <p className="text-gray-600">Loading template configuration...</p>
              </div>
            </div>
          ) : (
            <>
              {/* Category Tabs */}
              <div className="flex gap-2 mb-6 border-b border-gray-200">
                <button
                  onClick={() => setActiveTab('core')}
                  className={`px-4 py-2 font-medium transition-colors ${
                    activeTab === 'core'
                      ? 'text-blue-600 border-b-2 border-blue-600'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  CORE ({coreSegments.length})
                </button>
                <button
                  onClick={() => setActiveTab('additional')}
                  className={`px-4 py-2 font-medium transition-colors ${
                    activeTab === 'additional'
                      ? 'text-gray-600 border-b-2 border-gray-600'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  ADDITIONAL ({additionalSegments.length})
                </button>
                <button
                  onClick={() => setActiveTab('excluded')}
                  className={`px-4 py-2 font-medium transition-colors ${
                    activeTab === 'excluded'
                      ? 'text-red-600 border-b-2 border-red-600'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  EXCLUDED ({excludedSegments.length})
                </button>
              </div>

              {/* Segments Table */}
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 border border-gray-200 rounded-lg">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Order
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Segment Name
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Code
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Category
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Brevity Level
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Terminology Style
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {currentSegments.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                          No segments in this category
                        </td>
                      </tr>
                    ) : (
                      currentSegments.map((segment) => (
                        <tr key={segment.segment_id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {segment.display_order}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-900">
                            {segment.segment_definitions?.segment_name || segment.segment_code}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm font-mono text-gray-600">
                            {segment.segment_code}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                              segment.category === 'core'
                                ? 'bg-blue-100 text-blue-800'
                                : segment.category === 'additional'
                                ? 'bg-gray-100 text-gray-800'
                                : 'bg-red-100 text-red-800'
                            }`}>
                              {segment.category.toUpperCase()}
                            </span>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                            {formatBrevityLevel(segment.brevity_level)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                            {formatTerminologyStyle(segment.terminology_style)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm">
                            <button
                              onClick={() => setSelectedSegment(segment)}
                              className="text-blue-600 hover:text-blue-800 font-medium"
                            >
                              View Details
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        {/* Segment Detail Modal */}
        {selectedSegment && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto">
              <div className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold text-gray-900">
                    {selectedSegment.segment_definitions?.segment_name || selectedSegment.segment_code}
                  </h3>
                  <button
                    onClick={() => setSelectedSegment(null)}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Segment Code</label>
                    <p className="text-sm text-gray-900 font-mono bg-gray-50 px-3 py-2 rounded border border-gray-200">
                      {selectedSegment.segment_code}
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                    <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border border-gray-200">
                      {selectedSegment.category.toUpperCase()}
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Display Order</label>
                    <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border border-gray-200">
                      {selectedSegment.display_order}
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Brevity Level</label>
                    <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border border-gray-200">
                      {formatBrevityLevel(selectedSegment.brevity_level)}
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Terminology Style</label>
                    <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border border-gray-200">
                      {formatTerminologyStyle(selectedSegment.terminology_style)}
                    </p>
                  </div>

                  {selectedSegment.segment_definitions?.description && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                      <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border border-gray-200">
                        {selectedSegment.segment_definitions.description}
                      </p>
                    </div>
                  )}

                  {selectedSegment.segment_definitions?.prompt_section_text && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Prompt Section</label>
                      <pre className="text-xs text-gray-900 bg-gray-50 px-3 py-2 rounded border border-gray-200 whitespace-pre-wrap overflow-x-auto">
                        {selectedSegment.segment_definitions.prompt_section_text}
                      </pre>
                    </div>
                  )}
                </div>

                <div className="mt-6 flex justify-end">
                  <button
                    onClick={() => setSelectedSegment(null)}
                    className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

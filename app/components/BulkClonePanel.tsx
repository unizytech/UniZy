'use client';

import React, { useState, useEffect } from 'react';
import type { ConsultationTypeCode } from '@lib/types';
import { handleApiError } from '@lib/summaryApi';
import { useAuth } from '@lib/auth';
import { authGet, authPost, API_BASE_URL } from '@lib/apiClient';

interface BulkClonePanelProps {
  consultationTypes: Array<{
    type_code: string;
    type_name: string;
    id: string;
  }>;
  userId?: string;
  onComplete?: () => void;
}

interface SegmentOption {
  segment_code: string;
  segment_name: string;
  default_category: string;
  is_required: boolean;
  is_active?: boolean;
  consultation_type_code?: string;
}

interface CloneResult {
  success: Array<{
    original_segment_code: string;
    new_segment_code: string;
    segment_name: string;
    segment_id: string;
  }>;
  failed: Array<{
    segment_code: string;
    error: string;
  }>;
  summary: {
    total_requested: number;
    successful: number;
    failed: number;
    source_consultation_type: string;
    target_consultation_type: string;
  };
  message: string;
}

export function BulkClonePanel({ consultationTypes, userId, onComplete }: BulkClonePanelProps) {
  const { getAccessToken } = useAuth();
  const [sourceType, setSourceType] = useState<string>('');
  const [targetType, setTargetType] = useState<string>('');
  const [availableSegments, setAvailableSegments] = useState<SegmentOption[]>([]);
  const [selectedSegments, setSelectedSegments] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [loadingSegments, setLoadingSegments] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CloneResult | null>(null);

  // Load segments when source type changes
  useEffect(() => {
    if (sourceType) {
      loadSourceSegments();
    } else {
      setAvailableSegments([]);
      setSelectedSegments(new Set());
    }
  }, [sourceType]);

  const loadSourceSegments = async () => {
    setLoadingSegments(true);
    setError(null);
    try {
      const response = await authGet(
        `/api/v1/summary/admin/segments?consultation_type_code=${sourceType}&include_common=true`,
        getAccessToken()
      );

      if (!response.ok) {
        throw new Error('Failed to load segments');
      }

      const data = await response.json();
      setAvailableSegments(data.segments || []);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoadingSegments(false);
    }
  };

  const toggleSegment = (segmentCode: string) => {
    setSelectedSegments(prev => {
      const newSet = new Set(prev);
      if (newSet.has(segmentCode)) {
        newSet.delete(segmentCode);
      } else {
        newSet.add(segmentCode);
      }
      return newSet;
    });
  };

  const selectAll = () => {
    setSelectedSegments(new Set(availableSegments.map(s => s.segment_code)));
  };

  const deselectAll = () => {
    setSelectedSegments(new Set());
  };

  const handleBulkClone = async () => {
    if (!sourceType || !targetType || selectedSegments.size === 0) {
      setError('Please select source type, target type, and at least one segment');
      return;
    }

    if (sourceType === targetType) {
      setError('Source and target consultation types must be different');
      return;
    }

    if (!userId) {
      setError('User ID is required for bulk clone operation');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await authPost(
        `/api/v1/summary/admin/consultation-types/${targetType}/segments/clone-bulk?admin_id=${userId}`,
        getAccessToken(),
        {
          source_consultation_type_code: sourceType,
          segment_codes: Array.from(selectedSegments),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to bulk clone segments');
      }

      const data = await response.json();
      setResult(data);

      // Clear selections after successful clone
      setSelectedSegments(new Set());

      if (onComplete) {
        onComplete();
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const groupedSegments = availableSegments.reduce((acc, segment) => {
    const category = segment.default_category || 'uncategorized';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(segment);
    return acc;
  }, {} as Record<string, SegmentOption[]>);

  return (
    <div className="space-y-6">
      <div className="bg-blue-50 border-l-4 border-blue-500 p-4 rounded">
        <div className="flex">
          <div className="flex-1">
            <h3 className="text-sm font-medium text-blue-900">Bulk Clone Segments</h3>
            <p className="mt-1 text-sm text-blue-700">
              Quickly add segments from an existing consultation type to a new one. Select source, target, and segments to clone.
            </p>
          </div>
        </div>
      </div>

      {/* Source and Target Selection */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">1. Select Consultation Types</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Source Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Source Consultation Type
            </label>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Select source...</option>
              {[...consultationTypes].sort((a, b) => (a.type_name || '').localeCompare(b.type_name || '')).map((ct) => (
                <option key={ct.type_code} value={ct.type_code}>
                  {ct.type_name} ({ct.type_code})
                </option>
              ))}
            </select>
          </div>

          {/* Target Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Target Consultation Type
            </label>
            <select
              value={targetType}
              onChange={(e) => setTargetType(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Select target...</option>
              {[...consultationTypes]
                .sort((a, b) => (a.type_name || '').localeCompare(b.type_name || ''))
                .filter((ct) => ct.type_code !== sourceType)
                .map((ct) => (
                  <option key={ct.type_code} value={ct.type_code}>
                    {ct.type_name} ({ct.type_code})
                  </option>
                ))}
            </select>
          </div>
        </div>
      </div>

      {/* Segment Selection */}
      {sourceType && (
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="p-6 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">
                2. Select Segments to Clone ({selectedSegments.size}/{availableSegments.length})
              </h3>
              <div className="flex gap-2">
                <button
                  onClick={selectAll}
                  className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  Select All
                </button>
                <span className="text-gray-300">|</span>
                <button
                  onClick={deselectAll}
                  className="text-sm text-gray-600 hover:text-gray-700 font-medium"
                >
                  Deselect All
                </button>
              </div>
            </div>
          </div>

          {loadingSegments ? (
            <div className="p-8 text-center text-gray-500">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-2"></div>
              <p>Loading segments...</p>
            </div>
          ) : availableSegments.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              No segments available for this consultation type
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {Object.entries(groupedSegments).map(([category, segments]) => (
                <div key={category} className="p-4">
                  <h4 className="text-sm font-semibold text-gray-700 uppercase mb-3">
                    {category} ({segments.length})
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {segments.map((segment) => (
                      <label
                        key={segment.segment_code}
                        className={`flex items-start p-3 rounded-lg border-2 cursor-pointer transition-all ${
                          selectedSegments.has(segment.segment_code)
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200 hover:border-gray-300 bg-white'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedSegments.has(segment.segment_code)}
                          onChange={() => toggleSegment(segment.segment_code)}
                          className="mt-1 h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                        />
                        <div className="ml-3 flex-1">
                          <div className="font-medium text-gray-900 text-sm">
                            {segment.segment_name}
                          </div>
                          <div className="flex items-center gap-1 mt-1">
                            <span className="text-xs text-gray-500 font-mono">
                              {segment.segment_code}
                            </span>
                            {segment.is_required && (
                              <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
                                Req
                              </span>
                            )}
                            {segment.is_active === false && (
                              <span className="text-xs bg-gray-200 text-gray-700 px-1.5 py-0.5 rounded border border-gray-400">
                                INACTIVE
                              </span>
                            )}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Clone Button */}
      {sourceType && targetType && selectedSegments.size > 0 && (
        <div className="flex justify-end">
          <button
            onClick={handleBulkClone}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-6 py-3 rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Cloning...
              </>
            ) : (
              <>
                🚀 Clone {selectedSegments.size} Segment{selectedSegments.size !== 1 ? 's' : ''}
              </>
            )}
          </button>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded">
          <div className="flex">
            <div className="flex-1">
              <h3 className="text-sm font-medium text-red-900">Error</h3>
              <p className="mt-1 text-sm text-red-700">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Result Display */}
      {result && (
        <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">Clone Results</h3>
            <div className={`px-3 py-1 rounded-full text-sm font-medium ${
              result.summary.failed === 0
                ? 'bg-green-100 text-green-800'
                : 'bg-yellow-100 text-yellow-800'
            }`}>
              {result.summary.successful} / {result.summary.total_requested} successful
            </div>
          </div>

          <p className="text-sm text-gray-600">{result.message}</p>

          {/* Success List */}
          {result.success.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-green-800">✓ Successfully Cloned</h4>
              <div className="space-y-1">
                {result.success.map((item) => (
                  <div key={item.segment_id} className="text-sm text-gray-700 bg-green-50 p-2 rounded">
                    {item.segment_name} ({item.original_segment_code} → {item.new_segment_code})
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Failed List */}
          {result.failed.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-red-800">✗ Failed</h4>
              <div className="space-y-1">
                {result.failed.map((item, idx) => (
                  <div key={idx} className="text-sm text-gray-700 bg-red-50 p-2 rounded">
                    {item.segment_code}: {item.error}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

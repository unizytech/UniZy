'use client';

import React, { useState, useEffect } from 'react';
import {
  getAvailableSegmentsForTemplate,
  addSegmentsFromType,
  type AvailableSegment
} from '@lib/summaryApi';
import { useAuth } from '@lib/auth';

interface AddSegmentsModalProps {
  templateCode: string;
  isOpen: boolean;
  onClose: () => void;
  onSegmentsAdded: () => void;
}

export function AddSegmentsModal({
  templateCode,
  isOpen,
  onClose,
  onSegmentsAdded,
}: AddSegmentsModalProps) {
  const { getAccessToken } = useAuth();
  const [availableSegments, setAvailableSegments] = useState<AvailableSegment[]>([]);
  const [selectedSegments, setSelectedSegments] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [consultationTypeCode, setConsultationTypeCode] = useState<string>('');

  useEffect(() => {
    if (isOpen && templateCode) {
      loadAvailableSegments();
    }
  }, [isOpen, templateCode]);

  const loadAvailableSegments = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAvailableSegmentsForTemplate(templateCode, getAccessToken());
      setAvailableSegments(data.available_segments);
      setConsultationTypeCode(data.consultation_type_code);
      setSelectedSegments(new Set());
    } catch (err: any) {
      setError(err.message || 'Failed to load available segments');
    } finally {
      setLoading(false);
    }
  };

  const toggleSegment = (segmentCode: string) => {
    setSelectedSegments((prev) => {
      const next = new Set(prev);
      if (next.has(segmentCode)) {
        next.delete(segmentCode);
      } else {
        next.add(segmentCode);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelectedSegments(new Set(availableSegments.map((s) => s.segment_code)));
  };

  const deselectAll = () => {
    setSelectedSegments(new Set());
  };

  const handleAdd = async () => {
    if (selectedSegments.size === 0) return;

    setAdding(true);
    setError(null);
    try {
      await addSegmentsFromType(templateCode, {
        segment_codes: Array.from(selectedSegments),
        default_category: 'excluded',
      }, getAccessToken());
      onSegmentsAdded();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to add segments');
    } finally {
      setAdding(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-2xl font-bold text-gray-900">
            Add Segments from Session Type
          </h2>
          <p className="text-sm text-gray-600 mt-2">
            Select segments from <strong>{consultationTypeCode}</strong> to add to this template.
            New segments will be added as &quot;Excluded&quot; and can be moved to Core/Additional using drag-and-drop.
          </p>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-600"></div>
              <span className="ml-3 text-gray-600">Loading available segments...</span>
            </div>
          ) : availableSegments.length === 0 ? (
            <div className="text-center py-8">
              <div className="text-gray-400 text-4xl mb-3">&#10003;</div>
              <p className="text-gray-600 font-medium">All segments already added</p>
              <p className="text-sm text-gray-500 mt-1">
                All segments from the session type are already in this template.
              </p>
            </div>
          ) : (
            <>
              {/* Select All / Deselect All */}
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm text-gray-600">
                  {selectedSegments.size} of {availableSegments.length} selected
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={selectAll}
                    className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                  >
                    Select All
                  </button>
                  <span className="text-gray-300">|</span>
                  <button
                    type="button"
                    onClick={deselectAll}
                    className="text-sm text-gray-600 hover:text-gray-800 font-medium"
                  >
                    Deselect All
                  </button>
                </div>
              </div>

              {/* Segment List */}
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {availableSegments.map((segment) => (
                  <label
                    key={segment.segment_code}
                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedSegments.has(segment.segment_code)
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedSegments.has(segment.segment_code)}
                      onChange={() => toggleSegment(segment.segment_code)}
                      className="mt-1 h-4 w-4 text-blue-600 rounded focus:ring-blue-500"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">{segment.segment_name}</span>
                        <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                          {segment.segment_code}
                        </span>
                      </div>
                      {segment.description && (
                        <p className="text-sm text-gray-500 mt-1 truncate">{segment.description}</p>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                        <span>
                          Category: <strong className="text-gray-700">{segment.default_category}</strong>
                        </span>
                        <span>
                          Brevity: <strong className="text-gray-700">{segment.default_brevity_level}</strong>
                        </span>
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 bg-gray-50 flex justify-between items-center">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleAdd}
            disabled={selectedSegments.size === 0 || adding}
            className="px-4 py-2 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {adding ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white"></div>
                Adding...
              </>
            ) : (
              <>Add {selectedSegments.size} Segment{selectedSegments.size !== 1 ? 's' : ''}</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

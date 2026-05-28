'use client';

import React, { useState, useEffect } from 'react';
import type { BrevityLevel, TerminologyStyle } from '@lib/types';
import { updateTemplateSegment, type TemplateSegmentConfig } from '@lib/summaryApi';
import { useAuth } from '@lib/auth';

interface TemplateSegmentEditModalProps {
  segment: {
    id: string;  // Unique segment ID (UUID)
    segment_code: string;
    segment_name: string;
    category: 'core' | 'additional' | 'excluded';
    display_order: number;
    brevity_level: BrevityLevel;
    terminology_style: TerminologyStyle;
  };
  templateCode: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  onNavigateToSegmentDefinition?: (segmentId: string) => void;
}

export function TemplateSegmentEditModal({
  segment,
  templateCode,
  isOpen,
  onClose,
  onSuccess,
  onNavigateToSegmentDefinition,
}: TemplateSegmentEditModalProps) {
  const { getAccessToken } = useAuth();
  const [formData, setFormData] = useState({
    category: segment.category,
    display_order: segment.display_order,
    brevity_level: segment.brevity_level,
    terminology_style: segment.terminology_style,
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form data when segment changes
  useEffect(() => {
    setFormData({
      category: segment.category,
      display_order: segment.display_order,
      brevity_level: segment.brevity_level,
      terminology_style: segment.terminology_style,
    });
    setError(null);
  }, [segment]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const config: TemplateSegmentConfig = {
        category: formData.category,
        display_order: formData.display_order,
        brevity_level: formData.brevity_level,
        terminology_style: formData.terminology_style,
      };

      await updateTemplateSegment(templateCode, segment.segment_code, config, getAccessToken());
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to update segment configuration');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">
            Edit Segment Configuration
          </h2>
          <p className="text-sm text-gray-600 mb-6">
            Configure settings for <strong>{segment.segment_name}</strong> in this template
          </p>

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Configuration Fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Category */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Category <span className="text-red-500">*</span>
                </label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value as 'core' | 'additional' | 'excluded' })}
                  required
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white"
                >
                  <option value="core">Core</option>
                  <option value="additional">Additional</option>
                  <option value="excluded">Excluded</option>
                </select>
              </div>

              {/* Display Order */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Display Order <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  value={formData.display_order}
                  onChange={(e) => setFormData({ ...formData, display_order: parseInt(e.target.value) })}
                  required
                  min="0"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white"
                />
              </div>

              {/* Brevity Level */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Brevity Level <span className="text-red-500">*</span>
                </label>
                <select
                  value={formData.brevity_level}
                  onChange={(e) => setFormData({ ...formData, brevity_level: e.target.value as BrevityLevel })}
                  required
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white"
                >
                  <option value="concise">Concise</option>
                  <option value="balanced">Balanced</option>
                  <option value="detailed">Detailed</option>
                </select>
              </div>

              {/* Terminology Style */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Terminology Style <span className="text-red-500">*</span>
                </label>
                <select
                  value={formData.terminology_style}
                  onChange={(e) => setFormData({ ...formData, terminology_style: e.target.value as TerminologyStyle })}
                  required
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white"
                >
                  <option value="medical_terms">Medical Terms</option>
                  <option value="simple_terms">Simple Terms</option>
                  <option value="as_spoken">As Spoken</option>
                </select>
              </div>
            </div>

            {/* Navigate to Definition */}
            {onNavigateToSegmentDefinition && (
              <div className="border-t border-gray-200 pt-4">
                <div className="flex items-start gap-3">
                  <svg className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <div className="flex-1">
                    <p className="text-sm text-gray-700 font-medium mb-2">
                      Need to edit the segment definition?
                    </p>
                    <p className="text-xs text-gray-600 mb-3">
                      View which templates use this segment and edit its global definition (prompt text, schema, name).
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        onNavigateToSegmentDefinition(segment.id);
                        onClose();
                      }}
                      className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                      Edit Segment Definition
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex justify-end gap-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="px-6 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

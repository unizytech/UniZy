'use client';

import React, { useState, useEffect } from 'react';
import type { BrevityLevel, TerminologyStyle } from '@lib/types';
import { useAuth } from '@lib/auth';
import { authGet, authPut, API_BASE_URL } from '@lib/apiClient';

interface SegmentConfigFormProps {
  segment: any; // Segment with consultation_types and templates arrays
  onSuccess: () => void;
  onCancel: () => void;
}

export function SegmentConfigForm({
  segment,
  onSuccess,
  onCancel,
}: SegmentConfigFormProps) {
  const { getAccessToken } = useAuth();
  // Build list of all associations
  const associations = [
    ...(segment.consultation_types || []).map((ct: any) => ({
      type: 'consultation_type' as const,
      id: ct.type_id,
      code: ct.type_code,
      name: ct.type_name,
      label: `Consultation Type: ${ct.type_name}`,
    })),
    ...(segment.templates || []).map((tpl: any) => ({
      type: 'template' as const,
      id: tpl.template_id,
      code: tpl.template_code,
      name: tpl.template_name || tpl.template_code,
      label: `Template: ${tpl.template_name || tpl.template_code}`,
    })),
  ];

  // Use the first association for config operations
  const primaryAssociation = associations.length > 0 ? associations[0] : null;

  const [formData, setFormData] = useState({
    default_category: 'core' as 'core' | 'additional',
    default_display_order: 999,
    default_brevity_level: 'balanced' as BrevityLevel,
    default_terminology_style: 'medical_terms' as TerminologyStyle,
  });

  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load configuration on mount
  useEffect(() => {
    const loadConfig = async () => {
      if (!primaryAssociation) {
        setInitialLoading(false);
        return;
      }

      setInitialLoading(true);
      setError(null);

      try {
        const endpoint =
          primaryAssociation.type === 'consultation_type'
            ? `/api/v1/summary/admin/consultation-type-segments/${primaryAssociation.id}/${segment.segment_code}`
            : `/api/v1/summary/admin/template-segments/${primaryAssociation.id}/${segment.segment_code}`;

        const response = await authGet(endpoint, getAccessToken());

        if (!response.ok) {
          throw new Error('Failed to load configuration');
        }

        const data = await response.json();

        setFormData({
          default_category: data.category || 'core',
          default_display_order: data.display_order || 999,
          default_brevity_level: data.brevity_level || 'balanced',
          default_terminology_style: data.terminology_style || 'medical_terms',
        });
      } catch (err: any) {
        setError(err.message || 'Failed to load configuration');
      } finally {
        setInitialLoading(false);
      }
    };

    loadConfig();
  }, [primaryAssociation?.id, primaryAssociation?.type, segment.segment_code]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!primaryAssociation) {
      setError('No association found to save configuration');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const endpoint =
        primaryAssociation.type === 'consultation_type'
          ? `/api/v1/summary/admin/consultation-type-segments/${primaryAssociation.id}/${segment.segment_code}`
          : `/api/v1/summary/admin/template-segments/${primaryAssociation.id}/${segment.segment_code}`;

      const response = await authPut(endpoint, getAccessToken(), {
        category: formData.default_category,
        display_order: formData.default_display_order,
        brevity_level: formData.default_brevity_level,
        terminology_style: formData.default_terminology_style,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update configuration');
      }

      onSuccess();
    } catch (err: any) {
      setError(err.message || 'Failed to update configuration');
    } finally {
      setLoading(false);
    }
  };

  // Check if segment has any associations
  const hasAssociations = associations.length > 0;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">
            Edit Segment Configuration
          </h2>
          <p className="text-sm text-gray-600 mb-6">
            Configure association-specific settings for <strong>{segment.segment_name}</strong>
          </p>

          {/* No associations warning */}
          {!hasAssociations && (
            <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-lg">
              <div className="flex items-start">
                <svg className="w-5 h-5 text-amber-600 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <div>
                  <p className="text-sm font-medium text-amber-800">
                    No Associations Found
                  </p>
                  <p className="text-xs text-amber-700 mt-1">
                    This segment is not assigned to any consultation type or template.
                    Use the "Assigned to" button in the segments list to assign it first.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={onCancel}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-medium transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          )}

          {hasAssociations && (
            <>
              {/* Loading state */}
              {initialLoading && (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
                  <span className="ml-3 text-gray-600">Loading configuration...</span>
                </div>
              )}

              {!initialLoading && (
                <>
                  {error && (
                    <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                      <p className="text-sm text-red-800">{error}</p>
                    </div>
                  )}

                  {/* Read-only association display */}
                  <div className="mb-6 p-3 bg-gray-50 border border-gray-200 rounded-lg">
                    <label className="block text-xs font-medium text-gray-500 mb-2">
                      Assigned To
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {associations.map((assoc) => (
                        <span
                          key={`${assoc.type}:${assoc.id}`}
                          className={`inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium ${
                            assoc.type === 'consultation_type'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-purple-100 text-purple-800'
                          }`}
                        >
                          {assoc.type === 'consultation_type' ? (
                            <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                            </svg>
                          )}
                          {assoc.name}
                        </span>
                      ))}
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      To manage assignments, use the "Assigned to" button in the segments list.
                    </p>
                  </div>

                  <form onSubmit={handleSubmit} className="space-y-6">
                    {/* Configuration Fields */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {/* Category */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Category <span className="text-red-500">*</span>
                        </label>
                        <select
                          value={formData.default_category}
                          onChange={(e) => setFormData({ ...formData, default_category: e.target.value as 'core' | 'additional' })}
                          required
                          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-gray-900"
                        >
                          <option value="core">Core</option>
                          <option value="additional">Additional</option>
                        </select>
                      </div>

                      {/* Display Order */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Display Order <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="number"
                          value={formData.default_display_order}
                          onChange={(e) => setFormData({ ...formData, default_display_order: parseInt(e.target.value) })}
                          required
                          min="0"
                          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-gray-900"
                        />
                      </div>

                      {/* Brevity Level */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Brevity Level <span className="text-red-500">*</span>
                        </label>
                        <select
                          value={formData.default_brevity_level}
                          onChange={(e) => setFormData({ ...formData, default_brevity_level: e.target.value as BrevityLevel })}
                          required
                          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-gray-900"
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
                          value={formData.default_terminology_style}
                          onChange={(e) => setFormData({ ...formData, default_terminology_style: e.target.value as TerminologyStyle })}
                          required
                          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-gray-900"
                        >
                          <option value="medical_terms">Medical Terms</option>
                          <option value="simple_terms">Simple Terms</option>
                          <option value="as_spoken">As Spoken</option>
                        </select>
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex justify-end gap-3 pt-4">
                      <button
                        type="button"
                        onClick={onCancel}
                        disabled={loading}
                        className="px-6 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium transition-colors disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={loading}
                        className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                      >
                        {loading ? 'Saving...' : 'Save Configuration'}
                      </button>
                    </div>
                  </form>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

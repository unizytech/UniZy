'use client';

/**
 * Template EHR Configuration Modal
 *
 * Allows administrators to configure which EHR types a template is mapped to,
 * and what URL suffix to use for each mapping (primarily for Neopead which has
 * different endpoints per template).
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';
import type { Template } from '@lib/types';

interface TemplateEhrConfigModalProps {
  template: Template;
  onClose: () => void;
}

interface EhrType {
  id: string;
  ehr_code: string;
  ehr_name: string;
  default_api_url: string | null;
}

interface TemplateEhrMapping {
  id: string;
  template_id: string;
  template_code: string;
  template_name: string;
  ehr_type_id: string;
  ehr_code: string;
  ehr_name: string;
  url_suffix: string | null;
  created_at: string;
}

export function TemplateEhrConfigModal({ template, onClose }: TemplateEhrConfigModalProps) {
  const { getAccessToken } = useAuth();

  // State
  const [ehrTypes, setEhrTypes] = useState<EhrType[]>([]);
  const [mappings, setMappings] = useState<TemplateEhrMapping[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Form state for adding new mapping
  const [addingNew, setAddingNew] = useState(false);
  const [newEhrTypeId, setNewEhrTypeId] = useState('');
  const [newUrlSuffix, setNewUrlSuffix] = useState('');

  // Form state for editing
  const [editingMappingId, setEditingMappingId] = useState<string | null>(null);
  const [editUrlSuffix, setEditUrlSuffix] = useState('');

  // Fetch EHR types
  const fetchEhrTypes = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/schools/ehr-types', token);

      if (!response.ok) {
        throw new Error('Failed to fetch EHR types');
      }

      const data = await response.json();
      setEhrTypes(data.ehr_types || []);
    } catch (err) {
      console.error('Failed to fetch EHR types:', err);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch existing mappings for this template
  const fetchMappings = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet(`/api/v1/schools/template-ehr?template_id=${template.id}`, token);

      if (!response.ok) {
        throw new Error('Failed to fetch template EHR mappings');
      }

      const data = await response.json();
      setMappings(data.mappings || []);
    } catch (err) {
      console.error('Failed to fetch mappings:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch mappings');
    }
  }, [template.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchEhrTypes(), fetchMappings()]);
      setLoading(false);
    };
    loadData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Get configured EHR type IDs (to disable in add dropdown)
  const getConfiguredEhrTypeIds = () => {
    return mappings.map(m => m.ehr_type_id);
  };

  // Handle add new mapping
  const handleAddMapping = async () => {
    if (!newEhrTypeId) {
      alert('Please select an EHR type');
      return;
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const response = await authPost('/api/v1/schools/template-ehr', token, {
        template_id: template.id,
        ehr_type_id: newEhrTypeId,
        url_suffix: newUrlSuffix || null
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to create mapping');
      }

      // Refresh mappings
      await fetchMappings();
      setAddingNew(false);
      setNewEhrTypeId('');
      setNewUrlSuffix('');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to create mapping');
    } finally {
      setSaving(false);
    }
  };

  // Handle update mapping
  const handleUpdateMapping = async (mappingId: string) => {
    setSaving(true);
    try {
      const token = getAccessToken();
      const response = await authPut(`/api/v1/schools/template-ehr/${mappingId}`, token, {
        url_suffix: editUrlSuffix || null
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update mapping');
      }

      // Refresh mappings
      await fetchMappings();
      setEditingMappingId(null);
      setEditUrlSuffix('');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update mapping');
    } finally {
      setSaving(false);
    }
  };

  // Handle delete mapping
  const handleDeleteMapping = async (mappingId: string, ehrName: string) => {
    if (!confirm(`Remove EHR mapping for ${ehrName}?`)) {
      return;
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const response = await authDelete(`/api/v1/schools/template-ehr/${mappingId}`, token);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to delete mapping');
      }

      // Refresh mappings
      await fetchMappings();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete mapping');
    } finally {
      setSaving(false);
    }
  };

  // Start editing
  const startEditing = (mapping: TemplateEhrMapping) => {
    setEditingMappingId(mapping.id);
    setEditUrlSuffix(mapping.url_suffix || '');
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="bg-orange-600 text-white p-6 rounded-t-lg">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">EHR Configuration</h2>
              <p className="text-orange-100 text-sm mt-1">
                {template.template_name} ({template.template_code})
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-white hover:bg-orange-700 rounded-lg p-2 transition-colors"
              title="Close"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500"></div>
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
              {error}
            </div>
          ) : (
            <>
              {/* Info */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <p className="text-sm text-blue-800">
                  Configure which EHR systems this template can send extractions to.
                  The URL suffix is appended to the school&apos;s base EHR URL (primarily used for Neopead).
                </p>
              </div>

              {/* Add new mapping button */}
              {!addingNew && (
                <button
                  onClick={() => setAddingNew(true)}
                  className="mb-4 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  + Add EHR Mapping
                </button>
              )}

              {/* Add new mapping form */}
              {addingNew && (
                <div className="mb-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                  <h4 className="text-sm font-medium text-gray-900 mb-3">Add New EHR Mapping</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">EHR Type</label>
                      <select
                        value={newEhrTypeId}
                        onChange={(e) => setNewEhrTypeId(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
                      >
                        <option value="">Select EHR type...</option>
                        {ehrTypes.map(type => (
                          <option
                            key={type.id}
                            value={type.id}
                            disabled={getConfiguredEhrTypeIds().includes(type.id)}
                          >
                            {type.ehr_name} {getConfiguredEhrTypeIds().includes(type.id) ? '(already configured)' : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">URL Suffix (optional)</label>
                      <input
                        type="text"
                        value={newUrlSuffix}
                        onChange={(e) => setNewUrlSuffix(e.target.value)}
                        placeholder="/store-daycare-transcribed-data"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mt-4">
                    <button
                      onClick={handleAddMapping}
                      disabled={saving || !newEhrTypeId}
                      className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      {saving ? 'Saving...' : 'Add'}
                    </button>
                    <button
                      onClick={() => {
                        setAddingNew(false);
                        setNewEhrTypeId('');
                        setNewUrlSuffix('');
                      }}
                      className="px-4 py-2 bg-gray-500 hover:bg-gray-600 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Existing mappings */}
              {mappings.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                  <p>No EHR mappings configured for this template.</p>
                  <p className="text-sm mt-1">Add a mapping to enable EHR integration.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {mappings.map((mapping) => (
                    <div
                      key={mapping.id}
                      className="p-4 bg-gray-50 rounded-lg border border-gray-200"
                    >
                      {editingMappingId === mapping.id ? (
                        // Edit mode
                        <div className="flex items-center gap-4">
                          <div className="flex-1">
                            <label className="block text-xs text-gray-600 mb-1">
                              {mapping.ehr_name} - URL Suffix
                            </label>
                            <input
                              type="text"
                              value={editUrlSuffix}
                              onChange={(e) => setEditUrlSuffix(e.target.value)}
                              placeholder="/store-daycare-transcribed-data"
                              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
                            />
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleUpdateMapping(mapping.id)}
                              disabled={saving}
                              className="px-3 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => {
                                setEditingMappingId(null);
                                setEditUrlSuffix('');
                              }}
                              className="px-3 py-2 bg-gray-500 hover:bg-gray-600 text-white rounded-lg text-sm font-medium transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        // View mode
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="inline-block px-2 py-1 bg-orange-100 text-orange-700 text-xs font-medium rounded">
                              {mapping.ehr_name}
                            </span>
                            {mapping.url_suffix && (
                              <span className="ml-3 text-sm text-gray-600 font-mono">
                                {mapping.url_suffix}
                              </span>
                            )}
                            {!mapping.url_suffix && (
                              <span className="ml-3 text-sm text-gray-400 italic">
                                No suffix configured
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => startEditing(mapping)}
                              className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                              title="Edit"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                              </svg>
                            </button>
                            <button
                              onClick={() => handleDeleteMapping(mapping.id, mapping.ehr_name)}
                              disabled={saving}
                              className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
                              title="Remove"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="bg-gray-50 px-6 py-4 rounded-b-lg border-t border-gray-200">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

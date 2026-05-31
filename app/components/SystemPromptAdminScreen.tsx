'use client';

/**
 * System Prompt Admin Screen
 *
 * Admin interface for managing dynamic system prompts:
 * 1. Prompt Components - Reusable building blocks (role, guidelines, validation, etc.)
 * 2. Prompt Configurations - Composed configurations from components
 * 3. Consultation Type Assignments - Map configurations to consultation types
 */

import React, { useState, useEffect } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useAuth } from '@lib/auth';
import { authGet, authPost, authPut, authDelete, authPatch } from '@lib/apiClient';

// Types
interface PromptComponent {
  id: string;
  component_code: string;
  component_type: string;
  component_name: string;
  content_text: string;      // Backend field name
  component_text?: string;   // Legacy alias
  content_version: string;   // Backend field name
  version?: string;          // Legacy alias
  description?: string;
  is_base_component: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface PromptConfiguration {
  id: string;
  config_code?: string;
  config_name: string;
  config_description?: string;
  base_consultation_type?: string;
  config_version?: string;  // Backend field name
  version?: string;         // Alias for compatibility
  is_active: boolean;
  assembled_prompt?: string;
  assembled_system_prompt?: string;  // Full assembled prompt text
  last_assembled_at?: string;
  token_count?: number;
  estimated_token_count?: number;  // Token estimate from assembly
  component_count?: number;  // Added by list query
  components?: ConfigComponent[];
  component_ids?: string[];  // Added when fetching for edit
  created_at: string;
}

interface ConfigComponent {
  component_id: string;
  component_type: string;
  component_name: string;
  order_index: number;
}

interface ConsultationTypeAssignment {
  consultation_type_code: string;
  config_id: string;
  config_name: string;
  is_active: boolean;
}

type ViewMode = 'components' | 'configurations' | 'assignments';

const COMPONENT_TYPES = [
  { value: 'role', label: 'Role Definition', color: 'bg-blue-100 text-blue-800' },
  { value: 'capabilities', label: 'Capabilities', color: 'bg-green-100 text-green-800' },
  { value: 'critical_guidelines', label: 'Critical Guidelines', color: 'bg-red-100 text-red-800' },
  { value: 'processing_info', label: 'Processing Info', color: 'bg-purple-100 text-purple-800' },
  { value: 'processing_rules', label: 'Processing Rules', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'special_handling', label: 'Special Handling', color: 'bg-orange-100 text-orange-800' },
  { value: 'validation_checklist', label: 'Validation Checklist', color: 'bg-indigo-100 text-indigo-800' },
];

export function SystemPromptAdminScreen() {
  const { getAccessToken } = useAuth();
  const [viewMode, setViewMode] = useState<ViewMode>('components');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Data states
  const [components, setComponents] = useState<PromptComponent[]>([]);
  const [configurations, setConfigurations] = useState<PromptConfiguration[]>([]);
  const [assignments, setAssignments] = useState<ConsultationTypeAssignment[]>([]);
  const [consultationTypes, setConsultationTypes] = useState<any[]>([]);

  // Modal states
  const [showComponentModal, setShowComponentModal] = useState(false);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [editingComponent, setEditingComponent] = useState<PromptComponent | null>(null);
  const [editingConfig, setEditingConfig] = useState<PromptConfiguration | null>(null);

  // Preview modal state
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewContent, setPreviewContent] = useState<{ prompt: string; charCount: number; tokenCount: number } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Filter states
  const [componentTypeFilter, setComponentTypeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Load all data on mount (for accurate tab counts)
  useEffect(() => {
    loadConsultationTypes();
    loadComponents();
    loadConfigurations();
    loadAssignments();
  }, []);

  // Reload current view data when tab changes
  useEffect(() => {
    if (viewMode === 'components') {
      loadComponents();
    } else if (viewMode === 'configurations') {
      loadConfigurations();
    } else if (viewMode === 'assignments') {
      loadAssignments();
    }
  }, [viewMode]);

  const loadConsultationTypes = async () => {
    try {
      const response = await authGet('/api/v1/summary/consultation-types', getAccessToken());
      if (!response.ok) throw new Error('Failed to load consultation types');
      const data = await response.json();
      setConsultationTypes(data.consultation_types || []);
    } catch (err) {
      console.error('Error loading consultation types:', err);
    }
  };

  const loadComponents = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await authGet('/api/v1/system-prompts/components', getAccessToken());
      if (!response.ok) throw new Error('Failed to load components');
      const data = await response.json();
      setComponents(data.components || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load components');
    } finally {
      setLoading(false);
    }
  };

  const loadConfigurations = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await authGet('/api/v1/system-prompts/configurations', getAccessToken());
      if (!response.ok) throw new Error('Failed to load configurations');
      const data = await response.json();
      setConfigurations(data.configurations || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load configurations');
    } finally {
      setLoading(false);
    }
  };

  const loadAssignments = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await authGet('/api/v1/system-prompts/consultation-type-assignments', getAccessToken());
      if (!response.ok) throw new Error('Failed to load assignments');
      const data = await response.json();
      setAssignments(data.assignments || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load assignments');
    } finally {
      setLoading(false);
    }
  };

  const getComponentTypeStyle = (type: string) => {
    const typeInfo = COMPONENT_TYPES.find(t => t.value === type);
    return typeInfo?.color || 'bg-gray-100 text-gray-800';
  };

  const filteredComponents = components.filter(comp => {
    if (componentTypeFilter !== 'all' && comp.component_type !== componentTypeFilter) {
      return false;
    }
    if (searchQuery.trim()) {
      const search = searchQuery.toLowerCase();
      const text = comp.content_text || comp.component_text || '';
      return (
        comp.component_name.toLowerCase().includes(search) ||
        text.toLowerCase().includes(search) ||
        comp.component_type.toLowerCase().includes(search) ||
        comp.component_code?.toLowerCase().includes(search)
      );
    }
    return true;
  }).sort((a, b) => (a.component_name || '').localeCompare(b.component_name || ''));

  const filteredConfigurations = configurations.filter(config => {
    if (searchQuery.trim()) {
      const search = searchQuery.toLowerCase();
      return (
        config.config_name.toLowerCase().includes(search) ||
        (config.config_description?.toLowerCase().includes(search))
      );
    }
    return true;
  }).sort((a, b) => (a.config_name || '').localeCompare(b.config_name || ''));

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">System Prompt Management</h1>
            <p className="text-sm text-gray-600 mt-1">
              {viewMode === 'components'
                ? 'Manage reusable prompt building blocks'
                : viewMode === 'configurations'
                ? 'Compose configurations from components'
                : 'Assign configurations to session types'}
            </p>
          </div>
          {viewMode === 'components' && (
            <button
              onClick={() => {
                setEditingComponent(null);
                setShowComponentModal(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              + Create Component
            </button>
          )}
          {viewMode === 'configurations' && (
            <button
              onClick={() => {
                setEditingConfig(null);
                setShowConfigModal(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              + Create Configuration
            </button>
          )}
        </div>
      </div>

      {/* View Mode Tabs */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode('components')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'components'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            🧩 Components ({components.length})
          </button>
          <button
            onClick={() => setViewMode('configurations')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'configurations'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            📋 Configurations ({configurations.length})
          </button>
          <button
            onClick={() => setViewMode('assignments')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'assignments'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            🔗 Type Assignments ({assignments.length})
          </button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center">
            <svg className="w-5 h-5 text-red-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clipRule="evenodd"
              />
            </svg>
            <p className="text-red-800">{error}</p>
          </div>
        </div>
      )}

      {/* Components View */}
      {viewMode === 'components' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                Prompt Components ({filteredComponents.length} of {components.length})
              </h2>
              <div className="flex items-center gap-2">
                <select
                  value={componentTypeFilter}
                  onChange={(e) => setComponentTypeFilter(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                >
                  <option value="all">All Types</option>
                  {COMPONENT_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search components..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
            />
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading components...</p>
            </div>
          ) : filteredComponents.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No components found</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {filteredComponents.map((component) => (
                <div key={component.id} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-semibold text-gray-900">
                          {component.component_name}
                        </h3>
                        <span className={`text-xs px-2 py-0.5 rounded ${getComponentTypeStyle(component.component_type)}`}>
                          {component.component_type}
                        </span>
                        <span className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded">
                          v{component.content_version || component.version || '1.0.0'}
                        </span>
                        {!component.is_active && (
                          <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                            Inactive
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-600 mt-2 line-clamp-2">
                        {(component.content_text || component.component_text || '').substring(0, 200)}...
                      </p>
                      <p className="text-xs text-gray-400 mt-2">
                        {(component.content_text || component.component_text || '').length} chars | v{component.content_version || component.version || '1.0.0'} | Updated: {new Date(component.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <button
                        onClick={async () => {
                          try {
                            const response = await authPost(
                              `/api/v1/system-prompts/components/${component.id}/toggle-active`,
                              getAccessToken()
                            );
                            if (!response.ok) throw new Error('Failed to toggle');
                            loadComponents();
                          } catch (err) {
                            setError(err instanceof Error ? err.message : 'Failed to toggle');
                          }
                        }}
                        className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                          component.is_active
                            ? 'bg-amber-100 hover:bg-amber-200 text-amber-700'
                            : 'bg-green-100 hover:bg-green-200 text-green-700'
                        }`}
                      >
                        {component.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                      <button
                        onClick={() => {
                          setEditingComponent(component);
                          setShowComponentModal(true);
                        }}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                      >
                        Edit
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Configurations View */}
      {viewMode === 'configurations' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Prompt Configurations ({filteredConfigurations.length})
            </h2>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search configurations..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
            />
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading configurations...</p>
            </div>
          ) : filteredConfigurations.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No configurations found</p>
              <button
                onClick={() => setShowConfigModal(true)}
                className="text-blue-600 hover:text-blue-700 font-medium mt-2"
              >
                Create your first configuration
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {filteredConfigurations.map((config) => (
                <div key={config.id} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-lg font-semibold text-gray-900">
                          {config.config_name}
                        </h3>
                        <span className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded">
                          v{config.config_version || config.version || '1.0.0'}
                        </span>
                        {config.assembled_system_prompt && (
                          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                            {(config.assembled_system_prompt.length || 0).toLocaleString()} chars
                          </span>
                        )}
                        {config.estimated_token_count && (
                          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                            ~{config.estimated_token_count.toLocaleString()} tokens
                          </span>
                        )}
                        {!config.is_active && (
                          <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                            Inactive
                          </span>
                        )}
                        {config.base_consultation_type && (
                          <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded">
                            {config.base_consultation_type}
                          </span>
                        )}
                      </div>
                      {config.config_description && (
                        <p className="text-sm text-gray-600 mt-1">{config.config_description}</p>
                      )}
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <span>Components: {config.component_count ?? config.components?.length ?? 0}</span>
                        {config.token_count && <span>Tokens: ~{config.token_count}</span>}
                        {config.last_assembled_at && (
                          <span>Last assembled: {new Date(config.last_assembled_at).toLocaleString()}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <button
                        onClick={async () => {
                          try {
                            // Fetch components for this config before editing
                            const response = await authGet(
                              `/api/v1/system-prompts/configurations/${config.id}/components`,
                              getAccessToken()
                            );
                            if (response.ok) {
                              const data = await response.json();
                              // Map components to component_ids
                              const componentIds = (data.components || []).map((c: any) => c.component_id);
                              setEditingConfig({ ...config, components: data.components, component_ids: componentIds });
                            } else {
                              setEditingConfig(config);
                            }
                            setShowConfigModal(true);
                          } catch (err) {
                            setEditingConfig(config);
                            setShowConfigModal(true);
                          }
                        }}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                      >
                        Edit
                      </button>
                      <button
                        onClick={async () => {
                          setPreviewLoading(true);
                          setShowPreviewModal(true);
                          try {
                            const response = await authGet(
                              `/api/v1/system-prompts/configurations/${config.id}/preview`,
                              getAccessToken()
                            );
                            if (!response.ok) throw new Error('Failed to preview');
                            const data = await response.json();
                            setPreviewContent({
                              prompt: data.assembled_prompt,
                              charCount: data.character_count,
                              tokenCount: data.estimated_tokens
                            });
                          } catch (err) {
                            setError(err instanceof Error ? err.message : 'Failed to preview');
                            setShowPreviewModal(false);
                          } finally {
                            setPreviewLoading(false);
                          }
                        }}
                        className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                      >
                        Preview
                      </button>
                      <button
                        onClick={async () => {
                          try {
                            const response = await authPost(
                              `/api/v1/system-prompts/configurations/${config.id}/assemble`,
                              getAccessToken()
                            );
                            if (!response.ok) throw new Error('Failed to assemble');
                            loadConfigurations();
                          } catch (err) {
                            setError(err instanceof Error ? err.message : 'Failed to assemble');
                          }
                        }}
                        className="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                      >
                        Assemble
                      </button>
                      <button
                        onClick={async () => {
                          if (!confirm(`Delete configuration "${config.config_name}"?`)) return;
                          try {
                            const response = await authDelete(
                              `/api/v1/system-prompts/configurations/${config.id}`,
                              getAccessToken()
                            );
                            if (!response.ok) throw new Error('Failed to delete');
                            loadConfigurations();
                          } catch (err) {
                            setError(err instanceof Error ? err.message : 'Failed to delete');
                          }
                        }}
                        className="bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Assignments View */}
      {viewMode === 'assignments' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">
              Session Type Assignments
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              Map prompt configurations to session types
            </p>
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading assignments...</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {[...consultationTypes].sort((a, b) => (a.type_name || '').localeCompare(b.type_name || '')).map((type) => {
                const assignment = assignments.find(a => a.consultation_type_code === type.type_code);
                return (
                  <div key={type.type_code} className="p-4 hover:bg-gray-50 transition-colors">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-gray-900">
                          {type.type_name}
                        </h3>
                        <p className="text-sm text-gray-500">{type.type_code}</p>
                      </div>
                      <div className="flex items-center gap-4">
                        <select
                          value={assignment?.config_id || ''}
                          onChange={async (e) => {
                            try {
                              const configId = e.target.value;
                              if (configId) {
                                // Assign new config (replaces existing and sets as active)
                                const response = await authPost(
                                  `/api/v1/system-prompts/consultation-types/${type.type_code}/assign`,
                                  getAccessToken(),
                                  { config_id: configId }
                                );
                                if (!response.ok) throw new Error('Failed to assign');
                              } else if (assignment) {
                                // Remove existing assignment when "-- Not Assigned --" selected
                                const response = await authDelete(
                                  `/api/v1/system-prompts/consultation-types/${type.type_code}/configs/${assignment.config_id}`,
                                  getAccessToken()
                                );
                                if (!response.ok) throw new Error('Failed to unassign');
                              }
                              loadAssignments();
                            } catch (err) {
                              setError(err instanceof Error ? err.message : 'Failed to update assignment');
                            }
                          }}
                          className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white min-w-[200px]"
                        >
                          <option value="">-- Not Assigned --</option>
                          {[...configurations].sort((a, b) => (a.config_name || '').localeCompare(b.config_name || '')).map(config => (
                            <option key={config.id} value={config.id}>
                              {config.config_name}
                            </option>
                          ))}
                        </select>
                        {assignment && (
                          <span className={`text-xs px-2 py-1 rounded ${
                            assignment.is_active
                              ? 'bg-green-100 text-green-700'
                              : 'bg-amber-100 text-amber-700'
                          }`}>
                            {assignment.is_active ? 'Active' : 'Inactive'}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Component Modal */}
      {showComponentModal && (
        <ComponentModal
          component={editingComponent}
          allComponents={components}
          onClose={() => {
            setShowComponentModal(false);
            setEditingComponent(null);
          }}
          onSave={async (data) => {
            const endpoint = editingComponent
              ? `/api/v1/system-prompts/components/${editingComponent.id}`
              : `/api/v1/system-prompts/components`;

            const response = editingComponent
              ? await authPut(endpoint, getAccessToken(), data)
              : await authPost(endpoint, getAccessToken(), data);

            if (!response.ok) {
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.detail || 'Failed to save component');
            }

            // Success - close modal and refresh list
            setShowComponentModal(false);
            setEditingComponent(null);
            loadComponents();
          }}
        />
      )}

      {/* Configuration Modal */}
      {showConfigModal && (
        <ConfigurationModal
          config={editingConfig}
          components={components}
          onClose={() => {
            setShowConfigModal(false);
            setEditingConfig(null);
          }}
          onSave={async (data) => {
            const endpoint = editingConfig
              ? `/api/v1/system-prompts/configurations/${editingConfig.id}`
              : `/api/v1/system-prompts/configurations`;

            const response = editingConfig
              ? await authPut(endpoint, getAccessToken(), data)
              : await authPost(endpoint, getAccessToken(), data);

            if (!response.ok) {
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.detail || 'Failed to save configuration');
            }

            // Success - close modal and refresh list
            setShowConfigModal(false);
            setEditingConfig(null);
            loadConfigurations();
          }}
        />
      )}

      {/* Preview Modal */}
      {showPreviewModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-xl font-bold text-gray-900">System Prompt Preview</h2>
              <button
                onClick={() => {
                  setShowPreviewModal(false);
                  setPreviewContent(null);
                }}
                className="text-gray-500 hover:text-gray-700"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {previewLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <span className="ml-3 text-gray-600">Loading preview...</span>
                </div>
              ) : previewContent ? (
                <pre className="whitespace-pre-wrap text-sm text-gray-800 font-mono bg-gray-50 p-4 rounded-lg border">
                  {previewContent.prompt}
                </pre>
              ) : (
                <p className="text-gray-500 text-center py-8">No preview available</p>
              )}
            </div>
            <div className="p-4 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
              <div className="text-sm text-gray-600">
                {previewContent && (
                  <>
                    <span className="mr-4">Characters: {previewContent.charCount.toLocaleString()}</span>
                    <span>Estimated tokens: ~{previewContent.tokenCount.toLocaleString()}</span>
                  </>
                )}
              </div>
              <button
                onClick={() => {
                  setShowPreviewModal(false);
                  setPreviewContent(null);
                }}
                className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Component Modal
interface ComponentModalProps {
  component: PromptComponent | null;
  allComponents: PromptComponent[];  // All components for clone feature
  onClose: () => void;
  onSave: (data: Partial<PromptComponent>) => Promise<void>;
}

function ComponentModal({ component, allComponents, onClose, onSave }: ComponentModalProps) {
  // Generate a component_code from component_name: UPPER_SNAKE_CASE
  const generateCode = (name: string) => {
    return name.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_|_$/g, '');
  };

  const [formData, setFormData] = useState({
    component_code: component?.component_code || '',
    component_type: component?.component_type || 'role',
    component_name: component?.component_name || '',
    content_text: component?.content_text || component?.component_text || '',
    content_version: component?.content_version || component?.version || '1.0.0',
    description: component?.description || '',
    is_base_component: component?.is_base_component ?? false,
  });

  // Loading and error state for save operation
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Clone from existing component
  const handleCloneFrom = (sourceId: string) => {
    if (!sourceId) return;
    const source = allComponents.find(c => c.id === sourceId);
    if (source) {
      const newName = `${source.component_name} (Copy)`;
      setFormData({
        component_code: generateCode(newName), // Auto-generate from new name
        component_type: source.component_type,
        component_name: newName,
        content_text: source.content_text || source.component_text || '',
        content_version: '1.0.0',
        description: source.description || '',
        is_base_component: source.is_base_component,
      });
    }
  };

  // Auto-generate code from name if creating new component
  const handleNameChange = (name: string) => {
    const updates: any = { component_name: name };
    if (!component) {
      // Auto-generate code for new components
      updates.component_code = generateCode(name);
    }
    setFormData(prev => ({ ...prev, ...updates }));
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">
            {component ? 'Edit Component' : 'Create Component'}
          </h2>
        </div>

        <div className="p-6 space-y-4">
          {/* Clone from existing - only show when creating new component */}
          {!component && allComponents.length > 0 && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <label className="block text-sm font-medium text-blue-800 mb-2">
                📋 Clone from existing component (optional)
              </label>
              <select
                onChange={(e) => handleCloneFrom(e.target.value)}
                className="w-full px-3 py-2 border border-blue-300 rounded-lg text-gray-900 bg-white"
                defaultValue=""
              >
                <option value="">-- Start from scratch --</option>
                {COMPONENT_TYPES.map(type => {
                  const typeComponents = allComponents.filter(c => c.component_type === type.value).sort((a, b) => (a.component_name || '').localeCompare(b.component_name || ''));
                  if (typeComponents.length === 0) return null;
                  return (
                    <optgroup key={type.value} label={type.label}>
                      {typeComponents.map(c => (
                        <option key={c.id} value={c.id}>
                          {c.component_name} (v{c.content_version || c.version || '1.0.0'})
                        </option>
                      ))}
                    </optgroup>
                  );
                })}
              </select>
              <p className="text-xs text-blue-600 mt-1">
                Select a component to copy its content, then modify as needed
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Component Type *
              </label>
              <select
                value={formData.component_type}
                onChange={(e) => setFormData({ ...formData, component_type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              >
                {COMPONENT_TYPES.map(type => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Version
              </label>
              <input
                type="text"
                value={formData.content_version}
                onChange={(e) => setFormData({ ...formData, content_version: e.target.value })}
                placeholder="1.0.0"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Component Name *
            </label>
            <input
              type="text"
              value={formData.component_name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="e.g., Medical Transcriber Role v2"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Component Code * <span className="text-gray-500 font-normal">(auto-generated from name)</span>
            </label>
            <input
              type="text"
              value={formData.component_code}
              onChange={(e) => setFormData({ ...formData, component_code: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '') })}
              placeholder="e.g., ROLE_MEDICAL_AI"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white font-mono"
              disabled={!!component}
            />
            {!component && (
              <p className="text-xs text-gray-500 mt-1">
                Unique identifier. Cannot be changed after creation.
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <input
              type="text"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Brief description of this component's purpose"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Prompt Text *
            </label>
            <textarea
              value={formData.content_text}
              onChange={(e) => setFormData({ ...formData, content_text: e.target.value })}
              rows={12}
              placeholder="Enter the prompt component text..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white font-mono text-sm"
            />
            <p className="text-xs text-gray-500 mt-1">
              {formData.content_text.length} characters
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_base_component"
                checked={formData.is_base_component}
                onChange={(e) => setFormData({ ...formData, is_base_component: e.target.checked })}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded"
              />
              <label htmlFor="is_base_component" className="text-sm text-gray-700">
                Base/Template Component
              </label>
            </div>
          </div>

          {/* Error display */}
          {saveError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <div className="flex items-center">
                <svg className="w-5 h-5 text-red-600 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
                <p className="text-red-800 text-sm">{saveError}</p>
              </div>
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={async () => {
              setSaving(true);
              setSaveError(null);
              try {
                await onSave(formData);
              } catch (err) {
                setSaveError(err instanceof Error ? err.message : 'Failed to save component');
              } finally {
                setSaving(false);
              }
            }}
            disabled={saving || !formData.component_code || !formData.component_name || !formData.content_text}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {saving && (
              <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            )}
            {saving ? (component ? 'Updating...' : 'Creating...') : (component ? 'Update' : 'Create')}
          </button>
        </div>
      </div>
    </div>
  );
}

// Sortable Item for drag-and-drop
interface SortableItemProps {
  id: string;
  component: PromptComponent;
  index: number;
  onRemove: (id: string) => void;
}

function SortableItem({ id, component, index, onRemove }: SortableItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const typeInfo = COMPONENT_TYPES.find(t => t.value === component.component_type);

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-3 p-3 bg-white border rounded-lg ${isDragging ? 'shadow-lg' : 'shadow-sm'}`}
    >
      <div
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8h16M4 16h16" />
        </svg>
      </div>
      <span className="text-sm font-medium text-gray-500 w-6">{index + 1}.</span>
      <div className="flex-1">
        <span className="text-sm font-medium text-gray-900">{component.component_name}</span>
        <span className="text-xs text-gray-500 ml-1">
          (v{component.content_version || component.version || '1.0.0'})
        </span>
        <span className={`ml-2 text-xs px-2 py-0.5 rounded ${typeInfo?.color || 'bg-gray-100 text-gray-700'}`}>
          {typeInfo?.label || component.component_type}
        </span>
      </div>
      <button
        onClick={() => onRemove(id)}
        className="text-gray-400 hover:text-red-600 transition-colors"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// Configuration Modal
interface ConfigurationModalProps {
  config: PromptConfiguration | null;
  components: PromptComponent[];
  onClose: () => void;
  onSave: (data: any) => Promise<void>;
}

function ConfigurationModal({ config, components, onClose, onSave }: ConfigurationModalProps) {
  // Generate a config_code from config_name: UPPER_SNAKE_CASE
  const generateCode = (name: string) => {
    return name.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_|_$/g, '');
  };

  const [formData, setFormData] = useState({
    config_code: (config as any)?.config_code || '',
    config_name: config?.config_name || '',
    config_description: config?.config_description || '',
    version: (config as any)?.config_version || config?.version || '1.0',
    is_active: config?.is_active ?? true,
    // Check for component_ids first (set when fetching), then try to extract from components array
    component_ids: (config as any)?.component_ids || config?.components?.map(c => c.component_id) || [],
  });

  // Loading and error state for save operation
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Handle drag end
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      setFormData(prev => {
        const oldIndex = prev.component_ids.indexOf(active.id as string);
        const newIndex = prev.component_ids.indexOf(over.id as string);
        return {
          ...prev,
          component_ids: arrayMove(prev.component_ids, oldIndex, newIndex),
        };
      });
    }
  };

  // Auto-generate code from name if creating new config
  const handleNameChange = (name: string) => {
    const updates: any = { config_name: name };
    if (!config) {
      updates.config_code = generateCode(name);
    }
    setFormData(prev => ({ ...prev, ...updates }));
  };

  const activeComponents = components.filter(c => c.is_active);
  const groupedComponents = COMPONENT_TYPES.reduce((acc, type) => {
    acc[type.value] = activeComponents.filter(c => c.component_type === type.value).sort((a, b) => (a.component_name || '').localeCompare(b.component_name || ''));
    return acc;
  }, {} as Record<string, PromptComponent[]>);

  const toggleComponent = (componentId: string) => {
    setFormData(prev => ({
      ...prev,
      component_ids: prev.component_ids.includes(componentId)
        ? prev.component_ids.filter((id: string) => id !== componentId)
        : [...prev.component_ids, componentId]
    }));
  };

  // Get selected components in order
  const selectedComponents: PromptComponent[] = formData.component_ids
    .map((id: string) => components.find((c: PromptComponent) => c.id === id))
    .filter((c: PromptComponent | undefined): c is PromptComponent => c !== undefined);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">
            {config ? 'Edit Configuration' : 'Create Configuration'}
          </h2>
        </div>

        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Configuration Name *
              </label>
              <input
                type="text"
                value={formData.config_name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="e.g., OP Session v2"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Version
              </label>
              <input
                type="text"
                value={formData.version}
                onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Configuration Code * <span className="text-gray-500 font-normal">(auto-generated from name)</span>
            </label>
            <input
              type="text"
              value={formData.config_code}
              onChange={(e) => setFormData({ ...formData, config_code: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '') })}
              placeholder="e.g., OP_CONSULTATION_V2"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white font-mono"
              disabled={!!config}
            />
            {!config && (
              <p className="text-xs text-gray-500 mt-1">
                Unique identifier. Cannot be changed after creation.
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formData.config_description}
              onChange={(e) => setFormData({ ...formData, config_description: e.target.value })}
              rows={2}
              placeholder="Brief description of this configuration..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Component Selection (Checkboxes) */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Available Components
              </label>
              <div className="border border-gray-200 rounded-lg p-4 max-h-[300px] overflow-y-auto">
                {COMPONENT_TYPES.map(type => (
                  <div key={type.value} className="mb-4 last:mb-0">
                    <h4 className={`text-sm font-medium px-2 py-1 rounded mb-2 ${type.color}`}>
                      {type.label}
                    </h4>
                    {groupedComponents[type.value]?.length === 0 ? (
                      <p className="text-xs text-gray-400 ml-2">No components</p>
                    ) : (
                      <div className="space-y-1">
                        {groupedComponents[type.value]?.map(comp => (
                          <label
                            key={comp.id}
                            className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded cursor-pointer"
                          >
                            <input
                              type="checkbox"
                              checked={formData.component_ids.includes(comp.id)}
                              onChange={() => toggleComponent(comp.id)}
                              className="w-4 h-4 text-blue-600 border-gray-300 rounded"
                            />
                            <span className="text-sm text-gray-900">
                              {comp.component_name}
                              <span className="text-xs text-gray-500 ml-1">
                                (v{comp.content_version || comp.version || '1.0.0'})
                              </span>
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Selected Components (Drag to reorder) */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Selected Order ({formData.component_ids.length} components)
                {formData.component_ids.length > 0 && (
                  <span className="text-gray-500 font-normal ml-2">- drag to reorder</span>
                )}
              </label>
              <div className="border border-gray-200 rounded-lg p-4 max-h-[300px] overflow-y-auto bg-gray-50">
                {selectedComponents.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-8">
                    Select components from the left to add them here
                  </p>
                ) : (
                  <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragEnd={handleDragEnd}
                  >
                    <SortableContext
                      items={formData.component_ids}
                      strategy={verticalListSortingStrategy}
                    >
                      <div className="space-y-2">
                        {selectedComponents.map((comp: PromptComponent, index: number) => (
                          <SortableItem
                            key={comp.id}
                            id={comp.id}
                            component={comp}
                            index={index}
                            onRemove={toggleComponent}
                          />
                        ))}
                      </div>
                    </SortableContext>
                  </DndContext>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="config_is_active"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded"
            />
            <label htmlFor="config_is_active" className="text-sm text-gray-700">
              Active
            </label>
          </div>

          {/* Error display */}
          {saveError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <div className="flex items-center">
                <svg className="w-5 h-5 text-red-600 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
                <p className="text-red-800 text-sm">{saveError}</p>
              </div>
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={async () => {
              setSaving(true);
              setSaveError(null);
              try {
                await onSave(formData);
              } catch (err) {
                setSaveError(err instanceof Error ? err.message : 'Failed to save configuration');
              } finally {
                setSaving(false);
              }
            }}
            disabled={saving || !formData.config_code || !formData.config_name || formData.component_ids.length === 0}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {saving && (
              <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            )}
            {saving ? (config ? 'Updating...' : 'Creating...') : (config ? 'Update' : 'Create')}
          </button>
        </div>
      </div>
    </div>
  );
}

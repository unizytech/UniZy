'use client';

/**
 * Processing Modes Admin Screen
 *
 * Allows administrators to:
 * - View all processing modes
 * - Create new processing modes
 * - Edit existing modes (models, settings)
 * - Set default mode
 * - Activate/deactivate modes
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { authGet, authPost, authPut, authPatch, authDelete } from '@lib/apiClient';
import { ProcessingMode } from '@lib/types';

interface ModelOption {
  value: string;
  label: string;
  tier: string;
}

interface AvailableModels {
  batch_models: ModelOption[];
  live_models: ModelOption[];
  extraction_models: ModelOption[];
  merge_models: ModelOption[];
  triage_models: ModelOption[];
  compare_models: ModelOption[];
  emotion_models: ModelOption[];
  insights_models: ModelOption[];
  validator_models: ModelOption[];
}

const TRANSCRIPTION_APIS = [
  { value: 'gemini_batch', label: 'Gemini Batch API' },
  { value: 'gemini_live', label: 'Gemini Live API (Real-time)' },
];

interface ProcessingModeForm {
  mode_code: string;
  mode_name: string;
  description: string;
  transcription_api: 'gemini_batch' | 'gemini_live';
  transcription_model: string;
  extraction_model: string;
  triage_model: string;
  merge_model: string;
  compare_model: string;
  emotion_model: string;
  insights_model: string;
  validator_model: string;
  estimated_time_seconds: number;
  display_order: number;
  is_active: boolean;
}

const DEFAULT_FORM: ProcessingModeForm = {
  mode_code: '',
  mode_name: '',
  description: '',
  transcription_api: 'gemini_batch',
  transcription_model: 'gemini-2.5-flash',
  extraction_model: 'gemini-2.5-pro',
  triage_model: 'gemini-2.5-flash',
  merge_model: 'gemini-3.1-pro-preview',  // Gemini API (use gemini-3-pro for Vertex AI)
  compare_model: 'gemini-2.5-flash',
  emotion_model: 'gemini-2.5-flash',
  insights_model: 'gemini-2.5-flash',
  validator_model: 'gemini-2.5-flash',
  estimated_time_seconds: 30,
  display_order: 999,
  is_active: true,
};

type TabType = 'processing_modes' | 'app_settings';

export function ProcessingModesAdminScreen() {
  const { getAccessToken } = useAuth();

  // Tab state
  const [activeTab, setActiveTab] = useState<TabType>('processing_modes');

  // Processing Modes state
  const [modes, setModes] = useState<ProcessingMode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [showModal, setShowModal] = useState(false);
  const [editingMode, setEditingMode] = useState<ProcessingMode | null>(null);

  // Form state
  const [formData, setFormData] = useState<ProcessingModeForm>(DEFAULT_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Search
  const [searchTerm, setSearchTerm] = useState('');

  // Available models from API
  const [availableModels, setAvailableModels] = useState<AvailableModels>({
    batch_models: [],
    live_models: [],
    extraction_models: [],
    merge_models: [],
    triage_models: [],
    compare_models: [],
    emotion_models: [],
    insights_models: [],
    validator_models: [],
  });

  // App Settings state
  const [useVertexAi, setUseVertexAi] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSuccess, setSettingsSuccess] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);

  // Fetch modes
  const fetchModes = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/admin/processing-modes?include_inactive=true', token);

      if (!response.ok) {
        throw new Error(`Failed to fetch processing modes: ${response.statusText}`);
      }

      const data = await response.json();
      setModes(data.modes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch processing modes');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch available models from models_master table
  const fetchAvailableModels = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/admin/processing-modes/models/available', token);
      if (response.ok) {
        const data = await response.json();
        setAvailableModels({
          batch_models: data.batch_models || [],
          live_models: data.live_models || [],
          extraction_models: data.extraction_models || [],
          merge_models: data.merge_models || [],
          triage_models: data.triage_models || [],
          compare_models: data.compare_models || [],
          emotion_models: data.emotion_models || [],
          insights_models: data.insights_models || [],
          validator_models: data.validator_models || [],
        });
      }
    } catch (err) {
      console.error('Failed to fetch available models:', err);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchModes(), fetchAvailableModels()]);
      setLoading(false);
    };
    loadData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch app settings
  const fetchSettings = useCallback(async () => {
    setSettingsLoading(true);
    setSettingsError(null);
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/admin/settings', token);
      if (!response.ok) {
        throw new Error(`Failed to fetch settings: ${response.statusText}`);
      }
      const data = await response.json();
      const vertexSetting = data.settings?.use_vertex_ai;
      if (vertexSetting) {
        setUseVertexAi(vertexSetting.value === 'true');
      }
    } catch (err) {
      setSettingsError(err instanceof Error ? err.message : 'Failed to fetch settings');
    } finally {
      setSettingsLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load settings when app_settings tab is active
  useEffect(() => {
    if (activeTab === 'app_settings') {
      fetchSettings();
    }
  }, [activeTab, fetchSettings]);

  // Toggle use_vertex_ai
  const handleToggleVertexAi = async () => {
    setToggling(true);
    setSettingsError(null);
    setSettingsSuccess(null);
    try {
      const token = getAccessToken();
      const response = await authPut('/api/v1/admin/settings/use-vertex-ai', token, {
        value: !useVertexAi,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update setting');
      }
      const data = await response.json();
      setUseVertexAi(data.use_vertex_ai);
      setSettingsSuccess(data.message);
      setTimeout(() => setSettingsSuccess(null), 5000);
    } catch (err) {
      setSettingsError(err instanceof Error ? err.message : 'Failed to toggle setting');
    } finally {
      setToggling(false);
    }
  };

  // Open create modal
  const handleOpenCreate = () => {
    setEditingMode(null);
    setFormData(DEFAULT_FORM);
    setFormError(null);
    setShowModal(true);
  };

  // Open edit modal
  const handleOpenEdit = (mode: ProcessingMode) => {
    setEditingMode(mode);
    setFormData({
      mode_code: mode.mode_code,
      mode_name: mode.mode_name,
      description: mode.description || '',
      transcription_api: mode.transcription_api,
      transcription_model: mode.transcription_model,
      extraction_model: mode.extraction_model,
      triage_model: mode.triage_model || 'gemini-2.5-flash',
      merge_model: mode.merge_model || 'gemini-3.1-pro-preview',
      compare_model: mode.compare_model || 'gemini-2.5-flash',
      emotion_model: mode.emotion_model || 'gemini-2.5-flash',
      insights_model: mode.insights_model || 'gemini-2.5-flash',
      validator_model: mode.validator_model || 'gemini-2.5-flash',
      estimated_time_seconds: mode.estimated_time_seconds || 30,
      display_order: mode.display_order,
      is_active: mode.is_active,
    });
    setFormError(null);
    setShowModal(true);
  };

  // Handle transcription API change
  const handleTranscriptionApiChange = (api: 'gemini_batch' | 'gemini_live') => {
    const newModel = api === 'gemini_live'
      ? 'gemini-2.5-flash-native-audio-preview'
      : 'gemini-2.5-flash';

    setFormData({
      ...formData,
      transcription_api: api,
      transcription_model: newModel,
    });
  };

  // Save mode (create or update)
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Validation
    if (!formData.mode_code.trim()) {
      setFormError('Mode code is required');
      return;
    }
    if (!formData.mode_name.trim()) {
      setFormError('Mode name is required');
      return;
    }

    setIsSubmitting(true);

    try {
      const payload = {
        mode_code: formData.mode_code.trim(),
        mode_name: formData.mode_name.trim(),
        description: formData.description.trim() || null,
        transcription_api: formData.transcription_api,
        transcription_model: formData.transcription_model,
        extraction_model: formData.extraction_model,
        triage_model: formData.triage_model || null,
        merge_model: formData.merge_model || null,
        compare_model: formData.compare_model || null,
        emotion_model: formData.emotion_model || null,
        insights_model: formData.insights_model || null,
        validator_model: formData.validator_model || null,
        estimated_time_seconds: formData.estimated_time_seconds || null,
        display_order: formData.display_order,
        is_active: formData.is_active,
      };

      let response;
      if (editingMode) {
        response = await authPut(
          `/api/v1/admin/processing-modes/${editingMode.id}`,
          getAccessToken(),
          payload
        );
      } else {
        response = await authPost(
          '/api/v1/admin/processing-modes',
          getAccessToken(),
          payload
        );
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to ${editingMode ? 'update' : 'create'} mode`);
      }

      setShowModal(false);
      await fetchModes();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Operation failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Set as default
  const handleSetDefault = async (mode: ProcessingMode) => {
    if (mode.is_default) return;

    try {
      const response = await authPatch(
        `/api/v1/admin/processing-modes/${mode.id}/set-default`,
        getAccessToken(),
        {}
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to set default');
      }

      await fetchModes();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to set default');
    }
  };

  // Delete mode
  const handleDelete = async (mode: ProcessingMode) => {
    if (mode.is_default) {
      alert('Cannot delete the default mode. Set another mode as default first.');
      return;
    }

    if (!confirm(`Are you sure you want to deactivate "${mode.mode_name}"?`)) {
      return;
    }

    try {
      const response = await authDelete(
        `/api/v1/admin/processing-modes/${mode.id}`,
        getAccessToken()
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to delete mode');
      }

      await fetchModes();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete mode');
    }
  };

  // Get transcription models based on API, including current value if not in list
  const getTranscriptionModels = () => {
    const baseModels = formData.transcription_api === 'gemini_live'
      ? availableModels.live_models
      : availableModels.batch_models;

    const currentValue = formData.transcription_model;
    if (currentValue && !baseModels.find(m => m.value === currentValue)) {
      return [{ value: currentValue, label: `${currentValue} (custom)`, tier: 'custom' }, ...baseModels];
    }
    return baseModels;
  };

  // Get model options for a specific category, including current value if not in list
  const getModelOptions = (category: keyof AvailableModels, currentValue: string) => {
    const baseModels = availableModels[category] || [];
    if (currentValue && !baseModels.find(m => m.value === currentValue)) {
      return [{ value: currentValue, label: `${currentValue} (custom)`, tier: 'custom' }, ...baseModels];
    }
    return baseModels;
  };

  // Filter modes by search
  const filteredModes = modes.filter(mode =>
    mode.mode_code.toLowerCase().includes(searchTerm.toLowerCase()) ||
    mode.mode_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Format model name for display - show version and variant clearly
  const formatModelName = (model: string | undefined) => {
    if (!model) return '-';
    if (model.startsWith('gemini-')) {
      return model.replace('gemini-', '').replace('-preview', '');
    }
    if (model.startsWith('claude-')) {
      return model.replace('claude-', 'c-').replace(/-\d{8}$/, '');
    }
    if (model.startsWith('gpt-')) {
      return model.replace(/-\d{4}-\d{2}-\d{2}$/, '');
    }
    return model;
  };

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="flex border-b border-slate-700">
        <button
          onClick={() => setActiveTab('processing_modes')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors relative ${
            activeTab === 'processing_modes'
              ? 'text-blue-400'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Processing Modes
          {activeTab === 'processing_modes' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('app_settings')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors relative ${
            activeTab === 'app_settings'
              ? 'text-blue-400'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          App Settings
          {activeTab === 'app_settings' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400" />
          )}
        </button>
      </div>

      {/* App Settings Tab */}
      {activeTab === 'app_settings' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-xl font-bold text-white">App Settings</h2>
            <p className="text-slate-400 text-sm mt-1">
              Runtime settings that take effect without redeployment
            </p>
          </div>

          {settingsLoading ? (
            <div className="flex items-center justify-center h-32">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            </div>
          ) : (
            <div className="bg-slate-800/50 rounded-xl border border-slate-700 p-6">
              {settingsError && (
                <div className="mb-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                  <p className="text-red-400 text-sm">{settingsError}</p>
                </div>
              )}
              {settingsSuccess && (
                <div className="mb-4 p-3 bg-green-500/10 border border-green-500/50 rounded-lg">
                  <p className="text-green-400 text-sm">{settingsSuccess}</p>
                </div>
              )}

              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium text-white">Use Vertex AI</h3>
                  <p className="text-xs text-slate-400 mt-1">
                    When enabled, batch operations (transcription, extraction) use Vertex AI.
                    When disabled, Gemini API with API key is used.
                  </p>
                  <div className="mt-2">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      useVertexAi
                        ? 'bg-purple-500/20 text-purple-300'
                        : 'bg-blue-500/20 text-blue-300'
                    }`}>
                      Currently: {useVertexAi ? 'Vertex AI' : 'Gemini API'}
                    </span>
                  </div>
                </div>
                <button
                  onClick={handleToggleVertexAi}
                  disabled={toggling}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800 ${
                    toggling ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
                  } ${useVertexAi ? 'bg-purple-600' : 'bg-slate-600'}`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      useVertexAi ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Processing Modes Tab */}
      {activeTab === 'processing_modes' && (
        loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          </div>
        ) : (
          <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">Processing Modes</h2>
          <p className="text-slate-400 text-sm mt-1">
            Configure Gemini models for transcription, extraction, and analysis
          </p>
        </div>
        <button
          onClick={handleOpenCreate}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create Mode
        </button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search modes..."
            className="w-full px-4 py-2 pl-10 bg-slate-800/50 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <svg className="absolute left-3 top-2.5 w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/50 rounded-lg">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Modes Table */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-slate-800/80 border-b border-slate-700">
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Code</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Name</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Trans. API</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Trans. Model</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Extract Model</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Triage</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Merge</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Status</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {filteredModes.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-400">
                    {searchTerm ? 'No modes match your search.' : 'No processing modes found. Create one to get started.'}
                  </td>
                </tr>
              ) : (
                filteredModes.map((mode) => (
                  <tr
                    key={mode.id}
                    className="hover:bg-slate-800/30 transition-colors cursor-pointer"
                    onClick={() => handleOpenEdit(mode)}
                  >
                    <td className="px-4 py-3">
                      <code className="px-2 py-1 bg-slate-900 rounded text-xs text-slate-300">
                        {mode.mode_code}
                      </code>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-white">{mode.mode_name}</span>
                        {mode.is_default && (
                          <span className="px-1.5 py-0.5 bg-yellow-500/20 text-yellow-300 text-xs rounded">
                            Default
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        mode.transcription_api === 'gemini_live'
                          ? 'bg-purple-500/20 text-purple-300'
                          : 'bg-blue-500/20 text-blue-300'
                      }`}>
                        {mode.transcription_api === 'gemini_live' ? 'Live' : 'Batch'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-300" title={mode.transcription_model}>
                      {formatModelName(mode.transcription_model)}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-300" title={mode.extraction_model}>
                      {formatModelName(mode.extraction_model)}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-400" title={mode.triage_model}>
                      {formatModelName(mode.triage_model)}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-400" title={mode.merge_model}>
                      {formatModelName(mode.merge_model)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        mode.is_active
                          ? 'bg-green-500/20 text-green-300'
                          : 'bg-red-500/20 text-red-300'
                      }`}>
                        {mode.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-2">
                        {!mode.is_default && mode.is_active && (
                          <button
                            onClick={() => handleSetDefault(mode)}
                            className="p-1.5 text-slate-400 hover:text-yellow-400 hover:bg-yellow-500/10 rounded transition-colors"
                            title="Set as Default"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                            </svg>
                          </button>
                        )}
                        {!mode.is_default && (
                          <button
                            onClick={() => handleDelete(mode)}
                            className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                            title="Deactivate"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create/Edit Modal */}
      {showModal && activeTab === 'processing_modes' && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-white">
                  {editingMode ? 'Edit Processing Mode' : 'Create Processing Mode'}
                </h3>
                <button
                  onClick={() => setShowModal(false)}
                  className="p-1 text-slate-400 hover:text-white transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <form onSubmit={handleSave} className="space-y-6">
                {/* Basic Info Section */}
                <div className="space-y-4">
                  <h4 className="text-sm font-medium text-slate-300 border-b border-slate-700 pb-2">Basic Info</h4>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Mode Code *
                      </label>
                      <input
                        type="text"
                        value={formData.mode_code}
                        onChange={(e) => setFormData({ ...formData, mode_code: e.target.value })}
                        placeholder="e.g., fast"
                        disabled={!!editingMode}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Display Name *
                      </label>
                      <input
                        type="text"
                        value={formData.mode_name}
                        onChange={(e) => setFormData({ ...formData, mode_name: e.target.value })}
                        placeholder="e.g., Fast Mode"
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Description
                    </label>
                    <input
                      type="text"
                      value={formData.description}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      placeholder="Optional description"
                      className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>

                {/* Transcription Section */}
                <div className="space-y-4">
                  <h4 className="text-sm font-medium text-slate-300 border-b border-slate-700 pb-2">Transcription</h4>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Transcription API *
                      </label>
                      <select
                        value={formData.transcription_api}
                        onChange={(e) => handleTranscriptionApiChange(e.target.value as 'gemini_batch' | 'gemini_live')}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {TRANSCRIPTION_APIS.map((api) => (
                          <option key={api.value} value={api.value}>
                            {api.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Transcription Model *
                      </label>
                      <select
                        value={formData.transcription_model}
                        onChange={(e) => setFormData({ ...formData, transcription_model: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {getTranscriptionModels().map((model) => (
                          <option key={model.value} value={model.value}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                      {formData.transcription_api === 'gemini_live' && (
                        <p className="text-xs text-purple-400 mt-1">
                          Live API only supports native audio models
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Extraction & Analysis Section */}
                <div className="space-y-4">
                  <h4 className="text-sm font-medium text-slate-300 border-b border-slate-700 pb-2">Extraction & Analysis Models</h4>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Extraction Model *
                      </label>
                      <select
                        value={formData.extraction_model}
                        onChange={(e) => setFormData({ ...formData, extraction_model: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {getModelOptions('extraction_models', formData.extraction_model).map((model) => (
                          <option key={model.value} value={model.value}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Triage Model
                      </label>
                      <select
                        value={formData.triage_model}
                        onChange={(e) => setFormData({ ...formData, triage_model: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {getModelOptions('triage_models', formData.triage_model).map((model) => (
                          <option key={model.value} value={model.value}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Merge Model
                      </label>
                      <select
                        value={formData.merge_model}
                        onChange={(e) => setFormData({ ...formData, merge_model: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {getModelOptions('merge_models', formData.merge_model).map((model) => (
                          <option key={model.value} value={model.value}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Compare Model
                      </label>
                      <select
                        value={formData.compare_model}
                        onChange={(e) => setFormData({ ...formData, compare_model: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {getModelOptions('compare_models', formData.compare_model).map((model) => (
                          <option key={model.value} value={model.value}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Emotion Model
                      </label>
                      <select
                        value={formData.emotion_model}
                        onChange={(e) => setFormData({ ...formData, emotion_model: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {getModelOptions('emotion_models', formData.emotion_model).map((model) => (
                          <option key={model.value} value={model.value}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-slate-500 mt-1">
                        For text &amp; audio emotion analysis
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Insights Model
                      </label>
                      <select
                        value={formData.insights_model}
                        onChange={(e) => setFormData({ ...formData, insights_model: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {getModelOptions('insights_models', formData.insights_model).map((model) => (
                          <option key={model.value} value={model.value}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-slate-500 mt-1">
                        For consultation insights extraction
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Validator Model
                      </label>
                      <select
                        value={formData.validator_model}
                        onChange={(e) => setFormData({ ...formData, validator_model: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {getModelOptions('validator_models', formData.validator_model).map((model) => (
                          <option key={model.value} value={model.value}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-slate-500 mt-1">
                        For continuation merge validation
                      </p>
                    </div>
                  </div>
                </div>

                {/* Settings Section */}
                <div className="space-y-4">
                  <h4 className="text-sm font-medium text-slate-300 border-b border-slate-700 pb-2">Settings</h4>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Est. Time (seconds)
                      </label>
                      <input
                        type="number"
                        value={formData.estimated_time_seconds}
                        onChange={(e) => setFormData({ ...formData, estimated_time_seconds: parseInt(e.target.value) || 0 })}
                        min={0}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Display Order
                      </label>
                      <input
                        type="number"
                        value={formData.display_order}
                        onChange={(e) => setFormData({ ...formData, display_order: parseInt(e.target.value) || 0 })}
                        min={0}
                        className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="is_active"
                      checked={formData.is_active}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                      className="w-4 h-4 rounded border-slate-600 bg-slate-900/50 text-blue-500 focus:ring-blue-500"
                    />
                    <label htmlFor="is_active" className="text-sm text-slate-300">
                      Active (visible in mode selection)
                    </label>
                  </div>
                </div>

                {/* Error Message */}
                {formError && (
                  <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                    <p className="text-red-400 text-sm">{formError}</p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
                  <button
                    type="button"
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2 text-slate-300 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                  >
                    {isSubmitting ? 'Saving...' : (editingMode ? 'Save Changes' : 'Create Mode')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
          </>
        )
      )}
    </div>
  );
}

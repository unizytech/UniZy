'use client';

/**
 * Triage Layers Admin Screen
 *
 * Allows administrators to:
 * - View all triage layers configuration
 * - Enable/disable individual layers
 * - Adjust layer weights for conflict resolution
 * - View layer descriptions and status
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { authGet, authPut, authPost } from '@lib/apiClient';

interface TriageLayerConfig {
  id: string;
  layer_code: string;
  layer_name: string;
  description: string;
  is_enabled: boolean;
  weight: number;
  display_order: number;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export function TriageLayersAdminScreen() {
  const { getAccessToken } = useAuth();

  // State
  const [layers, setLayers] = useState<TriageLayerConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingLayers, setSavingLayers] = useState<Set<string>>(new Set());

  // Track unsaved changes
  const [pendingChanges, setPendingChanges] = useState<Map<string, Partial<TriageLayerConfig>>>(new Map());

  // Fetch layer configurations
  const fetchLayers = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/triage/layers/config', token);

      if (!response.ok) {
        throw new Error(`Failed to fetch triage layers: ${response.statusText}`);
      }

      const data = await response.json();
      setLayers(data.layers || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch triage layers');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchLayers();
      setLoading(false);
    };
    loadData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Toggle layer enabled state
  const handleToggleEnabled = async (layer: TriageLayerConfig) => {
    // Prevent disabling base_mvp
    if (layer.layer_code === 'base_mvp') {
      return;
    }

    const newEnabled = !layer.is_enabled;
    setSavingLayers(prev => new Set(prev).add(layer.layer_code));

    try {
      const token = getAccessToken();
      const response = await authPut(
        `/api/v1/triage/layers/config/${layer.layer_code}`,
        token,
        { is_enabled: newEnabled }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update layer');
      }

      // Update local state
      setLayers(prev => prev.map(l =>
        l.layer_code === layer.layer_code ? { ...l, is_enabled: newEnabled } : l
      ));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update layer');
    } finally {
      setSavingLayers(prev => {
        const newSet = new Set(prev);
        newSet.delete(layer.layer_code);
        return newSet;
      });
    }
  };

  // Update layer weight
  const handleWeightChange = (layerCode: string, weight: number) => {
    setPendingChanges(prev => {
      const newMap = new Map(prev);
      const existing = newMap.get(layerCode) || {};
      newMap.set(layerCode, { ...existing, weight });
      return newMap;
    });

    // Update local display
    setLayers(prev => prev.map(l =>
      l.layer_code === layerCode ? { ...l, weight } : l
    ));
  };

  // Save weight change
  const handleSaveWeight = async (layer: TriageLayerConfig) => {
    const changes = pendingChanges.get(layer.layer_code);
    if (!changes?.weight) return;

    setSavingLayers(prev => new Set(prev).add(layer.layer_code));

    try {
      const token = getAccessToken();
      const response = await authPut(
        `/api/v1/triage/layers/config/${layer.layer_code}`,
        token,
        { weight: changes.weight }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update weight');
      }

      // Clear pending change
      setPendingChanges(prev => {
        const newMap = new Map(prev);
        newMap.delete(layer.layer_code);
        return newMap;
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update weight');
    } finally {
      setSavingLayers(prev => {
        const newSet = new Set(prev);
        newSet.delete(layer.layer_code);
        return newSet;
      });
    }
  };

  // Enable all layers
  const handleEnableAll = async () => {
    const layersToEnable = layers.filter(l => !l.is_enabled && l.layer_code !== 'base_mvp');
    if (layersToEnable.length === 0) return;

    try {
      const token = getAccessToken();
      const updates = layersToEnable.map(l => ({
        layer_code: l.layer_code,
        is_enabled: true
      }));

      const response = await authPost('/api/v1/triage/layers/config/batch', token, { updates });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to enable layers');
      }

      await fetchLayers();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to enable layers');
    }
  };

  // Disable all layers (except base)
  const handleDisableAll = async () => {
    const layersToDisable = layers.filter(l => l.is_enabled && l.layer_code !== 'base_mvp');
    if (layersToDisable.length === 0) return;

    try {
      const token = getAccessToken();
      const updates = layersToDisable.map(l => ({
        layer_code: l.layer_code,
        is_enabled: false
      }));

      const response = await authPost('/api/v1/triage/layers/config/batch', token, { updates });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to disable layers');
      }

      await fetchLayers();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to disable layers');
    }
  };

  // Get layer icon based on code
  const getLayerIcon = (layerCode: string) => {
    switch (layerCode) {
      case 'base_mvp':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        );
      case 'doctor_practice':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        );
      case 'hospital_intelligence':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
          </svg>
        );
      case 'rag_guidelines':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        );
      default:
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        );
    }
  };

  // Get layer color based on code
  const getLayerColor = (layerCode: string, isEnabled: boolean) => {
    if (!isEnabled) return 'bg-slate-700 border-slate-600';

    switch (layerCode) {
      case 'base_mvp':
        return 'bg-emerald-900/30 border-emerald-500/50';
      case 'doctor_practice':
        return 'bg-blue-900/30 border-blue-500/50';
      case 'hospital_intelligence':
        return 'bg-purple-900/30 border-purple-500/50';
      case 'rag_guidelines':
        return 'bg-amber-900/30 border-amber-500/50';
      default:
        return 'bg-slate-700 border-slate-500';
    }
  };

  // Get badge color
  const getBadgeColor = (layerCode: string) => {
    switch (layerCode) {
      case 'base_mvp':
        return 'bg-emerald-500/20 text-emerald-300';
      case 'doctor_practice':
        return 'bg-blue-500/20 text-blue-300';
      case 'hospital_intelligence':
        return 'bg-purple-500/20 text-purple-300';
      case 'rag_guidelines':
        return 'bg-amber-500/20 text-amber-300';
      default:
        return 'bg-slate-500/20 text-slate-300';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const enabledCount = layers.filter(l => l.is_enabled).length;
  const totalCount = layers.length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">Triage Layer Configuration</h2>
          <p className="text-slate-400 text-sm mt-1">
            Configure multi-layer triage engine for enhanced suggestions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400">
            {enabledCount}/{totalCount} layers enabled
          </span>
          <button
            onClick={handleEnableAll}
            className="px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded-lg text-sm font-medium transition-colors"
          >
            Enable All
          </button>
          <button
            onClick={handleDisableAll}
            className="px-3 py-1.5 bg-slate-600/20 hover:bg-slate-600/30 text-slate-300 border border-slate-500/30 rounded-lg text-sm font-medium transition-colors"
          >
            Disable All
          </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/50 rounded-lg">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Info Banner */}
      <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-blue-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-blue-300 font-medium">Pipeline Architecture</p>
            <p className="text-slate-400 text-sm mt-1">
              <span className="text-emerald-400">Differential Trees</span> run first as a fast cache (~5ms).
              <span className="text-amber-400"> RAG Guidelines</span> then searches clinical evidence and can override tree suggestions when confident.
              <span className="text-cyan-400"> Gemini</span> receives RAG context to fill gaps not covered by guidelines.
              Finally, <span className="text-purple-400">Personalization layers</span> adjust based on doctor/hospital patterns.
            </p>
          </div>
        </div>
      </div>

      {/* Layers Grid */}
      <div className="grid gap-4">
        {layers.map((layer) => {
          const isSaving = savingLayers.has(layer.layer_code);
          const hasPendingWeight = pendingChanges.has(layer.layer_code);
          const isBaseMvp = layer.layer_code === 'base_mvp';

          return (
            <div
              key={layer.id}
              className={`p-5 rounded-xl border-2 transition-all duration-200 ${getLayerColor(layer.layer_code, layer.is_enabled)}`}
            >
              <div className="flex items-start justify-between gap-4">
                {/* Layer Info */}
                <div className="flex items-start gap-4 flex-1">
                  <div className={`p-3 rounded-lg ${layer.is_enabled ? getBadgeColor(layer.layer_code) : 'bg-slate-600/20 text-slate-400'}`}>
                    {getLayerIcon(layer.layer_code)}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="font-semibold text-white">{layer.layer_name}</h3>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${getBadgeColor(layer.layer_code)}`}>
                        {layer.layer_code}
                      </span>
                      {isBaseMvp && (
                        <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-300 rounded text-xs font-medium">
                          Always On
                        </span>
                      )}
                    </div>
                    <p className="text-slate-400 text-sm mt-1">{layer.description}</p>

                    {/* Layer Config Info */}
                    {layer.config && Object.keys(layer.config).length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {Object.entries(layer.config).map(([key, value]) => (
                          <span
                            key={key}
                            className="px-2 py-1 bg-slate-800/50 text-slate-400 rounded text-xs"
                          >
                            {key.replace(/_/g, ' ')}: {String(value)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Controls */}
                <div className="flex items-center gap-4">
                  {/* Weight Slider */}
                  <div className="w-48">
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs text-slate-400">Weight</label>
                      <span className="text-sm font-medium text-white">
                        {layer.weight.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={layer.weight}
                        onChange={(e) => handleWeightChange(layer.layer_code, parseFloat(e.target.value))}
                        disabled={!layer.is_enabled || isSaving}
                        className="flex-1 h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      {hasPendingWeight && (
                        <button
                          onClick={() => handleSaveWeight(layer)}
                          disabled={isSaving}
                          className="px-2 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded transition-colors disabled:opacity-50"
                        >
                          {isSaving ? '...' : 'Save'}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Toggle Switch */}
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => handleToggleEnabled(layer)}
                      disabled={isBaseMvp || isSaving}
                      className={`relative inline-flex h-7 w-14 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800 ${
                        layer.is_enabled
                          ? 'bg-emerald-600'
                          : 'bg-slate-600'
                      } ${isBaseMvp ? 'cursor-not-allowed opacity-75' : 'cursor-pointer'}`}
                      title={isBaseMvp ? 'Base layer cannot be disabled' : (layer.is_enabled ? 'Click to disable' : 'Click to enable')}
                    >
                      <span
                        className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                          layer.is_enabled ? 'translate-x-8' : 'translate-x-1'
                        }`}
                      />
                      {isSaving && (
                        <span className="absolute inset-0 flex items-center justify-center">
                          <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                        </span>
                      )}
                    </button>
                    <span className={`text-sm font-medium ${layer.is_enabled ? 'text-emerald-400' : 'text-slate-400'}`}>
                      {layer.is_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Pipeline Execution Flow */}
      <div className="p-6 bg-slate-800/50 rounded-xl border border-slate-700">
        <h3 className="text-lg font-semibold text-white mb-4">Pipeline Execution Flow</h3>
        <div className="flex flex-wrap items-center justify-center gap-3">
          {/* Step 1: Trees (Fast Cache) */}
          <div className="px-4 py-2 rounded-lg border bg-emerald-900/30 border-emerald-500/50">
            <div className="text-sm font-medium text-emerald-300">Differential Trees</div>
            <div className="text-xs text-emerald-400/70">~5ms - Fast Cache</div>
          </div>
          <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>

          {/* Step 2: RAG */}
          <div className={`px-4 py-2 rounded-lg border ${
            layers.find(l => l.layer_code === 'rag_guidelines')?.is_enabled
              ? 'bg-amber-900/30 border-amber-500/50'
              : 'bg-slate-700/50 border-slate-600'
          }`}>
            <div className={`text-sm font-medium ${
              layers.find(l => l.layer_code === 'rag_guidelines')?.is_enabled
                ? 'text-amber-300' : 'text-slate-500'
            }`}>RAG Guidelines</div>
            <div className={`text-xs ${
              layers.find(l => l.layer_code === 'rag_guidelines')?.is_enabled
                ? 'text-amber-400/70' : 'text-slate-500/70'
            }`}>~500ms - Primary Source</div>
          </div>
          <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>

          {/* Step 3: Gemini Gap Analysis */}
          <div className="px-4 py-2 rounded-lg border bg-cyan-900/30 border-cyan-500/50">
            <div className="text-sm font-medium text-cyan-300">Gemini Gap Analysis</div>
            <div className="text-xs text-cyan-400/70">2-15s - With RAG Context</div>
          </div>
          <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>

          {/* Step 4: Personalization */}
          <div className={`px-4 py-2 rounded-lg border ${
            layers.find(l => l.layer_code === 'doctor_practice')?.is_enabled ||
            layers.find(l => l.layer_code === 'hospital_intelligence')?.is_enabled
              ? 'bg-purple-900/30 border-purple-500/50'
              : 'bg-slate-700/50 border-slate-600'
          }`}>
            <div className={`text-sm font-medium ${
              layers.find(l => l.layer_code === 'doctor_practice')?.is_enabled ||
              layers.find(l => l.layer_code === 'hospital_intelligence')?.is_enabled
                ? 'text-purple-300' : 'text-slate-500'
            }`}>Personalization</div>
            <div className={`text-xs ${
              layers.find(l => l.layer_code === 'doctor_practice')?.is_enabled ||
              layers.find(l => l.layer_code === 'hospital_intelligence')?.is_enabled
                ? 'text-purple-400/70' : 'text-slate-500/70'
            }`}>Doctor + Hospital</div>
          </div>
          <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>

          {/* Step 5: Conflict Resolution */}
          <div className="px-4 py-2 rounded-lg border bg-rose-900/30 border-rose-500/50">
            <div className="text-sm font-medium text-rose-300">Conflict Resolution</div>
            <div className="text-xs text-rose-400/70">Deduplication + Merge</div>
          </div>
        </div>

        {/* Pipeline Notes */}
        <div className="mt-4 pt-4 border-t border-slate-700">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="flex items-start gap-2">
              <span className="w-2 h-2 mt-1 rounded-full bg-emerald-500 flex-shrink-0"></span>
              <span className="text-slate-400">
                <span className="text-slate-300">Trees</span> provide instant initial suggestions and red flag detection
              </span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-2 h-2 mt-1 rounded-full bg-amber-500 flex-shrink-0"></span>
              <span className="text-slate-400">
                <span className="text-slate-300">RAG</span> overrides trees when confidence &gt; 0.75 (evidence-based)
              </span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-2 h-2 mt-1 rounded-full bg-cyan-500 flex-shrink-0"></span>
              <span className="text-slate-400">
                <span className="text-slate-300">Gemini</span> fills gaps not covered by Trees or RAG
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Usage Notes */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 bg-slate-800/30 rounded-lg border border-slate-700">
          <h4 className="font-medium text-white mb-2 flex items-center gap-2">
            <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            Conflict Resolution Rules
          </h4>
          <ul className="text-sm text-slate-400 space-y-1.5">
            <li>1. Patient Safety First - allergies and contraindications always override</li>
            <li>2. Evidence Over Opinion - RAG guidelines take precedence</li>
            <li>3. Doctor Preference for Ties - when confidence is equal</li>
            <li>4. Layer weights used for scoring conflicts</li>
          </ul>
        </div>

        <div className="p-4 bg-slate-800/30 rounded-lg border border-slate-700">
          <h4 className="font-medium text-white mb-2 flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Getting Started
          </h4>
          <ul className="text-sm text-slate-400 space-y-1.5">
            <li>- Start with Base MVP only to establish baseline</li>
            <li>- Enable Doctor Practice after 10+ feedback entries</li>
            <li>- Enable Hospital Intelligence with 3+ doctors in specialty</li>
            <li>- Enable RAG Guidelines after ingesting clinical guidelines</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

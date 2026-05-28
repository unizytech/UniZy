'use client';

import React, { useState, useEffect } from 'react';
import { useAuth } from '@lib/auth';
import { authGet, authPut, authPost } from '@lib/apiClient';

interface ThinkingBudgets {
  extraction?: number;
  triage?: number;
  consultation_insights?: number;
  merge?: number;
  [key: string]: number | undefined;
}

interface ModelPricing {
  model_id: string;
  display_name: string;
  provider: string;
  input_price_per_million: number | null;
  output_price_per_million: number | null;
  cached_input_price_per_million: number | null;
  audio_price_per_minute: number | null;
  thinking_price_per_million: number | null;
  thinking_budgets: ThinkingBudgets | null;
  is_active: boolean;
  updated_at: string | null;
}

interface SuggestedPrice {
  model_id: string;
  display_name: string;
  current: Record<string, number | null> | null;
  suggested: Record<string, number | null> | null;
  source: string | null;
}

interface ModelPricingModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const CALL_TYPES = [
  { key: 'extraction', label: 'Extraction' },
  { key: 'triage', label: 'Triage' },
  { key: 'consultation_insights', label: 'Insights' },
  { key: 'merge', label: 'Merge' },
] as const;

export function ModelPricingModal({ isOpen, onClose }: ModelPricingModalProps) {
  const { getAccessToken } = useAuth();
  const [models, setModels] = useState<ModelPricing[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Track edited values: model_id -> field -> value
  const [edits, setEdits] = useState<Record<string, Record<string, number | null>>>({});

  // Track thinking budget edits separately: model_id -> ThinkingBudgets
  const [budgetEdits, setBudgetEdits] = useState<Record<string, ThinkingBudgets>>({});

  // Expanded row for thinking budget config
  const [expandedModel, setExpandedModel] = useState<string | null>(null);

  // Suggested prices from web refresh
  const [suggestions, setSuggestions] = useState<SuggestedPrice[]>([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (isOpen) {
      loadPricing();
      setEdits({});
      setBudgetEdits({});
      setExpandedModel(null);
      setSuggestions([]);
      setSelectedSuggestions(new Set());
      setError(null);
      setSuccessMsg(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const loadPricing = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authGet('/api/v1/models/pricing', getAccessToken());
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setModels(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pricing');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (modelId: string, field: string, value: string) => {
    const numValue = value === '' ? null : parseFloat(value);
    setEdits(prev => ({
      ...prev,
      [modelId]: { ...(prev[modelId] || {}), [field]: numValue },
    }));
  };

  const handleBudgetEdit = (modelId: string, callType: string, value: string) => {
    const numValue = value === '' ? undefined : parseInt(value, 10);
    setBudgetEdits(prev => ({
      ...prev,
      [modelId]: { ...(prev[modelId] || {}), [callType]: numValue },
    }));
  };

  const getEditedValue = (model: ModelPricing, field: keyof ModelPricing): string => {
    if (edits[model.model_id]?.[field] !== undefined) {
      const val = edits[model.model_id][field];
      return val === null ? '' : String(val);
    }
    const val = model[field];
    return val === null || val === undefined ? '' : String(val);
  };

  const getBudgetValue = (model: ModelPricing, callType: string): string => {
    if (budgetEdits[model.model_id]?.[callType] !== undefined) {
      const val = budgetEdits[model.model_id][callType];
      return val === undefined ? '' : String(val);
    }
    const val = model.thinking_budgets?.[callType];
    return val === undefined || val === null ? '' : String(val);
  };

  const hasEdits = Object.keys(edits).length > 0 || Object.keys(budgetEdits).length > 0;

  const handleSave = async () => {
    if (!hasEdits) return;

    setSaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      // Merge pricing edits and budget edits
      const allModelIds = new Set([...Object.keys(edits), ...Object.keys(budgetEdits)]);
      const updates = Array.from(allModelIds).map(model_id => {
        const pricingFields = edits[model_id] || {};
        const budgets = budgetEdits[model_id];

        const update: Record<string, unknown> = { model_id, ...pricingFields };

        if (budgets) {
          // Merge budget edits with existing budgets
          const model = models.find(m => m.model_id === model_id);
          const existingBudgets = model?.thinking_budgets || {};
          update.thinking_budgets = { ...existingBudgets, ...budgets };
        }

        return update;
      });

      const res = await authPut('/api/v1/models/pricing', getAccessToken(), { updates });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      setSuccessMsg(data.message);
      setEdits({});
      setBudgetEdits({});
      await loadPricing();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save pricing');
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshFromWeb = async () => {
    setRefreshing(true);
    setError(null);
    setSuggestions([]);
    setSelectedSuggestions(new Set());
    try {
      const res = await authPost('/api/v1/models/pricing/refresh', getAccessToken());
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: SuggestedPrice[] = await res.json();
      setSuggestions(data);

      const autoSelected = new Set<string>();
      for (const item of data) {
        if (item.suggested && item.current) {
          const fields = ['input_price_per_million', 'output_price_per_million', 'cached_input_price_per_million', 'audio_price_per_minute'] as const;
          for (const f of fields) {
            if (item.suggested[f] != null && item.current[f] != null && item.suggested[f] !== item.current[f]) {
              autoSelected.add(item.model_id);
              break;
            }
          }
        }
      }
      setSelectedSuggestions(autoSelected);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh pricing from web');
    } finally {
      setRefreshing(false);
    }
  };

  const handleApplySuggestions = () => {
    const newEdits: Record<string, Record<string, number | null>> = { ...edits };

    for (const item of suggestions) {
      if (selectedSuggestions.has(item.model_id) && item.suggested) {
        newEdits[item.model_id] = {};
        if (item.suggested.input_price_per_million != null) {
          newEdits[item.model_id].input_price_per_million = item.suggested.input_price_per_million;
        }
        if (item.suggested.output_price_per_million != null) {
          newEdits[item.model_id].output_price_per_million = item.suggested.output_price_per_million;
        }
        if (item.suggested.cached_input_price_per_million != null) {
          newEdits[item.model_id].cached_input_price_per_million = item.suggested.cached_input_price_per_million;
        }
        if (item.suggested.audio_price_per_minute != null) {
          newEdits[item.model_id].audio_price_per_minute = item.suggested.audio_price_per_minute;
        }
      }
    }

    setEdits(newEdits);
    setSuggestions([]);
    setSelectedSuggestions(new Set());
  };

  const toggleSuggestion = (modelId: string) => {
    setSelectedSuggestions(prev => {
      const next = new Set(prev);
      if (next.has(modelId)) next.delete(modelId);
      else next.add(modelId);
      return next;
    });
  };

  // Group models by provider
  const groupedModels: Record<string, ModelPricing[]> = {};
  for (const m of models) {
    if (!groupedModels[m.provider]) groupedModels[m.provider] = [];
    groupedModels[m.provider].push(m);
  }

  const providerLabels: Record<string, string> = {
    gemini: 'Google Gemini',
    anthropic: 'Anthropic Claude',
    openai: 'OpenAI',
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  const hasThinkingSupport = (model: ModelPricing) =>
    model.thinking_price_per_million != null || model.thinking_budgets != null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={onClose}
        />

        {/* Modal */}
        <div className="relative inline-block w-full max-w-6xl my-8 text-left align-middle bg-slate-800 rounded-2xl shadow-xl transform transition-all">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 rounded-t-2xl">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">Model Pricing & Thinking Budgets</h2>
                <p className="text-blue-200 text-sm">
                  Manage pricing and thinking token budgets per pipeline step
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRefreshFromWeb}
                  disabled={refreshing || loading}
                  className="px-3 py-1.5 bg-white/20 text-white text-sm rounded-lg hover:bg-white/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                >
                  {refreshing ? (
                    <>
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Searching...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Refresh from Web
                    </>
                  )}
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 text-white/80 hover:text-white hover:bg-white/20 rounded-lg"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          {/* Body */}
          <div className="px-6 py-4 max-h-[70vh] overflow-y-auto">
            {/* Messages */}
            {error && (
              <div className="mb-4 bg-red-900/50 border border-red-700 text-red-200 px-4 py-2 rounded-lg text-sm">
                {error}
              </div>
            )}
            {successMsg && (
              <div className="mb-4 bg-green-900/50 border border-green-700 text-green-200 px-4 py-2 rounded-lg text-sm">
                {successMsg}
              </div>
            )}

            {/* Suggestions panel */}
            {suggestions.length > 0 && (
              <div className="mb-4 bg-amber-900/30 border border-amber-700/50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-amber-200">
                    Suggested Price Updates ({suggestions.filter(s => s.suggested).length} found)
                  </h3>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setSuggestions([])}
                      className="px-2 py-1 text-xs bg-slate-600 text-slate-200 rounded hover:bg-slate-500"
                    >
                      Dismiss
                    </button>
                    <button
                      onClick={handleApplySuggestions}
                      disabled={selectedSuggestions.size === 0}
                      className="px-2 py-1 text-xs bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-50"
                    >
                      Apply Selected ({selectedSuggestions.size})
                    </button>
                  </div>
                </div>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {suggestions.filter(s => s.suggested).map(item => {
                    const changed = item.suggested && item.current;
                    const fields = ['input_price_per_million', 'output_price_per_million', 'cached_input_price_per_million'] as const;
                    const diffs = changed ? fields.filter(f =>
                      item.suggested![f] != null && item.current![f] != null && item.suggested![f] !== item.current![f]
                    ) : [];

                    if (diffs.length === 0) return null;

                    return (
                      <label key={item.model_id} className="flex items-center gap-2 text-sm text-slate-300 py-1 cursor-pointer hover:bg-slate-700/30 px-2 rounded">
                        <input
                          type="checkbox"
                          checked={selectedSuggestions.has(item.model_id)}
                          onChange={() => toggleSuggestion(item.model_id)}
                          className="rounded border-slate-500"
                        />
                        <span className="font-medium text-white">{item.display_name}</span>
                        <span className="text-slate-400">
                          {diffs.map(f => {
                            const label = f.replace('_per_million', '').replace('cached_input_price', 'cached');
                            return `${label}: $${item.current![f]} -> $${item.suggested![f]}`;
                          }).join(', ')}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            {loading ? (
              <div className="flex justify-center py-12">
                <svg className="animate-spin h-8 w-8 text-blue-500" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              </div>
            ) : (
              <div className="space-y-6">
                {Object.entries(groupedModels).map(([provider, providerModels]) => (
                  <div key={provider}>
                    <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-2">
                      {providerLabels[provider] || provider}
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-slate-600">
                        <thead className="bg-slate-700/50">
                          <tr>
                            <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">Model</th>
                            <th className="px-3 py-2 text-right text-xs font-medium text-slate-400 uppercase">Input $/M</th>
                            <th className="px-3 py-2 text-right text-xs font-medium text-slate-400 uppercase">Output $/M</th>
                            <th className="px-3 py-2 text-right text-xs font-medium text-slate-400 uppercase">Cached $/M</th>
                            <th className="px-3 py-2 text-right text-xs font-medium text-slate-400 uppercase">Audio $/min</th>
                            <th className="px-3 py-2 text-right text-xs font-medium text-purple-400 uppercase">Think $/M</th>
                            <th className="px-3 py-2 text-center text-xs font-medium text-purple-400 uppercase">Budgets</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">Updated</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-700">
                          {providerModels.map(model => {
                            const isEdited = !!edits[model.model_id] || !!budgetEdits[model.model_id];
                            const isExpanded = expandedModel === model.model_id;
                            const hasThinking = hasThinkingSupport(model);

                            return (
                              <React.Fragment key={model.model_id}>
                                <tr className={`${isEdited ? 'bg-blue-900/20' : ''} hover:bg-slate-700/30`}>
                                  <td className="px-3 py-2">
                                    <div className="text-sm font-medium text-white">{model.display_name}</div>
                                    <div className="text-xs text-slate-500">{model.model_id}</div>
                                  </td>
                                  <td className="px-3 py-2">
                                    <input
                                      type="number"
                                      step="0.001"
                                      value={getEditedValue(model, 'input_price_per_million')}
                                      onChange={e => handleEdit(model.model_id, 'input_price_per_million', e.target.value)}
                                      className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-right text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                                    />
                                  </td>
                                  <td className="px-3 py-2">
                                    <input
                                      type="number"
                                      step="0.001"
                                      value={getEditedValue(model, 'output_price_per_million')}
                                      onChange={e => handleEdit(model.model_id, 'output_price_per_million', e.target.value)}
                                      className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-right text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                                    />
                                  </td>
                                  <td className="px-3 py-2">
                                    <input
                                      type="number"
                                      step="0.0001"
                                      value={getEditedValue(model, 'cached_input_price_per_million')}
                                      onChange={e => handleEdit(model.model_id, 'cached_input_price_per_million', e.target.value)}
                                      className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-right text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                                    />
                                  </td>
                                  <td className="px-3 py-2">
                                    <input
                                      type="number"
                                      step="0.0001"
                                      value={getEditedValue(model, 'audio_price_per_minute')}
                                      onChange={e => handleEdit(model.model_id, 'audio_price_per_minute', e.target.value)}
                                      className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-right text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                                    />
                                  </td>
                                  <td className="px-3 py-2">
                                    <input
                                      type="number"
                                      step="0.01"
                                      value={getEditedValue(model, 'thinking_price_per_million')}
                                      onChange={e => handleEdit(model.model_id, 'thinking_price_per_million', e.target.value)}
                                      className="w-20 bg-slate-700 border border-purple-600/50 rounded px-2 py-1 text-sm text-right text-purple-300 focus:outline-none focus:ring-1 focus:ring-purple-500"
                                      placeholder="-"
                                    />
                                  </td>
                                  <td className="px-3 py-2 text-center">
                                    {hasThinking ? (
                                      <button
                                        onClick={() => setExpandedModel(isExpanded ? null : model.model_id)}
                                        className={`px-2 py-1 text-xs rounded transition-colors ${
                                          isExpanded
                                            ? 'bg-purple-600 text-white'
                                            : 'bg-purple-900/30 text-purple-300 hover:bg-purple-900/50'
                                        }`}
                                      >
                                        {isExpanded ? 'Hide' : 'Configure'}
                                      </button>
                                    ) : (
                                      <span className="text-xs text-slate-600">-</span>
                                    )}
                                  </td>
                                  <td className="px-3 py-2 text-xs text-slate-400">
                                    {formatDate(model.updated_at)}
                                  </td>
                                </tr>

                                {/* Expanded thinking budgets row */}
                                {isExpanded && (
                                  <tr className="bg-purple-900/10">
                                    <td colSpan={8} className="px-3 py-3">
                                      <div className="ml-4 border-l-2 border-purple-500/30 pl-4">
                                        <div className="flex items-center gap-2 mb-2">
                                          <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                                          </svg>
                                          <span className="text-sm font-medium text-purple-300">
                                            Thinking Budget per Step
                                          </span>
                                          <span className="text-xs text-slate-500">
                                            (0 = disabled, empty = model default)
                                          </span>
                                        </div>
                                        <div className="grid grid-cols-4 gap-3">
                                          {CALL_TYPES.map(ct => {
                                            const val = getBudgetValue(model, ct.key);
                                            const isZero = val === '0';
                                            const hasVal = val !== '';
                                            return (
                                              <div key={ct.key} className="flex flex-col gap-1">
                                                <label className="text-xs text-slate-400">{ct.label}</label>
                                                <div className="flex items-center gap-1">
                                                  <input
                                                    type="number"
                                                    step="256"
                                                    min="0"
                                                    value={val}
                                                    onChange={e => handleBudgetEdit(model.model_id, ct.key, e.target.value)}
                                                    placeholder="auto"
                                                    className={`w-full bg-slate-700 border rounded px-2 py-1 text-sm text-right focus:outline-none focus:ring-1 focus:ring-purple-500 ${
                                                      isZero
                                                        ? 'border-red-600/50 text-red-400'
                                                        : hasVal
                                                          ? 'border-purple-600/50 text-purple-300'
                                                          : 'border-slate-600 text-slate-400'
                                                    }`}
                                                  />
                                                </div>
                                                <span className={`text-[10px] ${isZero ? 'text-red-500' : hasVal ? 'text-purple-500' : 'text-slate-600'}`}>
                                                  {isZero ? 'disabled' : hasVal ? `${val} tok` : 'auto'}
                                                </span>
                                              </div>
                                            );
                                          })}
                                        </div>
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </React.Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-3 bg-slate-900/50 rounded-b-2xl flex justify-between items-center border-t border-slate-700">
            <p className="text-xs text-slate-500">
              Prices for cost calculations. Thinking budgets control reasoning token usage per step.
            </p>
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-slate-300 bg-slate-700 rounded-lg hover:bg-slate-600"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!hasEdits || saving}
                className="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                {saving ? (
                  <>
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Saving...
                  </>
                ) : (
                  'Save Changes'
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

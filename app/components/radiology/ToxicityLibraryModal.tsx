'use client';

/**
 * Toxicity Library Modal — per-template early/late toxicity items.
 *
 * Items rendered into the TOXICITY segment {{LIBRARY_TOXICITY}} placeholder
 * during template assembly. conditional_trigger flags items whose inclusion
 * depends on case context (e.g. brachytherapy planned, SCF irradiation,
 * left-heart). The id-prefix conventions GY_BR_*, BR_SCF_*, BR_LH_* embedded
 * in toxicity_code are what the prompt logic keys off.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@lib/auth';
import type { Template } from '@lib/types';
import {
  ToxicityItem,
  ToxicityItemPayload,
  createToxicityItem,
  deleteToxicityItem,
  listToxicityLibrary,
  updateToxicityItem,
} from '@/services/radiologyConfigApi';

interface Props {
  template: Template;
  onClose: () => void;
}

type Phase = 'early' | 'late';

const EMPTY_FORM = (phase: Phase): ToxicityItemPayload => ({
  toxicity_code: '',
  phase,
  text: '',
  conditional_trigger: '',
  display_order: 0,
});

export function ToxicityLibraryModal({ template, onClose }: Props) {
  const { getAccessToken } = useAuth();
  const [activePhase, setActivePhase] = useState<Phase>('early');
  const [items, setItems] = useState<ToxicityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | 'new' | null>(null);
  const [form, setForm] = useState<ToxicityItemPayload>(EMPTY_FORM('early'));

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listToxicityLibrary(template.id, getAccessToken());
      setItems(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [template.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    refresh();
  }, [refresh]);

  const startNew = () => {
    setForm(EMPTY_FORM(activePhase));
    setEditingId('new');
  };

  const startEdit = (item: ToxicityItem) => {
    setForm({
      toxicity_code: item.toxicity_code,
      phase: item.phase,
      text: item.text,
      conditional_trigger: item.conditional_trigger ?? '',
      display_order: item.display_order,
    });
    setEditingId(item.id);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(EMPTY_FORM(activePhase));
  };

  const save = async () => {
    if (!form.toxicity_code?.trim() || !form.text?.trim()) {
      alert('toxicity_code and text are required');
      return;
    }
    setSaving(true);
    try {
      const token = getAccessToken();
      if (editingId === 'new') {
        await createToxicityItem(template.id, token, form);
      } else if (editingId) {
        await updateToxicityItem(template.id, editingId, token, form);
      }
      cancelEdit();
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item: ToxicityItem) => {
    if (!confirm(`Remove toxicity "${item.toxicity_code}"?`)) return;
    setSaving(true);
    try {
      await deleteToxicityItem(template.id, item.id, getAccessToken());
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setSaving(false);
    }
  };

  const visible = items.filter((i) => i.phase === activePhase);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] overflow-y-auto">
        <div className="bg-purple-600 text-white p-6 rounded-t-lg sticky top-0 z-10">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">Toxicity Library</h2>
              <p className="text-purple-100 text-sm mt-1">
                {template.template_name} ({template.template_code})
              </p>
            </div>
            <button onClick={onClose} className="text-white hover:bg-purple-700 rounded-lg p-2 transition-colors" title="Close">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500" />
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">{error}</div>
          ) : (
            <>
              <div className="flex gap-2 mb-4">
                {(['early', 'late'] as Phase[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => {
                      setActivePhase(p);
                      cancelEdit();
                    }}
                    className={`px-4 py-2 rounded-lg text-sm font-medium border ${
                      activePhase === p
                        ? 'bg-purple-600 text-white border-purple-600'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    {p === 'early' ? 'Early toxicity' : 'Late toxicity'}
                    <span className="ml-2 text-xs opacity-75">
                      ({items.filter((i) => i.phase === p).length})
                    </span>
                  </button>
                ))}
              </div>

              {editingId === null && (
                <button
                  onClick={startNew}
                  className="mb-4 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  + Add {activePhase === 'early' ? 'Early' : 'Late'} Toxicity
                </button>
              )}

              {editingId !== null && (
                <ToxicityForm form={form} setForm={setForm} onCancel={cancelEdit} onSave={save} saving={saving} />
              )}

              <div className="divide-y divide-gray-200 border border-gray-200 rounded-lg">
                {visible.length === 0 && (
                  <div className="p-4 text-sm text-gray-500">No {activePhase} toxicity items yet.</div>
                )}
                {visible.map((it) => (
                  <div key={it.id} className="p-4 flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-gray-500">{it.toxicity_code}</span>
                        {it.conditional_trigger && (
                          <span className="px-2 py-0.5 text-xs rounded bg-amber-100 text-amber-800 border border-amber-200">
                            conditional · {it.conditional_trigger}
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-900 mt-1 whitespace-pre-wrap">{it.text}</div>
                    </div>
                    <div className="flex flex-col gap-2">
                      <button onClick={() => startEdit(it)} className="px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 text-gray-700">
                        Edit
                      </button>
                      <button onClick={() => remove(it)} className="px-3 py-1 text-xs border border-red-300 rounded hover:bg-red-50 text-red-700">
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ToxicityForm({
  form,
  setForm,
  onCancel,
  onSave,
  saving,
}: {
  form: ToxicityItemPayload;
  setForm: (f: ToxicityItemPayload) => void;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  const inputCls = 'w-full px-3 py-2 border border-gray-300 rounded text-sm text-gray-900 bg-white focus:ring-2 focus:ring-purple-500 focus:border-purple-500';
  const labelCls = 'block text-xs text-gray-600 mb-1';

  return (
    <div className="mb-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>toxicity_code *</label>
          <input
            className={inputCls}
            value={form.toxicity_code ?? ''}
            onChange={(e) => setForm({ ...form, toxicity_code: e.target.value })}
            placeholder="BR_E01 / GY_BR_L02 / BR_SCF_E03"
          />
        </div>
        <div>
          <label className={labelCls}>phase</label>
          <select
            className={inputCls}
            value={form.phase ?? 'early'}
            onChange={(e) => setForm({ ...form, phase: e.target.value as Phase })}
          >
            <option value="early">early</option>
            <option value="late">late</option>
          </select>
        </div>
        <div className="md:col-span-2">
          <label className={labelCls}>text * (verbatim consult-letter sentence)</label>
          <textarea
            className={inputCls}
            rows={3}
            value={form.text ?? ''}
            onChange={(e) => setForm({ ...form, text: e.target.value })}
          />
        </div>
        <div>
          <label className={labelCls}>conditional_trigger</label>
          <input
            className={inputCls}
            value={form.conditional_trigger ?? ''}
            onChange={(e) => setForm({ ...form, conditional_trigger: e.target.value })}
            placeholder="BRACHYTHERAPY / SCF / LEFT_HEART"
          />
        </div>
        <div>
          <label className={labelCls}>display_order</label>
          <input
            type="number"
            className={inputCls}
            value={form.display_order ?? 0}
            onChange={(e) => setForm({ ...form, display_order: Number(e.target.value) })}
          />
        </div>
      </div>
      <div className="mt-3 flex gap-2 justify-end">
        <button onClick={onCancel} disabled={saving} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
          Cancel
        </button>
        <button onClick={onSave} disabled={saving} className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}

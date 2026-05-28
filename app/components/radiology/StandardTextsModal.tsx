'use client';

/**
 * Standard Texts Modal — per-template named text blocks merged into the
 * extraction JSON before EHR dispatch.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@lib/auth';
import type { Template } from '@lib/types';
import {
  StandardTextItem,
  StandardTextPayload,
  createStandardText,
  deleteStandardText,
  listStandardTexts,
  updateStandardText,
} from '@/services/radiologyConfigApi';

interface Props {
  template: Template;
  onClose: () => void;
}

const EMPTY_FORM: StandardTextPayload = {
  key: '',
  label: '',
  text: '',
  display_order: 0,
};

export function StandardTextsModal({ template, onClose }: Props) {
  const { getAccessToken } = useAuth();
  const [items, setItems] = useState<StandardTextItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | 'new' | null>(null);
  const [form, setForm] = useState<StandardTextPayload>(EMPTY_FORM);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listStandardTexts(template.id, getAccessToken());
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
    setForm(EMPTY_FORM);
    setEditingId('new');
  };

  const startEdit = (item: StandardTextItem) => {
    setForm({
      key: item.key,
      label: item.label ?? '',
      text: item.text,
      display_order: item.display_order,
    });
    setEditingId(item.id);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const save = async () => {
    if (!form.key?.trim() || !form.text?.trim()) {
      alert('key and text are required');
      return;
    }
    setSaving(true);
    try {
      const token = getAccessToken();
      if (editingId === 'new') {
        await createStandardText(template.id, token, form);
      } else if (editingId) {
        await updateStandardText(template.id, editingId, token, form);
      }
      cancelEdit();
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item: StandardTextItem) => {
    if (!confirm(`Remove standard text "${item.key}"?`)) return;
    setSaving(true);
    try {
      await deleteStandardText(template.id, item.id, getAccessToken());
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setSaving(false);
    }
  };

  const inputCls = 'w-full px-3 py-2 border border-gray-300 rounded text-sm text-gray-900 bg-white focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500';
  const labelCls = 'block text-xs text-gray-600 mb-1';

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="bg-emerald-600 text-white p-6 rounded-t-lg sticky top-0 z-10">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">Standard Texts</h2>
              <p className="text-emerald-100 text-sm mt-1">
                {template.template_name} ({template.template_code})
              </p>
            </div>
            <button onClick={onClose} className="text-white hover:bg-emerald-700 rounded-lg p-2 transition-colors" title="Close">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500" />
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">{error}</div>
          ) : (
            <>
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 mb-4 text-sm text-emerald-900">
                Named text blocks merged into the extraction JSON keyed by <code className="font-mono">key</code>{' '}
                before the payload is sent to the EHR API. Use lowercase snake_case keys
                (e.g. <code className="font-mono">consent_block</code>, <code className="font-mono">footer_disclaimer</code>).
              </div>

              {editingId === null && (
                <button
                  onClick={startNew}
                  className="mb-4 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  + Add Standard Text
                </button>
              )}

              {editingId !== null && (
                <div className="mb-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className={labelCls}>key *</label>
                      <input
                        className={inputCls}
                        value={form.key ?? ''}
                        onChange={(e) => setForm({ ...form, key: e.target.value })}
                        placeholder="consent_block"
                      />
                    </div>
                    <div>
                      <label className={labelCls}>label</label>
                      <input
                        className={inputCls}
                        value={form.label ?? ''}
                        onChange={(e) => setForm({ ...form, label: e.target.value })}
                        placeholder="Consent block (UI label)"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label className={labelCls}>text *</label>
                      <textarea
                        className={inputCls}
                        rows={6}
                        value={form.text ?? ''}
                        onChange={(e) => setForm({ ...form, text: e.target.value })}
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
                    <button onClick={cancelEdit} disabled={saving} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                      Cancel
                    </button>
                    <button onClick={save} disabled={saving} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                  </div>
                </div>
              )}

              <div className="divide-y divide-gray-200 border border-gray-200 rounded-lg">
                {items.length === 0 && (
                  <div className="p-4 text-sm text-gray-500">No standard texts yet.</div>
                )}
                {items.map((it) => (
                  <div key={it.id} className="p-4 flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-gray-500">{it.key}</span>
                        {it.label && <span className="text-xs text-gray-700">— {it.label}</span>}
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

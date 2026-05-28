'use client';

/**
 * Plan Library Modal — per-template radiology plan templates.
 *
 * Items rendered into the PLAN segment {{LIBRARY_PLAN}} placeholder during
 * template assembly.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@lib/auth';
import type { Template } from '@lib/types';
import {
  PlanItem,
  PlanItemPayload,
  createPlanItem,
  deletePlanItem,
  listPlanLibrary,
  updatePlanItem,
} from '@/services/radiologyConfigApi';

interface Props {
  template: Template;
  onClose: () => void;
}

const EMPTY_FORM: PlanItemPayload = {
  plan_code: '',
  plan_name: '',
  rt_intent: '',
  rt_indication: '',
  rt_dose_gy: '',
  rt_fractions: '',
  rt_dose_per_fraction_gy: '',
  rt_weeks: '',
  rt_technique: '',
  concurrent_systemic_therapy: '',
  display_order: 0,
};

export function PlanLibraryModal({ template, onClose }: Props) {
  const { getAccessToken } = useAuth();
  const [items, setItems] = useState<PlanItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | 'new' | null>(null);
  const [form, setForm] = useState<PlanItemPayload>(EMPTY_FORM);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPlanLibrary(template.id, getAccessToken());
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

  const startEdit = (item: PlanItem) => {
    setForm({
      plan_code: item.plan_code,
      plan_name: item.plan_name,
      rt_intent: item.rt_intent ?? '',
      rt_indication: item.rt_indication ?? '',
      rt_dose_gy: item.rt_dose_gy ?? '',
      rt_fractions: item.rt_fractions ?? '',
      rt_dose_per_fraction_gy: item.rt_dose_per_fraction_gy ?? '',
      rt_weeks: item.rt_weeks ?? '',
      rt_technique: item.rt_technique ?? '',
      concurrent_systemic_therapy: item.concurrent_systemic_therapy ?? '',
      display_order: item.display_order,
    });
    setEditingId(item.id);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const save = async () => {
    if (!form.plan_code?.trim() || !form.plan_name?.trim()) {
      alert('plan_code and plan_name are required');
      return;
    }
    setSaving(true);
    try {
      const token = getAccessToken();
      if (editingId === 'new') {
        await createPlanItem(template.id, token, form);
      } else if (editingId) {
        await updatePlanItem(template.id, editingId, token, form);
      }
      cancelEdit();
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item: PlanItem) => {
    if (!confirm(`Remove plan "${item.plan_code}"?`)) return;
    setSaving(true);
    try {
      await deletePlanItem(template.id, item.id, getAccessToken());
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] overflow-y-auto">
        <div className="bg-blue-600 text-white p-6 rounded-t-lg sticky top-0 z-10">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">Plan Library</h2>
              <p className="text-blue-100 text-sm mt-1">
                {template.template_name} ({template.template_code})
              </p>
            </div>
            <button onClick={onClose} className="text-white hover:bg-blue-700 rounded-lg p-2 transition-colors" title="Close">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">{error}</div>
          ) : (
            <>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 text-sm text-blue-800">
                Plan templates listed here are injected into the PLAN segment prompt during template
                assembly. Doctor speech is matched against these to identify the regimen at extraction time.
              </div>

              {editingId === null && (
                <button
                  onClick={startNew}
                  className="mb-4 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  + Add Plan
                </button>
              )}

              {editingId !== null && (
                <PlanForm form={form} setForm={setForm} onCancel={cancelEdit} onSave={save} saving={saving} />
              )}

              <div className="divide-y divide-gray-200 border border-gray-200 rounded-lg">
                {items.length === 0 && (
                  <div className="p-4 text-sm text-gray-500">No plan templates yet.</div>
                )}
                {items.map((it) => (
                  <div key={it.id} className="p-4 flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="font-mono text-xs text-gray-500">{it.plan_code}</div>
                      <div className="font-semibold text-gray-900">{it.plan_name}</div>
                      <div className="text-sm text-gray-700 mt-1">
                        {[it.rt_intent, it.rt_dose_gy && `${it.rt_dose_gy} Gy`, it.rt_fractions && `${it.rt_fractions} fx`, it.rt_technique]
                          .filter(Boolean)
                          .join(' · ')}
                      </div>
                      {it.rt_indication && (
                        <div className="text-xs text-gray-600 mt-1">Indication: {it.rt_indication}</div>
                      )}
                      {it.concurrent_systemic_therapy && (
                        <div className="text-xs text-gray-600 mt-1">Concurrent: {it.concurrent_systemic_therapy}</div>
                      )}
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

function PlanForm({
  form,
  setForm,
  onCancel,
  onSave,
  saving,
}: {
  form: PlanItemPayload;
  setForm: (f: PlanItemPayload) => void;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  const set = (k: keyof PlanItemPayload) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  const inputCls = 'w-full px-3 py-2 border border-gray-300 rounded text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
  const labelCls = 'block text-xs text-gray-600 mb-1';

  return (
    <div className="mb-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>plan_code *</label>
          <input className={inputCls} value={form.plan_code ?? ''} onChange={set('plan_code')} placeholder="BR_PLAN_WB_HYPO_40_15" />
        </div>
        <div>
          <label className={labelCls}>plan_name *</label>
          <input className={inputCls} value={form.plan_name ?? ''} onChange={set('plan_name')} placeholder="Whole-breast hypofractionated" />
        </div>
        <div>
          <label className={labelCls}>rt_intent</label>
          <input className={inputCls} value={form.rt_intent ?? ''} onChange={set('rt_intent')} placeholder="Adjuvant / Definitive / Palliative" />
        </div>
        <div className="md:col-span-2">
          <label className={labelCls}>rt_indication</label>
          <textarea className={inputCls} rows={2} value={form.rt_indication ?? ''} onChange={set('rt_indication')} />
        </div>
        <div>
          <label className={labelCls}>rt_dose_gy</label>
          <input className={inputCls} value={form.rt_dose_gy ?? ''} onChange={set('rt_dose_gy')} placeholder="40" />
        </div>
        <div>
          <label className={labelCls}>rt_fractions</label>
          <input className={inputCls} value={form.rt_fractions ?? ''} onChange={set('rt_fractions')} placeholder="15" />
        </div>
        <div>
          <label className={labelCls}>rt_dose_per_fraction_gy</label>
          <input className={inputCls} value={form.rt_dose_per_fraction_gy ?? ''} onChange={set('rt_dose_per_fraction_gy')} placeholder="2.67" />
        </div>
        <div>
          <label className={labelCls}>rt_weeks</label>
          <input className={inputCls} value={form.rt_weeks ?? ''} onChange={set('rt_weeks')} placeholder="3" />
        </div>
        <div className="md:col-span-2">
          <label className={labelCls}>rt_technique</label>
          <input className={inputCls} value={form.rt_technique ?? ''} onChange={set('rt_technique')} placeholder="VMAT, IMRT, 3DCRT, DIBH..." />
        </div>
        <div className="md:col-span-2">
          <label className={labelCls}>concurrent_systemic_therapy</label>
          <textarea className={inputCls} rows={2} value={form.concurrent_systemic_therapy ?? ''} onChange={set('concurrent_systemic_therapy')} />
        </div>
      </div>
      <div className="mt-3 flex gap-2 justify-end">
        <button onClick={onCancel} disabled={saving} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
          Cancel
        </button>
        <button onClick={onSave} disabled={saving} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}

'use client';

/**
 * Template Field Config (Admin)
 *
 * Controls which segments/fields of each template are:
 *   - tracked by the public extraction-gaps API (per-leaf checkboxes)
 *   - included in the public template-schema empty-payload (segment-level)
 *
 * Storage: template_segments.gap_analysis_fields_json (jsonb) and
 *          template_segments.include_in_empty_payload (bool).
 * NULL values mean "legacy default" — external API consumers see unchanged
 * behavior until an admin flips a flag.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@lib/auth';
import {
  getAllTemplates,
  getTemplateFieldConfig,
  bulkUpdateTemplateFieldConfig,
  handleApiError,
  type TemplateFieldConfigSegment,
} from '@lib/summaryApi';
import type { Template } from '@lib/types';
import { SegmentFieldConfigRow } from './SegmentFieldConfigRow';

type SegmentDraft = {
  segment_code: string;
  segment_name: string;
  category: string;
  shape: TemplateFieldConfigSegment['shape'];
  schema_leaves: string[];
  default_leaves: string[];
  // Draft values (what the user has edited in-memory):
  gap_enabled: boolean;                // false => excluded ([])
  gap_included_leaves: string[];       // only meaningful when gap_enabled
  gap_is_default: boolean;             // true => send `null` to reset
  empty_payload_enabled: boolean;      // true => include; false => trim
  empty_is_default: boolean;           // true => send `null` to reset
  // Baseline (for dirty-tracking):
  baseline_gap: string[] | null;
  baseline_empty: boolean | null;
};

function toDraft(seg: TemplateFieldConfigSegment): SegmentDraft {
  const configuredGap = seg.gap_analysis_fields_json;
  const gap_is_default = configuredGap === null;
  const gap_included_leaves = gap_is_default
    ? [...seg.default_leaves]
    : [...(configuredGap || [])];
  const gap_enabled = gap_is_default ? seg.default_leaves.length > 0 : gap_included_leaves.length > 0;

  const configuredEmpty = seg.include_in_empty_payload;
  const empty_is_default = configuredEmpty === null;
  const empty_payload_enabled = empty_is_default ? true : !!configuredEmpty;

  return {
    segment_code: seg.segment_code,
    segment_name: seg.segment_name,
    category: seg.category,
    shape: seg.shape,
    schema_leaves: seg.schema_leaves,
    default_leaves: seg.default_leaves,
    gap_enabled,
    gap_included_leaves,
    gap_is_default,
    empty_payload_enabled,
    empty_is_default,
    baseline_gap: configuredGap,
    baseline_empty: configuredEmpty,
  };
}

function isDirty(d: SegmentDraft): boolean {
  // Effective gap value the user wants to persist
  const effectiveGap = d.gap_is_default
    ? null
    : (d.gap_enabled ? d.gap_included_leaves : []);
  const baselineGap = d.baseline_gap;
  const gapChanged = effectiveGap === null
    ? baselineGap !== null
    : baselineGap === null
      ? true
      : JSON.stringify([...effectiveGap].sort()) !== JSON.stringify([...baselineGap].sort());

  const effectiveEmpty = d.empty_is_default ? null : d.empty_payload_enabled;
  const emptyChanged = effectiveEmpty !== d.baseline_empty;

  return gapChanged || emptyChanged;
}

export function TemplateFieldConfigScreen() {
  const { getAccessToken } = useAuth();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [loadingConfig, setLoadingConfig] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<SegmentDraft[]>([]);

  useEffect(() => {
    const run = async () => {
      try {
        setLoadingTemplates(true);
        const token = getAccessToken();
        if (!token) return;
        const resp = await getAllTemplates('all', undefined, token);
        if (resp.success) {
          const list = [...resp.templates].sort((a, b) =>
            (a.template_code || '').localeCompare(b.template_code || '')
          );
          setTemplates(list);
        }
      } catch (e) {
        setError(handleApiError(e));
      } finally {
        setLoadingTemplates(false);
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedTemplate) {
      setDrafts([]);
      return;
    }
    const run = async () => {
      try {
        setLoadingConfig(true);
        setError(null);
        setNotice(null);
        const token = getAccessToken();
        if (!token) return;
        const resp = await getTemplateFieldConfig(selectedTemplate, token);
        setDrafts(resp.segments.map(toDraft));
      } catch (e) {
        setError(handleApiError(e));
      } finally {
        setLoadingConfig(false);
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTemplate]);

  const dirtyCount = useMemo(() => drafts.filter(isDirty).length, [drafts]);

  const updateDraft = (segmentCode: string, patch: Partial<SegmentDraft>) => {
    setDrafts(prev => prev.map(d => (d.segment_code === segmentCode ? { ...d, ...patch } : d)));
  };

  const handleSave = async () => {
    if (dirtyCount === 0) return;
    try {
      setSaving(true);
      setError(null);
      setNotice(null);
      const payload = drafts.filter(isDirty).map(d => {
        const gap = d.gap_is_default
          ? null
          : (d.gap_enabled ? d.gap_included_leaves : []);
        const empty = d.empty_is_default ? null : d.empty_payload_enabled;
        return {
          segment_code: d.segment_code,
          gap_analysis_fields_json: gap,
          include_in_empty_payload: empty,
        };
      });
      const token = getAccessToken();
      if (!token) return;
      const resp = await bulkUpdateTemplateFieldConfig(selectedTemplate, payload, token);
      setNotice(`Saved ${resp.update_count} segment${resp.update_count === 1 ? '' : 's'}.`);
      // Re-fetch to refresh baselines
      const fresh = await getTemplateFieldConfig(selectedTemplate, token);
      setDrafts(fresh.segments.map(toDraft));
    } catch (e) {
      setError(handleApiError(e));
    } finally {
      setSaving(false);
    }
  };

  const handleRevert = () => {
    setDrafts(prev => prev.map(d => ({
      ...d,
      gap_enabled: d.baseline_gap === null
        ? d.default_leaves.length > 0
        : (d.baseline_gap.length > 0),
      gap_included_leaves: d.baseline_gap === null ? [...d.default_leaves] : [...d.baseline_gap],
      gap_is_default: d.baseline_gap === null,
      empty_payload_enabled: d.baseline_empty === null ? true : d.baseline_empty,
      empty_is_default: d.baseline_empty === null,
    })));
  };

  return (
    <div className="p-6 max-w-5xl mx-auto text-slate-100">
      <h2 className="text-2xl font-semibold mb-2">Template Field Config</h2>
      <p className="text-sm text-slate-400 mb-6">
        Controls which fields the <code>extraction-gaps</code> API tracks and which segments are
        included in the <code>template-schema</code> empty payload. Defaults keep the public API
        backward-compatible until you explicitly change a flag.
      </p>

      <div className="mb-4">
        <label className="block text-sm font-medium mb-1">Template</label>
        <select
          className="bg-slate-800 border border-slate-700 rounded px-3 py-2 w-full"
          value={selectedTemplate}
          onChange={e => setSelectedTemplate(e.target.value)}
          disabled={loadingTemplates}
        >
          <option value="">{loadingTemplates ? 'Loading…' : 'Select a template'}</option>
          {templates.map(t => (
            <option key={t.template_code} value={t.template_code}>
              {t.template_code} — {t.template_name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/40 border border-red-700 rounded text-sm">
          {error}
        </div>
      )}
      {notice && (
        <div className="mb-4 p-3 bg-emerald-900/40 border border-emerald-700 rounded text-sm">
          {notice}
        </div>
      )}

      {loadingConfig && (
        <div className="text-slate-400">Loading segments…</div>
      )}

      {!loadingConfig && drafts.length > 0 && (
        <>
          <div className="sticky top-0 z-10 bg-slate-900/80 backdrop-blur py-3 flex items-center gap-3 border-b border-slate-800 mb-4">
            <button
              onClick={handleSave}
              disabled={dirtyCount === 0 || saving}
              className="px-4 py-2 rounded bg-emerald-700 hover:bg-emerald-600 disabled:bg-slate-700 disabled:text-slate-500 text-sm font-medium"
            >
              {saving ? 'Saving…' : `Save ${dirtyCount} change${dirtyCount === 1 ? '' : 's'}`}
            </button>
            <button
              onClick={handleRevert}
              disabled={dirtyCount === 0 || saving}
              className="px-3 py-2 rounded bg-slate-800 hover:bg-slate-700 disabled:text-slate-500 text-sm"
            >
              Revert
            </button>
            <span className="text-xs text-slate-500">
              NULL = legacy default. Untick a segment's "Gap analysis" to exclude it from gap reporting.
            </span>
          </div>

          <div className="space-y-3">
            {drafts.map(d => (
              <SegmentFieldConfigRow
                key={d.segment_code}
                draft={d}
                onChange={(patch) => updateDraft(d.segment_code, patch)}
              />
            ))}
          </div>
        </>
      )}

      {!loadingConfig && selectedTemplate && drafts.length === 0 && (
        <div className="text-slate-400">No active segments found for this template.</div>
      )}
    </div>
  );
}

export type { SegmentDraft };

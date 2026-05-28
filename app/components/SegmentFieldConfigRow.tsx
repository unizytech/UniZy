'use client';

/**
 * Per-segment row for TemplateFieldConfigScreen.
 *
 * Three controls per segment:
 *   1. "Empty payload" toggle -> include_in_empty_payload
 *   2. "Gap analysis" master toggle -> if off, gap_analysis_fields_json = []
 *   3. Expandable leaf checkboxes (shape-aware) -> gap_analysis_fields_json list
 *
 * "Reset to default" reverts to NULL, so the DB stays on legacy semantics.
 */

import React, { useMemo, useState } from 'react';
import type { SegmentDraft } from './TemplateFieldConfigScreen';

interface Props {
  draft: SegmentDraft;
  onChange: (patch: Partial<SegmentDraft>) => void;
}

function groupLeavesByParent(leaves: string[]): Array<{ parent: string; children: string[] }> {
  const groups: Record<string, string[]> = {};
  const order: string[] = [];
  for (const path of leaves) {
    const dot = path.indexOf('.');
    const parent = dot === -1 ? path : path.slice(0, dot);
    if (!(parent in groups)) {
      groups[parent] = [];
      order.push(parent);
    }
    if (dot !== -1) groups[parent].push(path.slice(dot + 1));
  }
  return order.map(parent => ({ parent, children: groups[parent] }));
}

export function SegmentFieldConfigRow({ draft, onChange }: Props) {
  const [expanded, setExpanded] = useState(false);

  const included = useMemo(() => new Set(draft.gap_included_leaves), [draft.gap_included_leaves]);

  // What leaves are selectable in the UI depends on shape:
  //   flat: the flat properties themselves
  //   nested_presence / comorbidity: show parent with optional sub-checkboxes
  //   array / unknown: single root toggle (handled by shape==='array' branch)
  const groups = useMemo(() => groupLeavesByParent(draft.schema_leaves), [draft.schema_leaves]);

  const toggleLeaf = (leaf: string) => {
    const next = new Set(included);
    if (next.has(leaf)) next.delete(leaf);
    else next.add(leaf);
    onChange({
      gap_included_leaves: Array.from(next),
      gap_is_default: false,
    });
  };

  const toggleGapEnabled = () => {
    const next = !draft.gap_enabled;
    onChange({
      gap_enabled: next,
      gap_is_default: false,
      // When enabling from off, re-seed with default leaves for discoverability
      gap_included_leaves: next && draft.gap_included_leaves.length === 0
        ? [...draft.default_leaves]
        : draft.gap_included_leaves,
    });
  };

  const resetToDefaults = () => {
    onChange({
      gap_is_default: true,
      gap_enabled: draft.default_leaves.length > 0,
      gap_included_leaves: [...draft.default_leaves],
      empty_is_default: true,
      empty_payload_enabled: true,
    });
  };

  const selectAll = () => {
    onChange({
      gap_included_leaves: [...draft.schema_leaves],
      gap_is_default: false,
      gap_enabled: draft.schema_leaves.length > 0,
    });
  };

  const clearAll = () => {
    onChange({
      gap_included_leaves: [],
      gap_is_default: false,
    });
  };

  const shapeLabel = draft.shape === 'unknown' ? 'flat' : draft.shape;

  return (
    <div className="border border-slate-800 rounded-lg bg-slate-900/60">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => setExpanded(x => !x)}
            className="text-slate-400 hover:text-slate-200 text-sm w-5"
            aria-label={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? '▾' : '▸'}
          </button>
          <div className="min-w-0">
            <div className="font-medium truncate">
              {draft.segment_name || draft.segment_code}
              <span className="ml-2 text-xs text-slate-500">({draft.segment_code})</span>
            </div>
            <div className="text-xs text-slate-500">
              {draft.category} · shape: {shapeLabel}
              {draft.gap_is_default && ' · gap: default'}
              {draft.empty_is_default && ' · payload: default'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 shrink-0">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.empty_payload_enabled}
              onChange={() => onChange({
                empty_payload_enabled: !draft.empty_payload_enabled,
                empty_is_default: false,
              })}
            />
            <span>Empty payload</span>
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.gap_enabled}
              onChange={toggleGapEnabled}
            />
            <span>Gap analysis</span>
          </label>

          <button
            onClick={resetToDefaults}
            className="text-xs text-slate-400 hover:text-slate-200 underline"
          >
            Reset defaults
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-slate-800 px-4 py-3">
          {draft.shape === 'array' ? (
            <div className="text-sm text-slate-400">
              Arrays are not gap-tracked by default. Tick to flag empty arrays as missing:
              <label className="ml-3 inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  disabled={!draft.gap_enabled}
                  checked={draft.gap_included_leaves.length > 0}
                  onChange={(e) => onChange({
                    gap_included_leaves: e.target.checked ? [draft.segment_code.toLowerCase()] : [],
                    gap_is_default: false,
                  })}
                />
                <span>Flag empty array as gap</span>
              </label>
            </div>
          ) : draft.schema_leaves.length === 0 ? (
            <div className="text-sm text-slate-500">Segment has no inspectable leaves.</div>
          ) : (
            <>
              <div className="flex items-center gap-3 mb-3">
                <button
                  onClick={selectAll}
                  disabled={!draft.gap_enabled}
                  className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:text-slate-600"
                >
                  Select all
                </button>
                <button
                  onClick={clearAll}
                  disabled={!draft.gap_enabled}
                  className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:text-slate-600"
                >
                  Clear all
                </button>
                <span className="text-xs text-slate-500">
                  {included.size} of {draft.schema_leaves.length} leaves selected
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {groups.map(({ parent, children }) => {
                  if (children.length === 0) {
                    // Flat leaf (vitals, nutritional, allergy)
                    return (
                      <label key={parent} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          disabled={!draft.gap_enabled}
                          checked={included.has(parent)}
                          onChange={() => toggleLeaf(parent)}
                        />
                        <span>{parent}</span>
                      </label>
                    );
                  }
                  // Nested group: show each leaf as `parent.child`
                  return (
                    <div key={parent} className="border border-slate-800 rounded p-2">
                      <div className="text-sm font-medium text-slate-300 mb-1">{parent}</div>
                      <div className="flex flex-col gap-1 ml-2">
                        {children.map(child => {
                          const leafPath = `${parent}.${child}`;
                          return (
                            <label key={leafPath} className="flex items-center gap-2 text-xs">
                              <input
                                type="checkbox"
                                disabled={!draft.gap_enabled}
                                checked={included.has(leafPath)}
                                onChange={() => toggleLeaf(leafPath)}
                              />
                              <span className="text-slate-400">.{child}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

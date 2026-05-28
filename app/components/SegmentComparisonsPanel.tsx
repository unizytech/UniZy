'use client';

import React, { useState, useEffect } from 'react';
import type { ConsultationTypeCode } from '@lib/types';
import {
  getAllSegments,
  getSegmentWithParent,
  getSegmentChildren,
  propagateParentChanges,
  syncSegmentFromParent,
  handleApiError,
} from '@lib/summaryApi';
import { useAuth } from '@lib/auth';

interface SegmentComparisonsPanelProps {
  userId?: string;
  adminId: string;
  consultationType: ConsultationTypeCode;
}

type ViewMode = 'compare' | 'children' | 'propagate';

export function SegmentComparisonsPanel({
  userId,
  adminId,
  consultationType,
}: SegmentComparisonsPanelProps) {
  const { getAccessToken } = useAuth();
  const [viewMode, setViewMode] = useState<ViewMode>('compare');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Segment lists
  const [segments, setSegments] = useState<any[]>([]);
  const [selectedSegment, setSelectedSegment] = useState<string>('');

  // Compare view
  const [comparisonData, setComparisonData] = useState<any>(null);

  // Children view
  const [childrenData, setChildrenData] = useState<any>(null);

  // Propagate view
  const [selectedChildren, setSelectedChildren] = useState<Set<string>>(new Set());
  const [forceUpdateDiverged, setForceUpdateDiverged] = useState(false);
  const [propagateResults, setPropagateResults] = useState<any>(null);

  useEffect(() => {
    loadSegments();
  }, [consultationType]);

  const loadSegments = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await getAllSegments(consultationType, true);
      if (response.success) {
        setSegments(response.segments);
        // Select first segment by default
        if (response.segments.length > 0 && !selectedSegment) {
          setSelectedSegment(response.segments[0].segment_code);
        }
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSegmentSelect = async (segmentCode: string) => {
    setSelectedSegment(segmentCode);
    setComparisonData(null);
    setChildrenData(null);
    setPropagateResults(null);
    setSelectedChildren(new Set());

    if (viewMode === 'compare') {
      await loadComparison(segmentCode);
    } else if (viewMode === 'children' || viewMode === 'propagate') {
      await loadChildren(segmentCode);
    }
  };

  const loadComparison = async (segmentCode: string) => {
    try {
      setLoading(true);
      setError(null);

      const response = await getSegmentWithParent(segmentCode, undefined);
      if (response.success) {
        setComparisonData(response.data);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const loadChildren = async (segmentCode: string) => {
    try {
      setLoading(true);
      setError(null);

      const response = await getSegmentChildren(segmentCode, true);
      if (response.success) {
        setChildrenData(response);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSyncFromParent = async (segmentCode: string, force: boolean = false) => {
    if (!confirm(`Sync "${segmentCode}" from its parent?${force ? ' This will overwrite customizations!' : ''}`)) {
      return;
    }

    try {
      setError(null);
      setSuccess(null);

      const response = await syncSegmentFromParent(segmentCode, undefined, force, getAccessToken());
      if (response.success) {
        setSuccess(response.message);
        await loadComparison(segmentCode);
      }
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handlePropagateChanges = async () => {
    if (selectedChildren.size === 0) {
      setError('Please select at least one child segment to update');
      return;
    }

    if (!confirm(`Propagate changes from "${selectedSegment}" to ${selectedChildren.size} child segment(s)?`)) {
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setSuccess(null);

      const response = await propagateParentChanges(
        selectedSegment,
        Array.from(selectedChildren),
        forceUpdateDiverged,
        adminId,
        getAccessToken()
      );

      if (response.success) {
        setPropagateResults(response);
        setSuccess(response.message);
        await loadChildren(selectedSegment);
        setSelectedChildren(new Set());
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const toggleChildSelection = (childCode: string) => {
    const newSelection = new Set(selectedChildren);
    if (newSelection.has(childCode)) {
      newSelection.delete(childCode);
    } else {
      newSelection.add(childCode);
    }
    setSelectedChildren(newSelection);
  };

  const selectAllChildren = (type: 'all' | 'in_sync' | 'diverged') => {
    if (!childrenData) return;

    const newSelection = new Set<string>();
    childrenData.children.forEach((child: any) => {
      if (type === 'all') {
        newSelection.add(child.segment_code);
      } else if (type === 'in_sync' && !child.diverged_from_parent) {
        newSelection.add(child.segment_code);
      } else if (type === 'diverged' && child.diverged_from_parent) {
        newSelection.add(child.segment_code);
      }
    });
    setSelectedChildren(newSelection);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Segment Comparisons</h2>
          <p className="text-sm text-gray-600 mt-1">
            Compare child vs. parent, view clones, and propagate changes
          </p>
        </div>
      </div>

      {/* View Mode Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => {
              setViewMode('compare');
              if (selectedSegment) loadComparison(selectedSegment);
            }}
            className={`${
              viewMode === 'compare'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
          >
            Compare with Parent
          </button>
          <button
            onClick={() => {
              setViewMode('children');
              if (selectedSegment) loadChildren(selectedSegment);
            }}
            className={`${
              viewMode === 'children'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
          >
            View Children
          </button>
          <button
            onClick={() => {
              setViewMode('propagate');
              if (selectedSegment) loadChildren(selectedSegment);
            }}
            className={`${
              viewMode === 'propagate'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
          >
            Propagate Changes
          </button>
        </nav>
      </div>

      {/* Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center">
            <svg className="w-5 h-5 text-red-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <p className="text-red-800">{error}</p>
          </div>
        </div>
      )}

      {success && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-center">
            <svg className="w-5 h-5 text-green-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <p className="text-green-800">{success}</p>
          </div>
        </div>
      )}

      {/* Segment Selector */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Select Segment
        </label>
        <select
          value={selectedSegment}
          onChange={(e) => handleSegmentSelect(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
        >
          <option value="">Choose a segment...</option>
          {segments.map((seg) => (
            <option key={seg.segment_code} value={seg.segment_code}>
              {seg.segment_name} ({seg.segment_code})
              {seg.is_active === false && ' - INACTIVE'}
              {seg.parent_segment_code && ` - Child of ${seg.parent_segment_code}`}
            </option>
          ))}
        </select>
      </div>

      {/* Content based on view mode */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-3 text-gray-600">Loading...</span>
        </div>
      ) : (
        <>
          {viewMode === 'compare' && comparisonData && (
            <CompareView
              data={comparisonData}
              onSync={handleSyncFromParent}
            />
          )}

          {viewMode === 'children' && childrenData && (
            <ChildrenView data={childrenData} />
          )}

          {viewMode === 'propagate' && childrenData && (
            <PropagateView
              data={childrenData}
              selectedChildren={selectedChildren}
              forceUpdateDiverged={forceUpdateDiverged}
              onToggleChild={toggleChildSelection}
              onSelectAll={selectAllChildren}
              onForceToggle={setForceUpdateDiverged}
              onPropagate={handlePropagateChanges}
              results={propagateResults}
            />
          )}
        </>
      )}
    </div>
  );
}

// Compare View Component
function CompareView({
  data,
  onSync,
}: {
  data: any;
  onSync: (segmentCode: string, force: boolean) => void;
}) {
  const { segment, parent, relationship } = data;

  if (!relationship.has_parent) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-8 text-center">
        <svg className="w-12 h-12 text-blue-600 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-blue-900 font-medium">No Parent Segment</p>
        <p className="text-sm text-blue-700 mt-1">
          This segment was not cloned from another segment, so there's nothing to compare.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Relationship Info */}
      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-sm font-semibold text-purple-900 flex items-center gap-2">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z" />
                <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z" />
              </svg>
              Parent-Child Relationship
            </h3>
            <dl className="mt-2 space-y-1 text-xs text-purple-800">
              <div className="flex gap-2">
                <dt className="font-medium">Parent:</dt>
                <dd className="font-mono">{relationship.parent_code}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium">Cloned:</dt>
                <dd>{relationship.cloned_at ? new Date(relationship.cloned_at).toLocaleString() : 'Unknown'}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium">Status:</dt>
                <dd>
                  {relationship.diverged ? (
                    <span className="px-2 py-0.5 bg-amber-100 text-amber-800 rounded-full font-medium">
                      Diverged (Customized)
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 bg-green-100 text-green-800 rounded-full font-medium">
                      In Sync
                    </span>
                  )}
                </dd>
              </div>
              {relationship.last_sync_at && (
                <div className="flex gap-2">
                  <dt className="font-medium">Last Sync:</dt>
                  <dd>{new Date(relationship.last_sync_at).toLocaleString()}</dd>
                </div>
              )}
            </dl>
          </div>
          <div className="space-y-2">
            {!relationship.diverged && (
              <button
                onClick={() => onSync(segment.segment_code, false)}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium text-sm transition-colors"
              >
                Sync from Parent
              </button>
            )}
            {relationship.diverged && (
              <button
                onClick={() => onSync(segment.segment_code, true)}
                className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-medium text-sm transition-colors"
              >
                Force Sync (Lose Changes)
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Side-by-side comparison */}
      <div className="grid grid-cols-2 gap-6">
        {/* Parent */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10.394 2.08a1 1 0 00-.788 0l-7 3a1 1 0 000 1.84L5.25 8.051a.999.999 0 01.356-.257l4-1.714a1 1 0 11.788 1.838L7.667 9.088l1.94.831a1 1 0 00.787 0l7-3a1 1 0 000-1.838l-7-3zM3.31 9.397L5 10.12v4.102a8.969 8.969 0 00-1.05-.174 1 1 0 01-.89-.89 11.115 11.115 0 01.25-3.762zM9.3 16.573A9.026 9.026 0 007 14.935v-3.957l1.818.78a3 3 0 002.364 0l5.508-2.361a11.026 11.026 0 01.25 3.762 1 1 0 01-.89.89 8.968 8.968 0 00-5.35 2.524 1 1 0 01-1.4 0zM6 18a1 1 0 001-1v-2.065a8.935 8.935 0 00-2-.712V17a1 1 0 001 1z" />
            </svg>
            Parent: {parent?.segment_name}
          </h3>
          <SegmentDetails segment={parent} />
        </div>

        {/* Child */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <svg className="w-5 h-5 text-purple-600" fill="currentColor" viewBox="0 0 20 20">
              <path d="M13 7H7v6h6V7z" />
              <path fillRule="evenodd" d="M7 2a1 1 0 012 0v1h2V2a1 1 0 112 0v1h2a2 2 0 012 2v2h1a1 1 0 110 2h-1v2h1a1 1 0 110 2h-1v2a2 2 0 01-2 2h-2v1a1 1 0 11-2 0v-1H9v1a1 1 0 11-2 0v-1H5a2 2 0 01-2-2v-2H2a1 1 0 110-2h1V9H2a1 1 0 010-2h1V5a2 2 0 012-2h2V2zM5 5h10v10H5V5z" clipRule="evenodd" />
            </svg>
            Child: {segment.segment_name}
          </h3>
          <SegmentDetails segment={segment} />
        </div>
      </div>
    </div>
  );
}

// Children View Component
function ChildrenView({ data }: { data: any }) {
  const { parent_segment_code, children, counts } = data;

  if (children.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
        <svg className="w-12 h-12 text-gray-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
        <p className="text-gray-600 font-medium">No Child Segments</p>
        <p className="text-sm text-gray-500 mt-1">
          This segment has no clones yet.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-900">{counts.total}</div>
          <div className="text-sm text-blue-700">Total Children</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-900">{counts.in_sync}</div>
          <div className="text-sm text-green-700">In Sync</div>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <div className="text-2xl font-bold text-amber-900">{counts.diverged}</div>
          <div className="text-sm text-amber-700">Diverged</div>
        </div>
      </div>

      {/* Children List */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Segment
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Cloned
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Last Sync
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {children.map((child: any) => (
              <tr key={child.segment_code} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">{child.segment_name}</div>
                  <div className="text-xs text-gray-500 font-mono">{child.segment_code}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  {child.diverged_from_parent ? (
                    <span className="px-2 py-1 text-xs font-medium bg-amber-100 text-amber-800 rounded-full">
                      Diverged
                    </span>
                  ) : (
                    <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full">
                      In Sync
                    </span>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {child.cloned_at ? new Date(child.cloned_at).toLocaleDateString() : 'N/A'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {child.last_parent_sync_at ? new Date(child.last_parent_sync_at).toLocaleDateString() : 'Never'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Propagate View Component
function PropagateView({
  data,
  selectedChildren,
  forceUpdateDiverged,
  onToggleChild,
  onSelectAll,
  onForceToggle,
  onPropagate,
  results,
}: {
  data: any;
  selectedChildren: Set<string>;
  forceUpdateDiverged: boolean;
  onToggleChild: (childCode: string) => void;
  onSelectAll: (type: 'all' | 'in_sync' | 'diverged') => void;
  onForceToggle: (force: boolean) => void;
  onPropagate: () => void;
  results: any;
}) {
  const { children, counts } = data;

  if (children.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
        <p className="text-gray-600">No child segments to propagate changes to.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Selection Controls */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-blue-900">Select Children to Update</h3>
            <p className="text-xs text-blue-700 mt-1">
              Choose which child segments should receive the parent's latest changes
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => onSelectAll('all')}
              className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Select All
            </button>
            <button
              onClick={() => onSelectAll('in_sync')}
              className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700"
            >
              In Sync Only
            </button>
            <button
              onClick={() => onSelectAll('diverged')}
              className="px-3 py-1 text-sm bg-amber-600 text-white rounded hover:bg-amber-700"
            >
              Diverged Only
            </button>
          </div>
        </div>

        <div className="mt-3 flex items-start">
          <input
            type="checkbox"
            checked={forceUpdateDiverged}
            onChange={(e) => onForceToggle(e.target.checked)}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded mt-0.5"
          />
          <div className="ml-3">
            <label className="text-sm font-medium text-gray-900">
              Force update diverged segments
            </label>
            <p className="text-xs text-gray-600 mt-0.5">
              ⚠️ This will overwrite any customizations in diverged segments
            </p>
          </div>
        </div>
      </div>

      {/* Children Selection List */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 w-12">
                <input
                  type="checkbox"
                  checked={selectedChildren.size === children.length}
                  onChange={() => {
                    if (selectedChildren.size === children.length) {
                      // Deselect all by selecting only in_sync (empty result)
                      onSelectAll('in_sync');
                    } else {
                      onSelectAll('all');
                    }
                  }}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Segment
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Last Sync
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {children.map((child: any) => {
              const isSelected = selectedChildren.has(child.segment_code);
              const willSkip = child.diverged_from_parent && !forceUpdateDiverged;

              return (
                <tr
                  key={child.segment_code}
                  className={`${isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'} ${willSkip ? 'opacity-50' : ''}`}
                >
                  <td className="px-6 py-4">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleChild(child.segment_code)}
                      className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{child.segment_name}</div>
                    <div className="text-xs text-gray-500 font-mono">{child.segment_code}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      {child.diverged_from_parent ? (
                        <>
                          <span className="px-2 py-1 text-xs font-medium bg-amber-100 text-amber-800 rounded-full">
                            Diverged
                          </span>
                          {willSkip && (
                            <span className="text-xs text-amber-600">(Will skip)</span>
                          )}
                        </>
                      ) : (
                        <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full">
                          In Sync
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {child.last_parent_sync_at ? new Date(child.last_parent_sync_at).toLocaleDateString() : 'Never'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Propagate Button */}
      <div className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg p-4">
        <div>
          <p className="text-sm font-medium text-gray-900">
            {selectedChildren.size} segment(s) selected
          </p>
          <p className="text-xs text-gray-600 mt-0.5">
            Changes will be propagated from the parent segment
          </p>
        </div>
        <button
          onClick={onPropagate}
          disabled={selectedChildren.size === 0}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Propagate to {selectedChildren.size} Segment(s)
        </button>
      </div>

      {/* Results */}
      {results && (
        <div className="space-y-4">
          {results.updated.length > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-green-900 mb-2">
                ✓ Updated ({results.updated.length})
              </h4>
              <ul className="text-xs text-green-800 space-y-1">
                {results.updated.map((item: any) => (
                  <li key={item.segment_code} className="font-mono">
                    {item.segment_code} - Synced at {new Date(item.synced_at).toLocaleString()}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {results.skipped.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-amber-900 mb-2">
                ⚠ Skipped ({results.skipped.length})
              </h4>
              <ul className="text-xs text-amber-800 space-y-1">
                {results.skipped.map((item: any) => (
                  <li key={item.segment_code} className="font-mono">
                    {item.segment_code} - {item.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {results.errors.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-red-900 mb-2">
                ✗ Errors ({results.errors.length})
              </h4>
              <ul className="text-xs text-red-800 space-y-1">
                {results.errors.map((item: any) => (
                  <li key={item.segment_code} className="font-mono">
                    {item.segment_code} - {item.error}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Segment Details Component
function SegmentDetails({ segment }: { segment: any }) {
  if (!segment) return <div className="text-gray-500">No data available</div>;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-4">
      <div>
        <label className="text-xs font-medium text-gray-500 uppercase">Code</label>
        <p className="text-sm font-mono text-gray-900 mt-1">{segment.segment_code}</p>
      </div>

      <div>
        <label className="text-xs font-medium text-gray-500 uppercase">Prompt</label>
        <pre className="text-xs text-gray-900 mt-1 bg-white p-3 rounded border border-gray-200 overflow-x-auto max-h-40">
          {segment.prompt_section_text}
        </pre>
      </div>

      <div>
        <label className="text-xs font-medium text-gray-500 uppercase">Schema</label>
        <pre className="text-xs text-gray-900 mt-1 bg-white p-3 rounded border border-gray-200 overflow-x-auto max-h-40 font-mono">
          {JSON.stringify(segment.schema_definition_json, null, 2)}
        </pre>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-gray-500 uppercase">Category</label>
          <p className="text-sm text-gray-900 mt-1">{segment.default_category}</p>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 uppercase">Display Order</label>
          <p className="text-sm text-gray-900 mt-1">{segment.display_order}</p>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 uppercase">Brevity</label>
          <p className="text-sm text-gray-900 mt-1">{segment.default_brevity_level}</p>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 uppercase">Terminology</label>
          <p className="text-sm text-gray-900 mt-1">{segment.default_terminology_style}</p>
        </div>
      </div>
    </div>
  );
}

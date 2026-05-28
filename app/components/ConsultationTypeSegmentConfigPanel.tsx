'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
  useDroppable,
} from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import type { ConsultationTypeCode, BrevityLevel, TerminologyStyle } from '@lib/types';
import {
  getConsultationTypeSegments,
  updateConsultationTypeSegment,
  bulkUpdateConsultationTypeSegments,
  deleteSegment,
  handleApiError,
  type ConsultationTypeSegmentUpdate,
} from '@lib/summaryApi';
import { SegmentList } from './SegmentList';
import { ConsultationTypeSegmentEditModal } from './ConsultationTypeSegmentEditModal';
import { useAuth } from '@lib/auth';

interface ConsultationTypeSegmentConfigPanelProps {
  consultationTypeCode: ConsultationTypeCode;
  consultationTypeName: string;
  onClose: () => void;
  onNavigateToSegmentDefinition?: (segmentId: string) => void;
}

interface ConsultationTypeSegment {
  id: string;
  segment_code: string;
  segment_name: string;
  default_category: 'core' | 'additional' | 'excluded';
  display_order: number;
  default_brevity_level: BrevityLevel;
  default_terminology_style: TerminologyStyle;
  consultation_type_id: string | null;
  is_active?: boolean;
  is_required: boolean;
  prompt_section_text: string;
  schema_definition_json: any;
}

// Droppable zone component
function DroppableZone({ id, children }: { id: string; children: React.ReactNode }) {
  const { setNodeRef } = useDroppable({ id });

  return (
    <div ref={setNodeRef} className="min-h-[100px]">
      {children}
    </div>
  );
}

export function ConsultationTypeSegmentConfigPanel({
  consultationTypeCode,
  consultationTypeName,
  onClose,
  onNavigateToSegmentDefinition,
}: ConsultationTypeSegmentConfigPanelProps) {
  const { getAccessToken } = useAuth();
  const [coreSegments, setCoreSegments] = useState<ConsultationTypeSegment[]>([]);
  const [additionalSegments, setAdditionalSegments] = useState<ConsultationTypeSegment[]>([]);
  const [excludedSegments, setExcludedSegments] = useState<ConsultationTypeSegment[]>([]);
  const [activeSegment, setActiveSegment] = useState<ConsultationTypeSegment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Multi-selection state
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedSegments, setSelectedSegments] = useState<Set<string>>(new Set());
  const [editingSegment, setEditingSegment] = useState<ConsultationTypeSegment | null>(null);

  // Calculate adaptive modal height based on total segment count
  const modalMaxHeight = useMemo(() => {
    // Find the longest column to determine optimal height
    const maxColumnLength = Math.max(
      coreSegments.length,
      additionalSegments.length,
      excludedSegments.length
    );

    // Use maximum height to minimize scrolling
    if (maxColumnLength <= 3) return 'max-h-[85vh]';
    if (maxColumnLength <= 5) return 'max-h-[92vh]';
    // For 6+ segments, always use max height to avoid scrolling
    return 'max-h-[98vh]';
  }, [coreSegments.length, additionalSegments.length, excludedSegments.length]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  useEffect(() => {
    loadSegments();
  }, [consultationTypeCode]);

  const loadSegments = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await getConsultationTypeSegments(consultationTypeCode, getAccessToken());

      if (response.success) {
        const segments = response.segments;

        // Separate segments by category
        const core = segments
          .filter((s: ConsultationTypeSegment) => s.default_category === 'core')
          .sort((a, b) => a.display_order - b.display_order);

        const additional = segments
          .filter((s: ConsultationTypeSegment) => s.default_category === 'additional')
          .sort((a, b) => a.display_order - b.display_order);

        const excluded = segments
          .filter((s: ConsultationTypeSegment) => s.default_category === 'excluded')
          .sort((a, b) => a.display_order - b.display_order);

        console.log('[ConsultationTypeSegmentConfig] Loaded segments:', {
          total: segments.length,
          core: core.length,
          additional: additional.length,
          excluded: excluded.length,
          excludedSegments: excluded.map((s: ConsultationTypeSegment) => s.segment_code)
        });

        setCoreSegments(core);
        setAdditionalSegments(additional);
        setExcludedSegments(excluded);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleDragStart = (event: DragStartEvent) => {
    const { active } = event;
    const segment = findSegmentByCode(active.id as string);
    setActiveSegment(segment);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveSegment(null);

    if (!over) return;

    const activeSegment = findSegmentByCode(active.id as string);
    if (!activeSegment) return;

    // Determine target category based on drop zone or segment being hovered
    let targetCategory: 'core' | 'additional' | 'excluded' | null = null;
    let targetSegment: ConsultationTypeSegment | null = null;
    const overIdString = over.id as string;

    // Check if dropped on a droppable zone
    if (overIdString === 'core-droppable') {
      targetCategory = 'core';
    } else if (overIdString === 'additional-droppable') {
      targetCategory = 'additional';
    } else if (overIdString === 'excluded-droppable') {
      targetCategory = 'excluded';
    } else {
      // Dropped on a segment - find which category that segment belongs to
      targetSegment = findSegmentByCode(overIdString);
      if (targetSegment) {
        targetCategory = targetSegment.default_category;
      }
    }

    // If we couldn't determine target category, don't move
    if (!targetCategory) return;

    const activeCategory = activeSegment.default_category;

    // If dropped in different category, move the segment
    if (targetCategory !== activeCategory) {
      await handleMoveSegment(activeSegment, targetCategory);
    } else if (targetSegment && active.id !== over.id) {
      // Reordering within the same category
      await handleReorderSegment(activeSegment, targetSegment, targetCategory);
    }
  };

  const handleReorderSegment = async (
    draggedSegment: ConsultationTypeSegment,
    targetSegment: ConsultationTypeSegment,
    category: 'core' | 'additional' | 'excluded'
  ) => {
    // Check if segment is required - required segments cannot be reordered (they must stay at top)
    // Actually, we should allow reordering within required segments too

    try {
      setSaving(true);
      setError(null);

      // Get the current segments for this category
      let categorySegments: ConsultationTypeSegment[];
      if (category === 'core') {
        categorySegments = [...coreSegments];
      } else if (category === 'additional') {
        categorySegments = [...additionalSegments];
      } else {
        categorySegments = [...excludedSegments];
      }

      // Find indices
      const oldIndex = categorySegments.findIndex(s => s.segment_code === draggedSegment.segment_code);
      const newIndex = categorySegments.findIndex(s => s.segment_code === targetSegment.segment_code);

      if (oldIndex === -1 || newIndex === -1 || oldIndex === newIndex) {
        return;
      }

      // Reorder the array
      const reorderedSegments = arrayMove(categorySegments, oldIndex, newIndex);

      // OPTIMIZED: Batch update all affected segments in a single API call
      const segmentsToUpdate = reorderedSegments
        .map((segment, index) => {
          if (segment.display_order !== index) {
            return {
              segment_code: segment.segment_code,
              category: segment.default_category,
              display_order: index,
            };
          }
          return null;
        })
        .filter((s): s is NonNullable<typeof s> => s !== null);

      if (segmentsToUpdate.length > 0) {
        await bulkUpdateConsultationTypeSegments(consultationTypeCode, segmentsToUpdate, getAccessToken());
      }

      // Reload segments
      await loadSegments();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const handleMoveSegment = async (
    segment: ConsultationTypeSegment,
    newCategory: 'core' | 'additional' | 'excluded'
  ) => {
    console.log('[ConsultationTypeSegmentConfig] Moving segment:', {
      segment: segment.segment_code,
      from: segment.default_category,
      to: newCategory
    });

    // Check if segment is required - required segments cannot be moved from CORE
    if (segment.is_required && segment.default_category === 'core' && newCategory !== 'core') {
      setError(`Cannot move required segment "${segment.segment_name}" from CORE to ${newCategory.toUpperCase()}`);
      return;
    }

    try {
      setSaving(true);
      setError(null);

      // Calculate new display order (append to end of target category)
      let newDisplayOrder = 0;
      if (newCategory === 'core') {
        newDisplayOrder = coreSegments.length;
      } else if (newCategory === 'additional') {
        newDisplayOrder = additionalSegments.length;
      } else {
        newDisplayOrder = excludedSegments.length;
      }

      const config: ConsultationTypeSegmentUpdate = {
        default_category: newCategory,
        display_order: newDisplayOrder,
      };

      console.log('[ConsultationTypeSegmentConfig] Updating segment with config:', config);

      await updateConsultationTypeSegment(consultationTypeCode, segment.segment_code, config, getAccessToken());

      console.log('[ConsultationTypeSegmentConfig] Update successful, reloading segments...');

      // Reload segments
      await loadSegments();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const findSegmentByCode = (code: string): ConsultationTypeSegment | null => {
    return (
      coreSegments.find((s) => s.segment_code === code) ||
      additionalSegments.find((s) => s.segment_code === code) ||
      excludedSegments.find((s) => s.segment_code === code) ||
      null
    );
  };

  // Multi-select handlers
  const handleToggleMultiSelectMode = () => {
    setMultiSelectMode(!multiSelectMode);
    setSelectedSegments(new Set()); // Clear selections when toggling mode
  };

  const handleSegmentToggle = (segmentCode: string) => {
    const newSelected = new Set(selectedSegments);
    if (newSelected.has(segmentCode)) {
      newSelected.delete(segmentCode);
    } else {
      newSelected.add(segmentCode);
    }
    setSelectedSegments(newSelected);
  };

  const handleBulkMove = async (targetCategory: 'core' | 'additional' | 'excluded') => {
    if (selectedSegments.size === 0) return;

    try {
      setSaving(true);
      setError(null);

      // Get target category's next display order
      let nextDisplayOrder = 0;
      if (targetCategory === 'core') {
        nextDisplayOrder = coreSegments.length;
      } else if (targetCategory === 'additional') {
        nextDisplayOrder = additionalSegments.length;
      } else {
        nextDisplayOrder = excludedSegments.length;
      }

      // Check for required segments being moved out of CORE
      const requiredSegmentMovingOut = Array.from(selectedSegments).some((segmentCode) => {
        const segment = findSegmentByCode(segmentCode);
        return segment && segment.is_required && segment.default_category === 'core' && targetCategory !== 'core';
      });

      if (requiredSegmentMovingOut) {
        setError('Cannot move required segments out of CORE category');
        return;
      }

      // OPTIMIZED: Collect all segment updates and batch them
      const segmentsToUpdate: Array<{ segment_code: string; category: string; display_order: number }> = [];
      for (const segmentCode of selectedSegments) {
        const segment = findSegmentByCode(segmentCode);
        if (segment && segment.default_category !== targetCategory) {
          segmentsToUpdate.push({
            segment_code: segmentCode,
            category: targetCategory,
            display_order: nextDisplayOrder++,
          });
        }
      }

      // Single API call for all updates
      if (segmentsToUpdate.length > 0) {
        await bulkUpdateConsultationTypeSegments(consultationTypeCode, segmentsToUpdate, getAccessToken());
      }

      // Clear selections and reload
      setSelectedSegments(new Set());
      await loadSegments();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const handleSegmentClick = (segment: ConsultationTypeSegment) => {
    // Always open edit modal when clicking segment
    // (In multi-select mode, clicking segment text opens modal, clicking checkbox toggles selection)
    setEditingSegment(segment);
  };

  const handleCloseEditModal = () => {
    setEditingSegment(null);
  };

  const handleEditSuccess = async () => {
    setEditingSegment(null);
    await loadSegments();
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 pt-8">
        <div className="bg-white rounded-lg p-8">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-600">Loading segments...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-1">
      <div className={`bg-white rounded-lg shadow-xl max-w-5xl w-full ${modalMaxHeight} overflow-y-auto`}>
        {/* Header */}
        <div className="bg-blue-600 text-white p-6 rounded-t-lg sticky top-0 z-10">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-2xl font-bold">Configure Consultation Type Segments</h2>
              <p className="text-blue-100 text-sm mt-1">
                {consultationTypeName} ({consultationTypeCode})
              </p>
              <p className="text-blue-100 text-xs mt-1">
                These are the base segment definitions that templates inherit from
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleToggleMultiSelectMode}
                disabled={saving}
                className={`${
                  multiSelectMode
                    ? 'bg-blue-500 text-white'
                    : 'bg-white text-blue-600'
                } px-4 py-2 rounded-lg font-medium hover:bg-blue-50 transition-colors disabled:opacity-50 flex items-center gap-2`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                {multiSelectMode ? 'Exit Multi-Select' : 'Multi-Select'}
              </button>
              <button
                onClick={onClose}
                className="bg-white text-blue-600 hover:bg-blue-50 px-4 py-2 rounded-lg font-medium transition-colors shadow-sm"
              >
                Close
              </button>
            </div>
          </div>

          {/* Bulk Move Controls */}
          {multiSelectMode && selectedSegments.size > 0 && (
            <div className="bg-blue-500 rounded-lg p-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                </svg>
                <span className="font-semibold">{selectedSegments.size} segment{selectedSegments.size > 1 ? 's' : ''} selected</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium mr-2">Move to:</span>
                <button
                  onClick={() => handleBulkMove('core')}
                  disabled={saving}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  CORE
                </button>
                <button
                  onClick={() => handleBulkMove('additional')}
                  disabled={saving}
                  className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  ADDITIONAL
                </button>
                <button
                  onClick={() => handleBulkMove('excluded')}
                  disabled={saving}
                  className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  EXCLUDED
                </button>
                <button
                  onClick={() => setSelectedSegments(new Set())}
                  disabled={saving}
                  className="bg-white text-blue-600 px-4 py-2 rounded-lg font-medium hover:bg-blue-50 transition-colors disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="p-6 space-y-4">
          {/* Error Display */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-center">
                <svg
                  className="w-5 h-5 text-red-600 mr-2"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
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

          {/* Info Banner */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-start">
              <svg
                className="w-5 h-5 text-blue-600 mr-2 mt-0.5 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <p className="text-sm text-blue-900 font-medium">
                  Junction Table Architecture
                </p>
                <p className="text-xs text-blue-800 mt-1">
                  Segments are linked to consultation types via junction tables. Moving segments updates their category for <strong>{consultationTypeName}</strong> only. Required segments cannot be moved from CORE.
                </p>
              </div>
            </div>
          </div>

          <DndContext
            sensors={sensors}
            collisionDetection={closestCorners}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* CORE Segments */}
              <div className="bg-blue-50 rounded-lg p-3 border-2 border-blue-200">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-base font-bold text-blue-900">
                    CORE ({coreSegments.length})
                  </h3>
                  <span className="text-xs font-semibold text-blue-700 bg-blue-200 px-2 py-1 rounded-md">
                    Essential
                  </span>
                </div>
                <p className="text-xs text-blue-800 mb-3 font-medium">
                  Default essential segments for this consultation type
                </p>
                <DroppableZone id="core-droppable">
                  <SortableContext
                    items={coreSegments.map((s) => s.segment_code)}
                    strategy={verticalListSortingStrategy}
                  >
                    <SegmentList
                      segments={coreSegments.map((s) => ({
                        id: s.id,
                        segment_code: s.segment_code,
                        segment_name: s.segment_name,
                        default_category: s.default_category,
                        display_order: s.display_order,
                        is_active: s.is_active,
                        is_required: s.is_required,
                        prompt_section_text: s.prompt_section_text,
                        schema_definition_json: s.schema_definition_json,
                        default_brevity_level: s.default_brevity_level,
                        default_terminology_style: s.default_terminology_style,
                      }))}
                      category="core"
                      onSegmentClick={(segment) => {
                        const fullSegment = coreSegments.find(s => s.segment_code === segment.segment_code);
                        if (fullSegment) handleSegmentClick(fullSegment);
                      }}
                      disabled={saving}
                      multiSelectMode={multiSelectMode}
                      selectedSegments={selectedSegments}
                      onSegmentToggle={handleSegmentToggle}
                    />
                  </SortableContext>
                </DroppableZone>
              </div>

              {/* ADDITIONAL Segments */}
              <div className="bg-gray-50 rounded-lg p-3 border-2 border-gray-300">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-base font-bold text-gray-900">
                    ADDITIONAL ({additionalSegments.length})
                  </h3>
                  <span className="text-xs font-semibold text-gray-700 bg-gray-300 px-2 py-1 rounded-md">
                    Optional
                  </span>
                </div>
                <p className="text-xs text-gray-800 mb-3 font-medium">
                  Default supplementary segments
                </p>
                <DroppableZone id="additional-droppable">
                  <SortableContext
                    items={additionalSegments.map((s) => s.segment_code)}
                    strategy={verticalListSortingStrategy}
                  >
                    <SegmentList
                      segments={additionalSegments.map((s) => ({
                        id: s.id,
                        segment_code: s.segment_code,
                        segment_name: s.segment_name,
                        default_category: s.default_category,
                        display_order: s.display_order,
                        is_active: s.is_active,
                        is_required: s.is_required,
                        prompt_section_text: s.prompt_section_text,
                        schema_definition_json: s.schema_definition_json,
                        default_brevity_level: s.default_brevity_level,
                        default_terminology_style: s.default_terminology_style,
                      }))}
                      category="additional"
                      onSegmentClick={(segment) => {
                        const fullSegment = additionalSegments.find(s => s.segment_code === segment.segment_code);
                        if (fullSegment) handleSegmentClick(fullSegment);
                      }}
                      disabled={saving}
                      multiSelectMode={multiSelectMode}
                      selectedSegments={selectedSegments}
                      onSegmentToggle={handleSegmentToggle}
                    />
                  </SortableContext>
                </DroppableZone>
              </div>

              {/* EXCLUDED Segments */}
              <div className="bg-red-50 rounded-lg p-3 border-2 border-red-200">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-base font-bold text-red-900">
                    EXCLUDED ({excludedSegments.length})
                  </h3>
                  <span className="text-xs font-semibold text-red-700 bg-red-200 px-2 py-1 rounded-md">
                    Hidden
                  </span>
                </div>
                <p className="text-xs text-red-800 mb-3 font-medium">
                  Segments explicitly hidden from this consultation type
                </p>
                <DroppableZone id="excluded-droppable">
                  <SortableContext
                    items={excludedSegments.map((s) => s.segment_code)}
                    strategy={verticalListSortingStrategy}
                  >
                    <SegmentList
                      segments={excludedSegments.map((s) => ({
                        id: s.id,
                        segment_code: s.segment_code,
                        segment_name: s.segment_name,
                        default_category: s.default_category,
                        display_order: s.display_order,
                        is_active: s.is_active,
                        is_required: s.is_required,
                        prompt_section_text: s.prompt_section_text,
                        schema_definition_json: s.schema_definition_json,
                        default_brevity_level: s.default_brevity_level,
                        default_terminology_style: s.default_terminology_style,
                      }))}
                      category="excluded"
                      onSegmentClick={(segment) => {
                        const fullSegment = excludedSegments.find(s => s.segment_code === segment.segment_code);
                        if (fullSegment) handleSegmentClick(fullSegment);
                      }}
                      disabled={saving}
                      multiSelectMode={multiSelectMode}
                      selectedSegments={selectedSegments}
                      onSegmentToggle={handleSegmentToggle}
                    />
                  </SortableContext>
                </DroppableZone>
              </div>
            </div>

            <DragOverlay>
              {activeSegment ? (
                <div className="bg-white border-2 border-blue-500 rounded-lg p-3 shadow-xl">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-medium">
                      {activeSegment.segment_name}
                    </span>
                    {activeSegment.is_required && (
                      <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                        Required
                      </span>
                    )}
                  </div>
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>

          <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-3">
            <div className="flex items-start">
              <svg
                className="w-4 h-4 text-yellow-700 mr-2 mt-0.5 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <p className="text-xs font-semibold text-yellow-900">Consultation Type Configuration</p>
                <p className="text-xs text-yellow-800 mt-0.5">
                  These settings define the defaults for this consultation type. Templates that inherit from this type will use these defaults. Required segments cannot be moved from CORE.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Edit Segment Modal */}
        {editingSegment && (
          <ConsultationTypeSegmentEditModal
            segment={{
              id: editingSegment.id,
              segment_code: editingSegment.segment_code,
              segment_name: editingSegment.segment_name,
              default_category: editingSegment.default_category,
              display_order: editingSegment.display_order,
              default_brevity_level: editingSegment.default_brevity_level,
              default_terminology_style: editingSegment.default_terminology_style,
            }}
            consultationTypeCode={consultationTypeCode}
            isOpen={!!editingSegment}
            onClose={handleCloseEditModal}
            onSuccess={handleEditSuccess}
            onNavigateToSegmentDefinition={onNavigateToSegmentDefinition}
          />
        )}
      </div>
    </div>
  );
}

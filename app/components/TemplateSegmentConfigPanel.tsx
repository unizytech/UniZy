'use client';

import React, { useState, useEffect } from 'react';
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
import type { Template, BrevityLevel, TerminologyStyle } from '@lib/types';
import {
  getTemplateSegments,
  updateTemplateSegment,
  bulkUpdateTemplateSegments,
  inheritTemplateConfiguration,
  // Counsellor-specific APIs (EHR-authenticated)
  getCounsellorTemplateSegments,
  updateCounsellorTemplateSegment,
  bulkUpdateCounsellorTemplateSegments,
  inheritCounsellorTemplateConfiguration,
  handleApiError,
  type TemplateSegmentConfig,
} from '@lib/summaryApi';
import { useAuth } from '@lib/auth';
import { SegmentList } from './SegmentList';
import { TemplateSegmentEditModal } from './TemplateSegmentEditModal';
import { AddSegmentsModal } from './AddSegmentsModal';

interface TemplateSegmentConfigPanelProps {
  template: Template;
  onClose: () => void;
  onNavigateToSegmentDefinition?: (segmentId: string) => void;
  doctorId?: string; // When provided, uses EHR-authenticated counsellor APIs
}

interface TemplateSegment {
  id: string;
  segment_code: string;
  segment_name: string;
  category: 'core' | 'additional' | 'excluded';
  display_order: number;
  brevity_level: BrevityLevel;
  terminology_style: TerminologyStyle;
  template_id: string;
  segment_definitions?: any;
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

export function TemplateSegmentConfigPanel({
  template,
  onClose,
  onNavigateToSegmentDefinition,
  doctorId,
}: TemplateSegmentConfigPanelProps) {
  const { getAccessToken } = useAuth();
  const [coreSegments, setCoreSegments] = useState<TemplateSegment[]>([]);
  const [additionalSegments, setAdditionalSegments] = useState<TemplateSegment[]>([]);
  const [excludedSegments, setExcludedSegments] = useState<TemplateSegment[]>([]);
  const [activeSegment, setActiveSegment] = useState<TemplateSegment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [inheriting, setInheriting] = useState(false);

  // Multi-selection state
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedSegments, setSelectedSegments] = useState<Set<string>>(new Set());
  const [editingSegment, setEditingSegment] = useState<TemplateSegment | null>(null);
  const [showAddSegmentsModal, setShowAddSegmentsModal] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  useEffect(() => {
    loadSegments();
  }, [template]);

  const loadSegments = async () => {
    try {
      setLoading(true);
      setError(null);

      // Use counsellor APIs when doctorId is provided (EHR-authenticated)
      // Otherwise use admin APIs
      const response = doctorId
        ? await getCounsellorTemplateSegments(template.template_code, doctorId, getAccessToken())
        : await getTemplateSegments(template.template_code, getAccessToken());

      if (response.success) {
        const segments = response.segments;

        // Separate segments by category
        const core = segments
          .filter((s: TemplateSegment) => s.category === 'core')
          .sort((a, b) => a.display_order - b.display_order);

        const additional = segments
          .filter((s: TemplateSegment) => s.category === 'additional')
          .sort((a, b) => a.display_order - b.display_order);

        const excluded = segments
          .filter((s: TemplateSegment) => s.category === 'excluded')
          .sort((a, b) => a.display_order - b.display_order);

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

  const handleInherit = async () => {
    if (!confirm('This will replace all segment configurations with session type defaults. Continue?')) {
      return;
    }

    try {
      setInheriting(true);
      setError(null);

      // Use counsellor APIs when doctorId is provided (EHR-authenticated)
      if (doctorId) {
        await inheritCounsellorTemplateConfiguration(template.template_code, doctorId, getAccessToken());
      } else {
        await inheritTemplateConfiguration(template.template_code, getAccessToken());
      }
      await loadSegments();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setInheriting(false);
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

    // Determine target category based on drop zone
    let targetCategory: 'core' | 'additional' | 'excluded' = 'core';
    let targetSegment: TemplateSegment | null = null;
    const overIdString = over.id as string;

    // Check exact drop zone IDs first, then fall back to checking segments
    if (overIdString === 'core-droppable' || overIdString === 'core-dropzone') {
      targetCategory = 'core';
    } else if (overIdString === 'additional-droppable' || overIdString === 'additional-dropzone') {
      targetCategory = 'additional';
    } else if (overIdString === 'excluded-droppable' || overIdString === 'excluded-dropzone') {
      targetCategory = 'excluded';
    } else {
      // Dropped on a segment - find which category that segment belongs to
      targetSegment = findSegmentByCode(overIdString);
      if (targetSegment) {
        targetCategory = targetSegment.category;
      } else {
        // Fallback: check if overIdString contains category keywords (order matters!)
        if (overIdString.includes('additional')) {
          targetCategory = 'additional';
        } else if (overIdString.includes('excluded')) {
          targetCategory = 'excluded';
        } else if (overIdString.includes('core')) {
          targetCategory = 'core';
        }
      }
    }

    const activeCategory = activeSegment.category;

    // If dropped in different category, move the segment
    if (targetCategory !== activeCategory) {
      await handleMoveSegment(activeSegment, targetCategory);
    } else if (targetSegment && active.id !== over.id) {
      // Reordering within the same category
      await handleReorderSegment(activeSegment, targetSegment, targetCategory);
    }
  };

  const handleReorderSegment = async (
    draggedSegment: TemplateSegment,
    targetSegment: TemplateSegment,
    category: 'core' | 'additional' | 'excluded'
  ) => {
    try {
      setSaving(true);
      setError(null);

      // Get the current segments for this category
      let categorySegments: TemplateSegment[];
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
              category: segment.category,
              display_order: index,
              brevity_level: segment.brevity_level,
              terminology_style: segment.terminology_style,
            };
          }
          return null;
        })
        .filter((s): s is NonNullable<typeof s> => s !== null);

      if (segmentsToUpdate.length > 0) {
        // Use counsellor APIs when doctorId is provided (EHR-authenticated)
        if (doctorId) {
          await bulkUpdateCounsellorTemplateSegments(template.template_code, segmentsToUpdate, doctorId, getAccessToken());
        } else {
          await bulkUpdateTemplateSegments(template.template_code, segmentsToUpdate, getAccessToken());
        }
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
    segment: TemplateSegment,
    newCategory: 'core' | 'additional' | 'excluded'
  ) => {
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

      const config: TemplateSegmentConfig = {
        category: newCategory,
        display_order: newDisplayOrder,
        brevity_level: segment.brevity_level,
        terminology_style: segment.terminology_style,
      };

      // Use counsellor APIs when doctorId is provided (EHR-authenticated)
      if (doctorId) {
        await updateCounsellorTemplateSegment(template.template_code, segment.segment_code, config, doctorId, getAccessToken());
      } else {
        await updateTemplateSegment(template.template_code, segment.segment_code, config, getAccessToken());
      }

      // Reload segments
      await loadSegments();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const findSegmentByCode = (code: string): TemplateSegment | null => {
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

      // OPTIMIZED: Collect all segment updates and batch them
      const segmentsToUpdate: Array<{ segment_code: string } & TemplateSegmentConfig> = [];
      for (const segmentCode of selectedSegments) {
        const segment = findSegmentByCode(segmentCode);
        if (segment && segment.category !== targetCategory) {
          segmentsToUpdate.push({
            segment_code: segmentCode,
            category: targetCategory,
            display_order: nextDisplayOrder++,
            brevity_level: segment.brevity_level,
            terminology_style: segment.terminology_style,
          });
        }
      }

      // Single API call for all updates
      if (segmentsToUpdate.length > 0) {
        // Use counsellor APIs when doctorId is provided (EHR-authenticated)
        if (doctorId) {
          await bulkUpdateCounsellorTemplateSegments(template.template_code, segmentsToUpdate, doctorId, getAccessToken());
        } else {
          await bulkUpdateTemplateSegments(template.template_code, segmentsToUpdate, getAccessToken());
        }
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

  const handleSegmentClick = (segment: TemplateSegment) => {
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
      <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[98vh] overflow-y-auto">
        {/* Header */}
        <div className="bg-blue-600 text-white p-6 rounded-t-lg sticky top-0 z-10">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-2xl font-bold">Configure Template Segments</h2>
              <p className="text-blue-100 text-sm mt-1">
                {template.template_name} ({template.template_code})
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
                onClick={() => setShowAddSegmentsModal(true)}
                disabled={saving}
                className="bg-green-500 text-white px-4 py-2 rounded-lg font-medium hover:bg-green-600 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                Add Segments
              </button>
              <button
                onClick={handleInherit}
                disabled={inheriting || saving}
                className="bg-white text-blue-600 px-4 py-2 rounded-lg font-medium hover:bg-blue-50 transition-colors disabled:opacity-50"
              >
                {inheriting ? 'Inheriting...' : 'Inherit from Type'}
              </button>
              <button
                onClick={onClose}
                className="bg-white text-blue-600 px-4 py-2 rounded-lg font-medium hover:bg-blue-50 transition-colors"
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
                  Essential segments for extraction
                </p>
                <DroppableZone id="core-droppable">
                  <SortableContext
                    items={coreSegments.map((s) => s.segment_code)}
                    strategy={verticalListSortingStrategy}
                  >
                    <SegmentList
                      segments={coreSegments.map((s) => ({
                        id: s.segment_definitions?.id || s.id,
                        segment_code: s.segment_code,
                        segment_name: s.segment_definitions?.segment_name || s.segment_code,
                        default_category: s.category,
                        display_order: s.display_order,
                        is_required: false,
                        prompt_section_text: '',
                        schema_definition_json: {},
                        default_brevity_level: s.brevity_level,
                        default_terminology_style: s.terminology_style,
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
                  Supplementary segments
                </p>
                <DroppableZone id="additional-droppable">
                  <SortableContext
                    items={additionalSegments.map((s) => s.segment_code)}
                    strategy={verticalListSortingStrategy}
                  >
                    <SegmentList
                      segments={additionalSegments.map((s) => ({
                        id: s.segment_definitions?.id || s.id,
                        segment_code: s.segment_code,
                        segment_name: s.segment_definitions?.segment_name || s.segment_code,
                        default_category: s.category,
                        display_order: s.display_order,
                        is_required: false,
                        prompt_section_text: '',
                        schema_definition_json: {},
                        default_brevity_level: s.brevity_level,
                        default_terminology_style: s.terminology_style,
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
                  Segments not included in extraction
                </p>
                <DroppableZone id="excluded-droppable">
                  <SortableContext
                    items={excludedSegments.map((s) => s.segment_code)}
                    strategy={verticalListSortingStrategy}
                  >
                    <SegmentList
                      segments={excludedSegments.map((s) => ({
                        id: s.segment_definitions?.id || s.id,
                        segment_code: s.segment_code,
                        segment_name: s.segment_definitions?.segment_name || s.segment_code,
                        default_category: s.category,
                        display_order: s.display_order,
                        is_required: false,
                        prompt_section_text: '',
                        schema_definition_json: {},
                        default_brevity_level: s.brevity_level,
                        default_terminology_style: s.terminology_style,
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
                      {activeSegment.segment_definitions?.segment_name || activeSegment.segment_code}
                    </span>
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
                <p className="text-xs font-semibold text-yellow-900">Drag & Drop to Configure</p>
                <p className="text-xs text-yellow-800 mt-0.5">
                  Drag segments between CORE, ADDITIONAL, and EXCLUDED categories to customize your template.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Edit Segment Modal */}
        {editingSegment && (
          <TemplateSegmentEditModal
            segment={{
              id: editingSegment.segment_definitions?.id || editingSegment.id,
              segment_code: editingSegment.segment_code,
              segment_name: editingSegment.segment_definitions?.segment_name || editingSegment.segment_code,
              category: editingSegment.category,
              display_order: editingSegment.display_order,
              brevity_level: editingSegment.brevity_level,
              terminology_style: editingSegment.terminology_style,
            }}
            templateCode={template.template_code}
            isOpen={!!editingSegment}
            onClose={handleCloseEditModal}
            onSuccess={handleEditSuccess}
            onNavigateToSegmentDefinition={onNavigateToSegmentDefinition}
          />
        )}

        {/* Add Segments Modal */}
        <AddSegmentsModal
          templateCode={template.template_code}
          isOpen={showAddSegmentsModal}
          onClose={() => setShowAddSegmentsModal(false)}
          onSegmentsAdded={loadSegments}
        />
      </div>
    </div>
  );
}

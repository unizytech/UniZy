'use client';

import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { Segment, SegmentCategory } from "@lib/types";

interface SegmentListProps {
  segments: Segment[];
  category: SegmentCategory;
  onSegmentClick: (segment: Segment) => void;
  selectedSegmentCode?: string | null;
  disabled?: boolean;
  multiSelectMode?: boolean;
  selectedSegments?: Set<string>;
  onSegmentToggle?: (segmentCode: string) => void;
}

interface SortableSegmentItemProps {
  segment: Segment;
  category: SegmentCategory;
  isSelected: boolean;
  onClick: () => void;
  disabled?: boolean;
  multiSelectMode?: boolean;
  isChecked?: boolean;
  onToggle?: () => void;
}

function SortableSegmentItem({
  segment,
  category,
  isSelected,
  onClick,
  disabled,
  multiSelectMode,
  isChecked,
  onToggle,
}: SortableSegmentItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: segment.segment_code,
    disabled,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const baseClasses =
    'bg-white border-2 rounded-lg p-3 cursor-pointer transition-all hover:shadow-md';
  const selectedClasses = isSelected
    ? 'border-blue-500 ring-2 ring-blue-200'
    : isChecked
      ? 'border-blue-400 bg-blue-50'
      : category === 'core'
        ? 'border-blue-300 hover:border-blue-400'
        : category === 'excluded'
          ? 'border-red-300 hover:border-red-400'
          : 'border-gray-300 hover:border-gray-400';
  const disabledClasses = disabled ? 'opacity-50 cursor-not-allowed' : '';

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onToggle) {
      onToggle();
    }
  };

  const handleSegmentClick = () => {
    if (!multiSelectMode) {
      onClick();
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`${baseClasses} ${selectedClasses} ${disabledClasses}`}
      onClick={handleSegmentClick}
      {...attributes}
      {...listeners}
    >
      <div className="flex items-center justify-between">
        {multiSelectMode && (
          <div className="flex-shrink-0 mr-3" onClick={handleCheckboxClick}>
            <input
              type="checkbox"
              checked={isChecked || false}
              onChange={() => {}}
              className="w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer"
            />
          </div>
        )}
        <div className="flex-1 min-w-0 pr-2" onClick={!multiSelectMode ? undefined : onClick}>
          <div className="flex items-center gap-2 mb-1.5">
            <h4 className="text-sm font-semibold text-gray-900">
              {segment.segment_name}
            </h4>
            {segment.is_active === false && (
              <span className="text-xs font-bold text-gray-700 bg-gray-200 px-2 py-0.5 rounded-full flex-shrink-0 border border-gray-400">
                INACTIVE
              </span>
            )}
            {segment.is_required && (
              <span className="text-xs font-medium text-red-700 bg-red-100 px-2 py-0.5 rounded-full flex-shrink-0">
                Required
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <span className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-md font-medium">
              {segment.default_brevity_level || 'balanced'}
            </span>
            <span className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-md font-medium">
              {segment.default_terminology_style?.replace(/_/g, ' ') || 'medical terms'}
            </span>
          </div>
        </div>
        <div className="flex-shrink-0">
          <svg
            className="w-5 h-5 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 8h16M4 16h16"
            />
          </svg>
        </div>
      </div>
    </div>
  );
}

export function SegmentList({
  segments,
  category,
  onSegmentClick,
  selectedSegmentCode,
  disabled,
  multiSelectMode,
  selectedSegments,
  onSegmentToggle,
}: SegmentListProps) {
  if (segments.length === 0) {
    return (
      <div className="bg-white border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
        <svg
          className="w-12 h-12 text-gray-400 mx-auto mb-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
          />
        </svg>
        <p className="text-gray-600 font-medium">No segments in this category</p>
        <p className="text-sm text-gray-500 mt-1">Drag segments here to add them</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {segments.map((segment) => (
        <SortableSegmentItem
          key={segment.segment_code}
          segment={segment}
          category={category}
          isSelected={selectedSegmentCode === segment.segment_code}
          onClick={() => onSegmentClick(segment)}
          disabled={disabled}
          multiSelectMode={multiSelectMode}
          isChecked={selectedSegments?.has(segment.segment_code)}
          onToggle={() => onSegmentToggle?.(segment.segment_code)}
        />
      ))}
    </div>
  );
}

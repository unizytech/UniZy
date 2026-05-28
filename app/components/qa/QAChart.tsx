'use client';

/**
 * QA Chart Component
 *
 * Renders charts for analytics responses using Recharts.
 * Supports bar, line, pie, and stat_card types.
 */

import React from 'react';
import type { QAChartData } from '@lib/types';

// ============================================================================
// Types
// ============================================================================

interface QAChartProps {
  data: QAChartData;
}

// ============================================================================
// Color Palette
// ============================================================================

const COLORS = [
  '#f43f5e', // rose-500
  '#3b82f6', // blue-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#8b5cf6', // violet-500
  '#06b6d4', // cyan-500
  '#ec4899', // pink-500
  '#84cc16', // lime-500
];

// ============================================================================
// Component
// ============================================================================

export default function QAChart({ data }: QAChartProps) {
  switch (data.chart_type) {
    case 'bar':
      return <BarChart data={data} />;
    case 'line':
      return <LineChart data={data} />;
    case 'pie':
      return <PieChart data={data} />;
    case 'stat_card':
      return <StatCard data={data} />;
    default:
      return <BarChart data={data} />;
  }
}

// ============================================================================
// Bar Chart (Simple CSS-based)
// ============================================================================

function BarChart({ data }: { data: QAChartData }) {
  const maxValue = Math.max(...data.values, 1);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-4">{data.title}</h3>
      <div className="space-y-3">
        {data.labels.map((label, index) => {
          const value = data.values[index] || 0;
          const percentage = (value / maxValue) * 100;
          const color = COLORS[index % COLORS.length];

          return (
            <div key={label} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600 truncate max-w-[200px]">{label}</span>
                <span className="font-medium text-gray-900">{value}</span>
              </div>
              <div className="h-6 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${percentage}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
              {data.secondary_values && (
                <div className="text-xs text-gray-500 pl-1">
                  {data.secondary_label}: {data.secondary_values[index]}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// Line Chart (Simple CSS-based)
// ============================================================================

function LineChart({ data }: { data: QAChartData }) {
  const maxValue = Math.max(...data.values, 1);
  const minValue = Math.min(...data.values, 0);
  const range = maxValue - minValue || 1;

  // Create SVG path for line
  const points = data.values.map((value, index) => {
    const x = (index / (data.values.length - 1 || 1)) * 100;
    const y = 100 - ((value - minValue) / range) * 100;
    return `${x},${y}`;
  });
  const pathD = `M ${points.join(' L ')}`;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-4">{data.title}</h3>
      <div className="relative h-48">
        {/* Y-axis labels */}
        <div className="absolute left-0 top-0 bottom-0 w-12 flex flex-col justify-between text-xs text-gray-500 pr-2">
          <span>{maxValue}</span>
          <span>{Math.round((maxValue + minValue) / 2)}</span>
          <span>{minValue}</span>
        </div>

        {/* Chart area */}
        <div className="absolute left-14 right-0 top-0 bottom-6 border-l border-b border-gray-200">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
            {/* Grid lines */}
            <line x1="0" y1="50" x2="100" y2="50" stroke="#e5e7eb" strokeWidth="0.5" />

            {/* Line */}
            <path
              d={pathD}
              fill="none"
              stroke="#f43f5e"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />

            {/* Data points */}
            {data.values.map((value, index) => {
              const x = (index / (data.values.length - 1 || 1)) * 100;
              const y = 100 - ((value - minValue) / range) * 100;
              return (
                <circle
                  key={index}
                  cx={x}
                  cy={y}
                  r="2"
                  fill="#f43f5e"
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
          </svg>
        </div>

        {/* X-axis labels */}
        <div className="absolute left-14 right-0 bottom-0 flex justify-between text-xs text-gray-500">
          {data.labels.slice(0, 6).map((label, index) => (
            <span key={label} className="truncate max-w-[60px]">
              {label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Pie Chart (Simple CSS-based)
// ============================================================================

function PieChart({ data }: { data: QAChartData }) {
  const total = data.values.reduce((sum, v) => sum + v, 0) || 1;

  // Calculate segments
  let currentAngle = 0;
  const segments = data.values.map((value, index) => {
    const percentage = (value / total) * 100;
    const angle = (value / total) * 360;
    const segment = {
      label: data.labels[index],
      value,
      percentage,
      startAngle: currentAngle,
      endAngle: currentAngle + angle,
      color: COLORS[index % COLORS.length],
    };
    currentAngle += angle;
    return segment;
  });

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-4">{data.title}</h3>
      <div className="flex items-start gap-6">
        {/* Pie */}
        <div className="relative w-40 h-40 flex-shrink-0">
          <svg viewBox="0 0 100 100" className="w-full h-full transform -rotate-90">
            {segments.map((segment, index) => {
              if (segment.percentage < 0.5) return null;
              const largeArc = segment.endAngle - segment.startAngle > 180 ? 1 : 0;
              const startRad = (segment.startAngle * Math.PI) / 180;
              const endRad = (segment.endAngle * Math.PI) / 180;
              const x1 = 50 + 40 * Math.cos(startRad);
              const y1 = 50 + 40 * Math.sin(startRad);
              const x2 = 50 + 40 * Math.cos(endRad);
              const y2 = 50 + 40 * Math.sin(endRad);

              return (
                <path
                  key={index}
                  d={`M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`}
                  fill={segment.color}
                  stroke="white"
                  strokeWidth="1"
                />
              );
            })}
          </svg>
        </div>

        {/* Legend */}
        <div className="flex-1 space-y-2">
          {segments.slice(0, 8).map((segment, index) => (
            <div key={index} className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: segment.color }}
              />
              <span className="text-sm text-gray-600 truncate flex-1">
                {segment.label}
              </span>
              <span className="text-sm font-medium text-gray-900">
                {segment.percentage.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Stat Card
// ============================================================================

function StatCard({ data }: { data: QAChartData }) {
  const value = data.values[0] || 0;
  const label = data.labels[0] || '';

  return (
    <div className="bg-gradient-to-br from-rose-500 to-rose-600 rounded-xl p-6 text-white">
      <h3 className="text-sm font-medium text-rose-100 mb-2">{data.title}</h3>
      <p className="text-4xl font-bold">{value}</p>
      {label && <p className="text-sm text-rose-200 mt-1">{label}</p>}
    </div>
  );
}

'use client';

import React, { useState } from 'react';
import { createPortal } from 'react-dom';

// Audio quality analysis result from backend
export interface AudioQuality {
  overall_quality: 'good' | 'fair' | 'poor' | 'unknown';
  is_acceptable: boolean;
  issues: Array<{
    type: string;
    severity: 'warning' | 'critical';
    message: string;
  }>;
  metrics: {
    snr_db: number | null;
    rms_db: number | null;
    peak_db: number | null;
    clipping_ratio: number | null;
    silence_ratio: number | null;
    speech_detected: boolean | null;
    duration_seconds: number | null;
  };
  summary_message: string;
}

export interface BackgroundSession {
  submissionId: string;
  patientId: string;
  templateName: string;
  status: 'processing' | 'completed' | 'error';
  progress: number;
  progressMessage?: string;
  startedAt: Date;
  // Template context for restoring results later
  templateContext?: {
    templateCode: string;
    consultationTypeCode: string;
    doctorId: string;
  };
  result?: {
    transcript: string;
    coreData: any | null;
    additionalData: any | null;
    extractionId?: string;  // For emotion analysis lookup
    audioQuality?: AudioQuality;  // Audio quality analysis
    metrics: {
      stitchingTime?: number;
      transcriptionTime?: number;
      extractionTime?: number;
    };
  };
  error?: string;
}

interface BackgroundProcessingStatusProps {
  sessions: BackgroundSession[];
  onCancelSession?: (submissionId: string) => void;
}

export function BackgroundProcessingStatus({ sessions, onCancelSession }: BackgroundProcessingStatusProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const activeSessions = sessions.filter(s => s.status === 'processing');
  const activeCount = activeSessions.length;

  // Don't render if no active sessions
  if (!mounted || activeCount === 0) {
    return null;
  }

  // Calculate average progress
  const avgProgress = activeSessions.reduce((sum, s) => sum + s.progress, 0) / activeCount;

  const content = (
    <div className="fixed bottom-4 right-4 z-40">
      {/* Expanded view */}
      {isExpanded && (
        <div className="mb-2 bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden w-80">
          <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700">
              Active Extractions
            </span>
            <button
              onClick={() => setIsExpanded(false)}
              className="text-gray-400 hover:text-gray-600"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>

          <div className="max-h-64 overflow-y-auto">
            {activeSessions.map((session) => (
              <div
                key={session.submissionId}
                className="p-3 border-b border-gray-100 last:border-b-0"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {session.patientId}
                    </p>
                    <p className="text-xs text-gray-500 truncate">
                      {session.templateName}
                    </p>
                  </div>
                  <span className="text-xs font-medium text-blue-600">
                    {Math.round(session.progress)}%
                  </span>
                </div>

                {/* Progress bar */}
                <div className="mt-2 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all duration-300 ease-out"
                    style={{ width: `${session.progress}%` }}
                  />
                </div>

                {/* Progress message */}
                {session.progressMessage && (
                  <p className="mt-1 text-xs text-gray-500 truncate">
                    {session.progressMessage}
                  </p>
                )}

                {/* Time elapsed */}
                <p className="mt-1 text-xs text-gray-400">
                  Started {formatTimeAgo(session.startedAt)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Collapsed status bar */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-3 px-4 py-3 bg-white rounded-lg shadow-lg border border-gray-200 hover:bg-gray-50 transition-colors"
      >
        {/* Spinner */}
        <div className="relative">
          <svg
            className="w-5 h-5 text-blue-500 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        </div>

        {/* Text */}
        <div className="text-left">
          <p className="text-sm font-medium text-gray-900">
            Processing {activeCount} extraction{activeCount !== 1 ? 's' : ''}
          </p>
          <p className="text-xs text-gray-500">
            {Math.round(avgProgress)}% complete
          </p>
        </div>

        {/* Expand indicator */}
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </button>
    </div>
  );

  return createPortal(content, document.body);
}

function formatTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);

  if (seconds < 60) {
    return `${seconds}s ago`;
  }

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }

  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

'use client';

/**
 * QA Chat Message Component
 *
 * Renders a single chat message in the Q&A interface.
 * Supports user and assistant messages with custom content rendering.
 */

import React from 'react';
import type { QAMessage } from '@lib/types';

// ============================================================================
// Types
// ============================================================================

interface QAChatMessageProps {
  message: QAMessage;
  renderContent: () => React.ReactNode;
}

// ============================================================================
// Component
// ============================================================================

export default function QAChatMessage({
  message,
  renderContent,
}: QAChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-4 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
          isUser
            ? 'bg-gray-200 text-gray-600'
            : 'bg-rose-100 text-rose-600'
        }`}
      >
        {isUser ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
            />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
        )}
      </div>

      {/* Message Content */}
      <div
        className={`flex-1 max-w-3xl ${isUser ? 'text-right' : ''}`}
      >
        {/* Message Header */}
        <div
          className={`flex items-center gap-2 mb-1 ${
            isUser ? 'justify-end' : ''
          }`}
        >
          <span className="text-sm font-medium text-gray-700">
            {isUser ? 'You' : 'Q&A Assistant'}
          </span>
          <span className="text-xs text-gray-400">
            {formatTime(message.timestamp)}
          </span>
        </div>

        {/* Message Body */}
        <div
          className={`rounded-2xl px-4 py-3 inline-block max-w-full ${
            isUser
              ? 'bg-rose-600 text-white rounded-br-md'
              : 'bg-white border border-gray-200 text-gray-700 rounded-bl-md shadow-sm'
          }`}
        >
          {renderContent()}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
}

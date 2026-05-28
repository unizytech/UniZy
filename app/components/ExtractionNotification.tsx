'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';

export interface ExtractionNotificationData {
  id: string;
  submissionId: string;
  patientId: string;
  templateName: string;
  status: 'completed' | 'error';
  timestamp: Date;
  error?: string;
}

interface NotificationItemProps {
  notification: ExtractionNotificationData;
  onView: (submissionId: string) => void;
  onDismiss: (id: string) => void;
}

function NotificationItem({ notification, onView, onDismiss }: NotificationItemProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [progress, setProgress] = useState(100);
  const AUTO_DISMISS_MS = 10000; // 10 seconds

  useEffect(() => {
    if (isHovered) return;

    const startTime = Date.now();
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, 100 - (elapsed / AUTO_DISMISS_MS) * 100);
      setProgress(remaining);

      if (remaining <= 0) {
        onDismiss(notification.id);
      }
    }, 100);

    return () => clearInterval(interval);
  }, [isHovered, notification.id, onDismiss]);

  const isError = notification.status === 'error';

  return (
    <div
      className={`
        relative overflow-hidden rounded-lg shadow-lg border
        ${isError ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200'}
        transition-all duration-300 ease-out
      `}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Progress bar */}
      <div
        className={`absolute bottom-0 left-0 h-1 transition-all duration-100 ${isError ? 'bg-red-400' : 'bg-blue-500'}`}
        style={{ width: `${progress}%` }}
      />

      <div className="p-4">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${isError ? 'bg-red-100' : 'bg-green-100'}`}>
            {isError ? (
              <svg className="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className={`text-sm font-medium ${isError ? 'text-red-900' : 'text-gray-900'}`}>
              {isError ? 'Extraction Failed' : 'Extraction Complete'}
            </p>
            <p className="text-sm text-gray-600 truncate">
              Patient: {notification.patientId}
            </p>
            <p className="text-xs text-gray-500 truncate">
              {notification.templateName}
            </p>
            {isError && notification.error && (
              <p className="text-xs text-red-600 mt-1 line-clamp-2">
                {notification.error}
              </p>
            )}
          </div>

          {/* Dismiss button */}
          <button
            onClick={() => onDismiss(notification.id)}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>

        {/* Action button */}
        {!isError && (
          <button
            onClick={() => onView(notification.submissionId)}
            className="mt-3 w-full px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors"
          >
            View Results
          </button>
        )}
      </div>
    </div>
  );
}

interface ExtractionNotificationsProps {
  notifications: ExtractionNotificationData[];
  onView: (submissionId: string) => void;
  onDismiss: (id: string) => void;
}

export function ExtractionNotifications({ notifications, onView, onDismiss }: ExtractionNotificationsProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted || notifications.length === 0) {
    return null;
  }

  return createPortal(
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-3 w-80">
      {notifications.map((notification) => (
        <NotificationItem
          key={notification.id}
          notification={notification}
          onView={onView}
          onDismiss={onDismiss}
        />
      ))}
    </div>,
    document.body
  );
}

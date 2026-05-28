'use client';

import React, { useState, useRef, useEffect } from 'react';
import { getRecordingAudio, AudioDataResponse } from '../../lib/recordingsApi';

interface AudioPlayerModalProps {
  isOpen: boolean;
  onClose: () => void;
  submissionId: string;
  patientName?: string;
  consultationDate?: string;
  accessToken: string | null;
  audioType?: 'original' | 'processed';
}

export function AudioPlayerModal({
  isOpen,
  onClose,
  submissionId,
  patientName,
  consultationDate,
  accessToken,
  audioType,
}: AudioPlayerModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioData, setAudioData] = useState<AudioDataResponse | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  // Fetch audio data when modal opens
  useEffect(() => {
    if (isOpen && submissionId) {
      fetchAudio();
    }
    return () => {
      // Cleanup blob URL when modal closes
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
        setAudioUrl(null);
      }
    };
  }, [isOpen, submissionId, audioType]);

  const fetchAudio = async () => {
    setLoading(true);
    setError(null);
    setAudioData(null);

    try {
      const data = await getRecordingAudio(submissionId, accessToken, audioType || 'original');
      setAudioData(data);

      // Decode base64 to binary
      const binaryString = atob(data.audio_data);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Use simple mime type without codecs
      const simpleMimeType = data.mime_type.split(';')[0];
      const blob = new Blob([bytes], { type: simpleMimeType });
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);
    } catch (err: any) {
      setError(err.message || 'Failed to load audio');
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDuration = (seconds: number | null): string => {
    if (!seconds) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">
                {audioType === 'processed' ? 'Processed Audio (Silence Removed)' : 'Audio Playback'}
              </h2>
              {patientName && (
                <p className="text-blue-200 text-sm">{patientName}</p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-white hover:bg-white hover:bg-opacity-20 rounded-full p-2 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-8">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
              <p className="mt-4 text-gray-600">Loading audio...</p>
              <p className="text-sm text-gray-400 mt-1">This may take a moment for large files</p>
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
              <svg className="w-10 h-10 text-red-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-red-700 font-medium">{error}</p>
              <button
                onClick={fetchAudio}
                className="mt-3 px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 rounded-lg transition-colors text-sm"
              >
                Retry
              </button>
            </div>
          ) : audioUrl && audioData ? (
            <div className="space-y-4">
              {/* Audio Info */}
              <div className="bg-gray-50 rounded-lg p-4 grid grid-cols-3 gap-4 text-center">
                <div>
                  <div className="text-xs text-gray-500 uppercase tracking-wide">Format</div>
                  <div className="text-sm font-medium text-gray-900 mt-1">
                    {audioData.mime_type.split('/')[1]?.split(';')[0]?.toUpperCase() || 'Audio'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 uppercase tracking-wide">Size</div>
                  <div className="text-sm font-medium text-gray-900 mt-1">
                    {formatFileSize(audioData.size_bytes)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 uppercase tracking-wide">Duration</div>
                  <div className="text-sm font-medium text-gray-900 mt-1">
                    {formatDuration(audioData.duration_seconds)}
                  </div>
                </div>
              </div>

              {consultationDate && (
                <div className="text-center text-sm text-gray-500">
                  Recorded on {new Date(consultationDate).toLocaleString()}
                </div>
              )}

              {/* Audio Player */}
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-4 border border-blue-200">
                <audio
                  ref={audioRef}
                  controls
                  className="w-full"
                  src={audioUrl}
                  onError={(e) => {
                    console.error('Audio error:', e);
                    setError(`Audio playback error: ${(e.target as HTMLAudioElement).error?.message || 'Unknown error'}`);
                  }}
                >
                  Your browser does not support the audio element.
                </audio>
              </div>

              {/* Download Button */}
              <div className="flex justify-center">
                <a
                  href={audioUrl}
                  download={`recording-${submissionId.slice(0, 8)}.${audioData.mime_type.split('/')[1]?.split(';')[0] || 'webm'}`}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors text-sm"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download Audio
                </a>
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="bg-gray-50 px-6 py-4 border-t flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg transition-colors font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

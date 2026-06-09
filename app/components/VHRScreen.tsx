'use client';

import React, { useState, useEffect, useRef } from 'react';
import type { ExtractionResponse, ConsultationTypeCode, ProcessingMode, ActivatedTemplate } from "@lib/types";
import CounsellorSelector from './CounsellorSelector';
import AssistantSelector from './AssistantSelector';
import { handleApiError, getProcessingModes, getEmotionAnalysis, getTriageSuggestions, saveExtractionEdits, getExtractionTranslation, saveTranslationEdits, retryExtractionTranslation, type EmotionAnalysisData, type TriageSuggestionsResponse, type ExtractionTranslation } from "@lib/summaryApi";
import { getAssistantTemplates, type AssistantTemplate } from '@/services/assistantApi';
import { searchStudents, type StudentSearchResult } from "@lib/studentHistoryApi";
import { getCounsellorTemplates, type CounsellorTemplate } from "../services/counsellorApi";
import { RecordingManager } from '../services/recordingService';
import { API_CONFIG } from "@lib/config";
import ExtractionMergeScreen from './ExtractionMergeScreen';
import { generateOphthalHtml } from '@lib/ophthalHtmlFormatter';
import { BackgroundProcessingStatus, type BackgroundSession, type AudioQuality } from './BackgroundProcessingStatus';
import { ExtractionNotifications, type ExtractionNotificationData } from './ExtractionNotification';
import { EmotionAnalysisModal, type EmotionAnalysisData as EmotionModalData } from './EmotionAnalysisModal';
import { TriageSuggestionsModal, type TriageSuggestionsData } from './TriageSuggestionsModal';
import { InterventionsModal, type InterventionData } from './InterventionsModal';
import { RecordingHistoryModal, type ReprocessStartedInfo } from './RecordingHistoryModal';
import { AudioPlaybackByIdModal } from './AudioPlaybackByIdModal';
import ExtractionPhotosSection from './ExtractionPhotosSection';
// Supabase Realtime for WebSocket-based progress updates
import { supabase, isRealtimeAvailable, ProcessingProgress, ProcessingProgress as RealtimeProgress, ProcessingJobRow } from '@lib/supabase';
import type { RealtimeChannel, RealtimePostgresChangesPayload } from '@supabase/supabase-js';
import { useAuth } from '@lib/auth';
import { authGet, authFetch } from '@lib/apiClient';

export function VHRScreen() {
  // Auth
  const { getAccessToken, loading: authLoading } = useAuth();

  // Counsellor selection
  const [selectedCounsellorId, setSelectedCounsellorId] = useState<string | null>(null);

  // Assistant selection (optional)
  const [selectedAssistantId, setSelectedAssistantId] = useState<string | null>(null);

  // Template selection
  const [selectedTemplate, setSelectedTemplate] = useState<CounsellorTemplate | null>(null);

  // Counsellor templates
  const [activatedTemplates, setActivatedTemplates] = useState<CounsellorTemplate[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  // Student ID and list
  const [studentId, setStudentId] = useState('');
  const [studentsList, setStudentsList] = useState<StudentSearchResult[]>([]);
  const [loadingStudents, setLoadingStudents] = useState(false);

  // Continuation mode (whether this recording continues a prior consultation)
  const [isContinuation, setIsContinuation] = useState(false);

  // Reset continuation toggle when student changes
  useEffect(() => { setIsContinuation(false); }, [studentId]);

  // Processing mode (determines model selection)
  const [processingMode, setProcessingMode] = useState<string>('default');
  const [processingModes, setProcessingModes] = useState<ProcessingMode[]>([]);
  const [loadingProcessingModes, setLoadingProcessingModes] = useState(false);

  // Extraction mode (determines extraction strategy)
  const [extractionMode, setExtractionMode] = useState<'core' | 'additional' | 'full'>('full');

  // Input mode: 'mic' or 'upload'
  const [inputMode, setInputMode] = useState<'mic' | 'upload' | null>(null);

  // Chunked recording state
  const recordingManagerRef = useRef<RecordingManager | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [chunksUploaded, setChunksUploaded] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [processingProgress, setProcessingProgress] = useState<ProcessingProgress | null>(null);

  // Final transcript (from either recording method)
  const [transcript, setTranscript] = useState('');

  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Extraction state (progressive)
  const [coreExtractionData, setCoreExtractionData] = useState<ExtractionResponse | null>(null);
  const [additionalExtractionData, setAdditionalExtractionData] = useState<ExtractionResponse | null>(null);
  const [loadingCore, setLoadingCore] = useState(false);
  const [loadingAdditional, setLoadingAdditional] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Results view mode (JSON vs HTML for ophthal/opto templates)
  const [resultsViewMode, setResultsViewMode] = useState<'json' | 'html'>('json');

  // Merge screen state
  const [showMergeScreen, setShowMergeScreen] = useState(false);

  // Audio playback modal state
  const [showAudioPlaybackModal, setShowAudioPlaybackModal] = useState(false);

  // Background processing sessions (for async processing)
  const [backgroundSessions, setBackgroundSessions] = useState<BackgroundSession[]>([]);
  const [notifications, setNotifications] = useState<ExtractionNotificationData[]>([]);

  // Stacked results history (for viewing multiple completed extractions)
  interface ViewedResult {
    submissionId: string;
    patientId: string;
    templateName: string;
    transcript: string;
    coreData: Record<string, unknown> | null;
    metrics: {
      stitchingTime?: number;
      transcriptionTime?: number;
      extractionTime?: number;
    };
    audioQuality?: AudioQuality;  // Audio quality analysis
    timestamp: Date;
    extractionId?: string;  // For emotion analysis lookup
    // Template context for restoring results
    templateContext?: {
      templateCode: string;
      consultationTypeCode: string;
      doctorId: string;
    };
  }
  const [viewedResults, setViewedResults] = useState<ViewedResult[]>([]);

  // Current extraction ID (for emotion analysis button)
  const [currentExtractionId, setCurrentExtractionId] = useState<string | null>(null);

  // Emotion analysis modal state
  const [showEmotionModal, setShowEmotionModal] = useState(false);
  const [emotionData, setEmotionData] = useState<EmotionModalData>({
    loading: false
  });

  // Triage suggestions modal state
  const [showTriageModal, setShowTriageModal] = useState(false);
  const [triageData, setTriageData] = useState<TriageSuggestionsData>({
    loading: false
  });

  // Interventions modal state
  const [showInterventionsModal, setShowInterventionsModal] = useState(false);
  const [interventionsData, setInterventionsData] = useState<{
    interventions: InterventionData[];
    loading: boolean;
    error?: string;
    insightsEnabled?: boolean;
  }>({ interventions: [], loading: false });

  // Recording history modal state
  const [showRecordingHistoryModal, setShowRecordingHistoryModal] = useState(false);
  const [recordingHistorySource, setRecordingHistorySource] = useState<'doctor' | 'nurse'>('doctor');

  // EHR Payload preview modal state
  const [showPayloadModal, setShowPayloadModal] = useState(false);
  const [payloadData, setPayloadData] = useState<{
    loading: boolean;
    error?: string;
    payload?: Record<string, unknown>;
    payloadType?: 'raster' | 'aosta' | 'neopaed' | 'kg';
    templateCode?: string;
  }>({ loading: false });

  // Realtime Extraction Response modal state (auto-triggered when extraction result is received)
  const [showRealtimeModal, setShowRealtimeModal] = useState(false);
  const [realtimeExtractionResult, setRealtimeExtractionResult] = useState<{
    submissionId: string;
    response: Record<string, unknown>;
    receivedAt: Date;
  } | null>(null);
  const realtimeExtractionChannelsRef = useRef<Map<string, RealtimeChannel>>(new Map());

  // Edit mode state
  const [isEditMode, setIsEditMode] = useState(false);

  // JSON copy feedback state
  const [jsonCopied, setJsonCopied] = useState(false);
  const [editedCoreData, setEditedCoreData] = useState<Record<string, unknown> | null>(null);
  const [editedAdditionalData, setEditedAdditionalData] = useState<Record<string, unknown> | null>(null);
  const [isSavingEdits, setIsSavingEdits] = useState(false);
  const [editSaveError, setEditSaveError] = useState<string | null>(null);
  const [editSaveSuccess, setEditSaveSuccess] = useState<string | null>(null);
  const [editWarnings, setEditWarnings] = useState<Array<{ category: string; severity: 'info' | 'warning' | 'error'; message: string }>>([]);

  // Realtime channels for WebSocket-based progress updates
  const realtimeChannelsRef = useRef<Map<string, RealtimeChannel>>(new Map());

  // Timing metrics
  const [stitchingTime, setStitchingTime] = useState<number | null>(null);
  const [transcriptionTime, setTranscriptionTime] = useState<number | null>(null);
  const [coreExtractionTime, setCoreExtractionTime] = useState<number | null>(null);
  const [additionalExtractionTime, setAdditionalExtractionTime] = useState<number | null>(null);

  // Audio quality analysis
  const [currentAudioQuality, setCurrentAudioQuality] = useState<AudioQuality | null>(null);

  // Translation state
  const [translationData, setTranslationData] = useState<ExtractionTranslation | null>(null);
  const [translationViewActive, setTranslationViewActive] = useState(false);
  const [translationLoading, setTranslationLoading] = useState(false);
  const [editedTranslationData, setEditedTranslationData] = useState<Record<string, unknown> | null>(null);
  const [translationOutdated, setTranslationOutdated] = useState(false);
  const [retranslating, setRetranslating] = useState(false);
  const [counsellorTranslationLanguage, setCounsellorTranslationLanguage] = useState<string | null>(null);

  // Cache refresh state
  const [isRefreshingCache, setIsRefreshingCache] = useState(false);

  // Recording duration timer
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isRecording && !isPaused && recordingManagerRef.current) {
      interval = setInterval(() => {
        if (recordingManagerRef.current) {
          setRecordingDuration(recordingManagerRef.current.getRecordingDuration());
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isRecording, isPaused]);

  // Load processing modes when auth is ready (only once)
  const [processingModesLoaded, setProcessingModesLoaded] = useState(false);
  useEffect(() => {
    if (!authLoading && !processingModesLoaded) {
      const token = getAccessToken();
      if (token) {
        setProcessingModesLoaded(true);
        loadProcessingModesFromDB();
      }
    }
  }, [authLoading, getAccessToken, processingModesLoaded]);

  // Load activated templates when counsellor or assistant is selected
  // Assistant templates take priority over counsellor templates
  useEffect(() => {
    if (selectedAssistantId) {
      loadAssistantActivatedTemplates();
    } else if (selectedCounsellorId) {
      loadActivatedTemplates();
    } else {
      setActivatedTemplates([]);
      setSelectedTemplate(null);
    }
  }, [selectedCounsellorId, selectedAssistantId]);

  // Load students list when counsellor is selected
  useEffect(() => {
    if (selectedCounsellorId) {
      loadStudentsList();
    } else {
      setStudentsList([]);
      setStudentId('');
    }
  }, [selectedCounsellorId]);

  const loadStudentsList = async () => {
    if (!selectedCounsellorId) return;

    try {
      setLoadingStudents(true);
      const accessToken = getAccessToken();
      // Use searchStudents with empty query to get all students for this counsellor
      // For Counsellor SKS, this automatically syncs with Neopaed school system
      const response = await searchStudents('', selectedCounsellorId, 1, 100, accessToken);
      console.log('[DEBUG] Loaded students:', response.total_count);
      setStudentsList(response.students);
      // Auto-select first student if available
      if (response.students.length > 0) {
        setStudentId(response.students[0].student_id);
      }
    } catch (err) {
      console.error('Failed to load students list:', err);
      setStudentsList([]);
    } finally {
      setLoadingStudents(false);
    }
  };

  const loadProcessingModesFromDB = async () => {
    try {
      setLoadingProcessingModes(true);
      const accessToken = getAccessToken();
      const response = await getProcessingModes(accessToken);
      setProcessingModes(response.processing_modes);

      // Auto-select default mode if available
      const defaultMode = response.processing_modes.find(m => m.mode_code === 'default');
      if (defaultMode) {
        setProcessingMode(defaultMode.mode_code);
      } else if (response.processing_modes.length > 0) {
        setProcessingMode(response.processing_modes[0].mode_code);
      }
    } catch (err) {
      console.error('Failed to load processing modes:', err);
    } finally {
      setLoadingProcessingModes(false);
    }
  };

  const openHtmlInNewWindow = () => {
    const merged: Record<string, any> = {
      ...(coreExtractionData?.insights || {}),
      ...(additionalExtractionData?.insights || {}),
    };

    // 🔍 DEBUG: Log the actual data structure being passed to HTML formatter
    console.log('[HTML_FORMATTER_DEBUG] ========== DATA STRUCTURE ==========');
    console.log('[HTML_FORMATTER_DEBUG] Merged data keys:', Object.keys(merged));
    console.log('[HTML_FORMATTER_DEBUG] Full merged data:', merged);
    console.log('[HTML_FORMATTER_DEBUG] Template type:', selectedTemplate?.consultation_type_code);
    console.log('[HTML_FORMATTER_DEBUG] Is ophthal/opto template:', isOphthalOrOptoTemplate(selectedTemplate));
    console.log('[HTML_FORMATTER_DEBUG] ===================================');

    // Use specialized ophthalmology HTML formatter for ophthalmology/optometry templates
    const html = isOphthalOrOptoTemplate(selectedTemplate)
      ? generateOphthalHtml(merged, selectedTemplate)
      : generateHtmlFromData(merged, selectedTemplate);

    const newWindow = window.open('', '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');

    if (newWindow) {
      newWindow.document.write(html);
      newWindow.document.close();
    } else {
      alert('Please allow pop-ups for this site to view HTML in a new window');
    }
  };

  const loadActivatedTemplates = async () => {
    if (!selectedCounsellorId) return;

    try {
      setLoadingTemplates(true);
      console.log('[DEBUG] Loading templates for counsellor:', selectedCounsellorId);
      const accessToken = getAccessToken();
      const templates = await getCounsellorTemplates(selectedCounsellorId, accessToken);
      console.log('[DEBUG] Received templates:', templates);
      console.log('[DEBUG] Template count:', templates.length);
      setActivatedTemplates(templates);
      // Auto-select first template if available
      if (templates.length > 0) {
        setSelectedTemplate(templates[0]);
        console.log('[DEBUG] Auto-selected template:', templates[0].template_name);
      } else {
        console.warn('[DEBUG] No templates found for counsellor:', selectedCounsellorId);
      }
    } catch (err) {
      console.error('Failed to load activated templates:', err);
      setActivatedTemplates([]);
      setSelectedTemplate(null);
    } finally {
      setLoadingTemplates(false);
    }
  };

  // Load assistant's accessible templates
  const loadAssistantActivatedTemplates = async () => {
    if (!selectedAssistantId) return;

    try {
      setLoadingTemplates(true);
      console.log('[DEBUG] Loading templates for assistant:', selectedAssistantId);
      const accessToken = getAccessToken();
      const assistantTemplates = await getAssistantTemplates(selectedAssistantId, accessToken);
      console.log('[DEBUG] Received assistant templates:', assistantTemplates);
      console.log('[DEBUG] Assistant template count:', assistantTemplates.length);

      // Convert AssistantTemplate to CounsellorTemplate format for UI compatibility
      // Only include templates with 'use' access level
      // Deduplicate by template_id to avoid React key warnings
      const seenTemplateIds = new Set<string>();
      const convertedTemplates: CounsellorTemplate[] = assistantTemplates
        .filter(nt => nt.is_active)
        .filter(nt => {
          if (seenTemplateIds.has(nt.template_id)) {
            return false;
          }
          seenTemplateIds.add(nt.template_id);
          return true;
        })
        .map(nt => ({
          id: nt.template_id,
          template_code: nt.template_code,
          template_name: nt.template_name || nt.template_code,
          consultation_type_id: '',
          consultation_type_code: nt.consultation_type_code || '',
          consultation_type_name: nt.consultation_type_name || '',
          description: nt.description || '',
          counsellor_id: selectedCounsellorId || '',  // Use counsellor if selected
          is_active: nt.is_active,
          is_default: false,
          created_at: nt.created_at,
          updated_at: nt.created_at,
        }));

      setActivatedTemplates(convertedTemplates);
      // Auto-select first template if available
      if (convertedTemplates.length > 0) {
        setSelectedTemplate(convertedTemplates[0]);
        console.log('[DEBUG] Auto-selected assistant template:', convertedTemplates[0].template_name);
      } else {
        console.warn('[DEBUG] No accessible templates found for assistant:', selectedAssistantId);
        setSelectedTemplate(null);
      }
    } catch (err) {
      console.error('Failed to load assistant templates:', err);
      setActivatedTemplates([]);
      setSelectedTemplate(null);
    } finally {
      setLoadingTemplates(false);
    }
  };

  // ============================================================================
  // Background Session Management (localStorage persistence)
  // ============================================================================

  const STORAGE_KEY = 'vhr_background_sessions';
  const MAX_SESSION_AGE_HOURS = 24;

  // Save background sessions to localStorage
  const saveSessionsToStorage = (sessions: BackgroundSession[]) => {
    try {
      const toStore = sessions.map(s => ({
        submissionId: s.submissionId,
        patientId: s.patientId,
        templateName: s.templateName,
        status: s.status,
        progress: s.progress,
        startedAt: s.startedAt.toISOString(),
        templateContext: s.templateContext,
      }));
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore));
    } catch (err) {
      console.error('[VHR] Failed to save sessions to localStorage:', err);
    }
  };

  // Load and recover background sessions on mount
  useEffect(() => {
    const recoverSessions = async () => {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) return;

        const parsed = JSON.parse(stored) as Array<{
          submissionId: string;
          patientId: string;
          templateName: string;
          status: string;
          progress: number;
          startedAt: string;
          templateContext?: {
            templateCode: string;
            consultationTypeCode: string;
            doctorId: string;
          };
        }>;

        // Filter out stale sessions (older than 24 hours)
        const now = Date.now();
        const validSessions = parsed.filter(s => {
          const age = now - new Date(s.startedAt).getTime();
          return age < MAX_SESSION_AGE_HOURS * 60 * 60 * 1000;
        });

        // Check status for each session and reconnect if still processing
        for (const session of validSessions) {
          if (session.status === 'processing') {
            try {
              // Check status via API
              const response = await authGet(
                `/api/v1/option1/recording/status/${session.submissionId}`,
                getAccessToken()
              );

              if (response.ok) {
                const data = await response.json();

                if (data.status === 'COMPLETED') {
                  // Already completed - show notification
                  addNotification({
                    submissionId: session.submissionId,
                    patientId: session.patientId,
                    templateName: session.templateName,
                    status: 'completed',
                  });
                } else if (data.status === 'ERROR') {
                  // Error - show error notification
                  addNotification({
                    submissionId: session.submissionId,
                    patientId: session.patientId,
                    templateName: session.templateName,
                    status: 'error',
                    error: data.error_message || 'Processing failed',
                  });
                } else {
                  // Still processing - reconnect Realtime listener
                  const recoveredSession: BackgroundSession = {
                    submissionId: session.submissionId,
                    patientId: session.patientId,
                    templateName: session.templateName,
                    status: 'processing',
                    progress: data.progress || 0,
                    progressMessage: data.message,
                    startedAt: new Date(session.startedAt),
                    templateContext: session.templateContext,
                  };

                  setBackgroundSessions(prev => [...prev, recoveredSession]);
                  startBackgroundProgressListener(recoveredSession);
                }
              }
            } catch (err) {
              console.error('[VHR] Failed to check session status:', session.submissionId, err);
            }
          }
        }

        // Update storage with cleaned sessions
        saveSessionsToStorage(validSessions.map(s => ({
          ...s,
          startedAt: new Date(s.startedAt),
        } as BackgroundSession)));
      } catch (err) {
        console.error('[VHR] Failed to recover sessions from localStorage:', err);
      }
    };

    recoverSessions();
  }, []);

  // Save to localStorage whenever backgroundSessions changes
  useEffect(() => {
    saveSessionsToStorage(backgroundSessions);
  }, [backgroundSessions]);

  // Cleanup Realtime channels on unmount
  useEffect(() => {
    return () => {
      // Unsubscribe from all processing_jobs Realtime channels
      realtimeChannelsRef.current.forEach((channel, submissionId) => {
        console.log('[Realtime] Cleaning up processing channel for:', submissionId);
        channel.unsubscribe();
      });
      realtimeChannelsRef.current.clear();

      // Unsubscribe from all realtime_extraction_responses channels
      cleanupAllRealtimeExtractionSubscriptions();
    };
  }, []);

  // Add a new background session and start progress listener
  const addBackgroundSession = (session: BackgroundSession) => {
    setBackgroundSessions(prev => [...prev, session]);
    startBackgroundProgressListener(session);
    // Also start realtime extraction response subscription (for EHR client simulation)
    startRealtimeExtractionSubscription(session.submissionId);
  };

  // Start progress listener for a background session
  // Uses Supabase Realtime (WebSocket) - no polling!
  const startBackgroundProgressListener = (session: BackgroundSession, retryCount = 0) => {
    const MAX_RETRIES = 3;
    const RETRY_DELAY_MS = 2000;

    // Check if Supabase Realtime is available
    if (!isRealtimeAvailable() || !supabase) {
      console.error('[Realtime] Supabase Realtime not configured. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY to .env');
      setBackgroundSessions(prev =>
        prev.map(s =>
          s.submissionId === session.submissionId
            ? { ...s, status: 'error' as const, error: 'Realtime not configured. Check environment variables.' }
            : s
        )
      );
      return;
    }

    console.log(`[Realtime] Starting WebSocket subscription for: ${session.submissionId} (attempt ${retryCount + 1}/${MAX_RETRIES + 1})`);

    const channelName = `processing:${session.submissionId}`;
    const channel = supabase
      .channel(channelName)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'processing_jobs',
          filter: `submission_id=eq.${session.submissionId}`,
        },
        (payload: RealtimePostgresChangesPayload<ProcessingJobRow>) => {
          const row = payload.new as ProcessingJobRow;

          // Parse progress_json if available
          // Handle both: 1) JSONB object (new), 2) double-encoded string (old data)
          let progressData: RealtimeProgress | null = null;
          if (row.progress_json) {
            try {
              // If it's already an object (JSONB returns object directly), use it
              if (typeof row.progress_json === 'object') {
                progressData = row.progress_json as RealtimeProgress;
              } else {
                // It's a string - parse it
                let parsed = JSON.parse(row.progress_json);
                // Handle double-encoded case (old data)
                if (typeof parsed === 'string') {
                  parsed = JSON.parse(parsed);
                }
                progressData = parsed;
              }
            } catch {
              // Fallback to legacy columns
              console.warn('[Realtime] Failed to parse progress_json:', row.progress_json);
            }
          }

          // Use progress_json or fallback to legacy columns
          const status = progressData?.status || row.status;
          const progress = progressData?.progress ?? row.progress_percentage;
          const message = progressData?.message || row.progress_message || `Processing: ${status}`;

          // Update session progress
          setBackgroundSessions(prev =>
            prev.map(s =>
              s.submissionId === session.submissionId
                ? { ...s, progress, progressMessage: message }
                : s
            )
          );

          // Handle completion
          if (status === 'COMPLETED') {
            // Map snake_case metrics from backend to camelCase for frontend
            const backendMetrics = progressData?.metrics || {};
            const mappedMetrics = {
              stitchingTime: backendMetrics.stitching_time,
              transcriptionTime: backendMetrics.transcription_time,
              extractionTime: backendMetrics.extraction_time,
            };

            setBackgroundSessions(prev =>
              prev.map(s =>
                s.submissionId === session.submissionId
                  ? {
                      ...s,
                      status: 'completed' as const,
                      progress: 100,
                      result: {
                        transcript: progressData?.transcript || '',
                        coreData: progressData?.insights || null,
                        additionalData: null,
                        extractionId: progressData?.extraction_id,  // Capture extraction_id for emotion analysis
                        audioQuality: progressData?.audio_quality || undefined,  // Audio quality analysis
                        metrics: mappedMetrics,
                      },
                    }
                  : s
              )
            );

            // Set current extraction ID for emotion analysis button
            if (progressData?.extraction_id) {
              setCurrentExtractionId(progressData.extraction_id);
            }

            addNotification({
              submissionId: session.submissionId,
              patientId: session.patientId,
              templateName: session.templateName,
              status: 'completed',
            });

            // Cleanup channel
            channel.unsubscribe();
            realtimeChannelsRef.current.delete(session.submissionId);
          }

          // Handle error
          if (status === 'ERROR') {
            const errorMessage = progressData?.error || row.error_message || 'Processing failed';

            setBackgroundSessions(prev =>
              prev.map(s =>
                s.submissionId === session.submissionId
                  ? { ...s, status: 'error' as const, error: errorMessage }
                  : s
              )
            );

            addNotification({
              submissionId: session.submissionId,
              patientId: session.patientId,
              templateName: session.templateName,
              status: 'error',
              error: errorMessage,
            });

            // Cleanup channel
            channel.unsubscribe();
            realtimeChannelsRef.current.delete(session.submissionId);
          }
        }
      )
      .subscribe(async (status: string) => {
        if (status === 'SUBSCRIBED') {
          console.log('[Realtime] Subscribed to processing updates');

          // Fetch current job status to catch up with any progress made before subscription was ready
          try {
            const response = await authGet(
              `/api/v1/option1/recording/status/${session.submissionId}`,
              getAccessToken()
            );
            if (response.ok) {
              const data = await response.json();
              console.log('[Realtime] Initial job status:', data.status, data.progress);

              // Update session with current progress
              const progress = data.progress || 0;
              const message = data.message || data.status;

              setBackgroundSessions(prev =>
                prev.map(s =>
                  s.submissionId === session.submissionId
                    ? { ...s, progress, progressMessage: message }
                    : s
                )
              );

              // If already completed, handle it
              if (data.status === 'COMPLETED' && data.insights) {
                console.log('[Realtime] Job already completed, fetching results');
                setBackgroundSessions(prev =>
                  prev.map(s =>
                    s.submissionId === session.submissionId
                      ? {
                          ...s,
                          status: 'completed' as const,
                          progress: 100,
                          progressMessage: 'Completed',
                          result: {
                            transcript: data.transcript || '',
                            coreData: data.insights,
                            additionalData: null,
                            extractionId: data.extraction_id,
                            metrics: {
                              stitchingTime: data.stitching_time_seconds,
                              transcriptionTime: data.transcription_time_seconds,
                              extractionTime: data.extraction_time_seconds,
                            },
                          },
                        }
                      : s
                  )
                );

                addNotification({
                  submissionId: session.submissionId,
                  patientId: session.patientId,
                  templateName: session.templateName,
                  status: 'completed',
                });

                // Cleanup channel
                channel.unsubscribe();
                realtimeChannelsRef.current.delete(session.submissionId);
              } else if (data.status === 'ERROR') {
                setBackgroundSessions(prev =>
                  prev.map(s =>
                    s.submissionId === session.submissionId
                      ? { ...s, status: 'error' as const, error: data.message || 'Processing failed' }
                      : s
                  )
                );

                addNotification({
                  submissionId: session.submissionId,
                  patientId: session.patientId,
                  templateName: session.templateName,
                  status: 'error',
                  error: data.message || 'Processing failed',
                });

                channel.unsubscribe();
                realtimeChannelsRef.current.delete(session.submissionId);
              }
            }
          } catch (err) {
            console.warn('[Realtime] Failed to fetch initial job status:', err);
            // Continue with subscription - we'll get updates via Realtime
          }
        } else if (status === 'TIMED_OUT') {
          console.warn(`[Realtime] Subscription timed out (attempt ${retryCount + 1}/${MAX_RETRIES + 1})`);
          // Cleanup failed channel
          channel.unsubscribe();
          realtimeChannelsRef.current.delete(session.submissionId);

          // Retry if we haven't exceeded max retries
          if (retryCount < MAX_RETRIES) {
            console.log(`[Realtime] Retrying in ${RETRY_DELAY_MS}ms...`);
            setTimeout(() => {
              startBackgroundProgressListener(session, retryCount + 1);
            }, RETRY_DELAY_MS);
          } else {
            console.error('[Realtime] Max retries exceeded, falling back to polling');
            // Don't mark as error - the processing continues, we just won't get live updates
            // The user can still see results when they refresh or check history
            setBackgroundSessions(prev =>
              prev.map(s =>
                s.submissionId === session.submissionId
                  ? { ...s, progressMessage: 'Live updates unavailable. Processing continues in background.' }
                  : s
              )
            );
          }
        } else if (status === 'CHANNEL_ERROR') {
          console.error('[Realtime] Channel error:', status);
          setBackgroundSessions(prev =>
            prev.map(s =>
              s.submissionId === session.submissionId
                ? { ...s, status: 'error' as const, error: `Realtime subscription failed: ${status}` }
                : s
            )
          );
        }
      });

    realtimeChannelsRef.current.set(session.submissionId, channel);
  };

  // Subscribe to realtime_extraction_responses table for EHR client simulation
  // Auto-subscribes when background session starts, auto-shows modal when result received
  const startRealtimeExtractionSubscription = (submissionId: string) => {
    if (!isRealtimeAvailable() || !supabase) {
      console.warn('[RealtimeExtraction] Supabase Realtime not configured');
      return;
    }

    // Don't create duplicate subscription
    if (realtimeExtractionChannelsRef.current.has(submissionId)) {
      console.log(`[RealtimeExtraction] Already subscribed to: ${submissionId}`);
      return;
    }

    console.log(`[RealtimeExtraction] Starting subscription for submission_id: ${submissionId}`);

    const channelName = `extraction-response:${submissionId}`;
    const channel = supabase
      .channel(channelName)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'realtime_extraction_responses',
          filter: `submission_id=eq.${submissionId}`,
        },
        (payload) => {
          console.log('[RealtimeExtraction] Received INSERT event:', payload);
          const row = payload.new as Record<string, unknown>;

          // Set the result and auto-show modal
          setRealtimeExtractionResult({
            submissionId,
            response: row,
            receivedAt: new Date()
          });
          setShowRealtimeModal(true);

          // Cleanup this subscription after receiving
          setTimeout(() => {
            channel.unsubscribe();
            realtimeExtractionChannelsRef.current.delete(submissionId);
            console.log(`[RealtimeExtraction] Cleaned up subscription for: ${submissionId}`);
          }, 1000);
        }
      )
      .subscribe(async (status: string) => {
        console.log(`[RealtimeExtraction] Subscription status for ${submissionId}: ${status}`);
        if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          console.warn(`[RealtimeExtraction] Subscription failed for ${submissionId}: ${status}`);
          realtimeExtractionChannelsRef.current.delete(submissionId);
        } else if (status === 'SUBSCRIBED') {
          // Check for existing record (in case INSERT happened before subscription was ready)
          console.log(`[RealtimeExtraction] SUBSCRIBED - Checking for existing record for ${submissionId}`);

          if (!supabase) {
            console.error('[RealtimeExtraction] Supabase client is null in callback!');
            return;
          }

          try {
            const { data, error } = await supabase
              .from('realtime_extraction_responses')
              .select('*')
              .eq('submission_id', submissionId)
              .maybeSingle();

            console.log(`[RealtimeExtraction] Query result - data:`, data, 'error:', error);

            if (error) {
              console.error(`[RealtimeExtraction] Error checking existing record: ${error.message}`, error);
            } else if (data) {
              console.log('[RealtimeExtraction] Found existing record, showing modal:', data);
              setRealtimeExtractionResult({
                submissionId,
                response: data as Record<string, unknown>,
                receivedAt: new Date()
              });
              setShowRealtimeModal(true);
              // Cleanup subscription since we already have the result
              setTimeout(() => {
                channel.unsubscribe();
                realtimeExtractionChannelsRef.current.delete(submissionId);
                console.log(`[RealtimeExtraction] Cleaned up subscription for: ${submissionId}`);
              }, 1000);
            } else {
              console.log(`[RealtimeExtraction] No existing record found for ${submissionId}, waiting for INSERT event...`);
            }
          } catch (err) {
            console.error('[RealtimeExtraction] Exception during query:', err);
          }
        }
      });

    realtimeExtractionChannelsRef.current.set(submissionId, channel);
  };

  // Cleanup all realtime extraction subscriptions (called on unmount)
  const cleanupAllRealtimeExtractionSubscriptions = () => {
    realtimeExtractionChannelsRef.current.forEach((channel, submissionId) => {
      console.log(`[RealtimeExtraction] Cleaning up channel for: ${submissionId}`);
      channel.unsubscribe();
    });
    realtimeExtractionChannelsRef.current.clear();
  };

  // Handle closing the realtime result modal
  const handleCloseRealtimeModal = () => {
    setShowRealtimeModal(false);
    setRealtimeExtractionResult(null);
  };

  // Add notification
  const addNotification = (data: Omit<ExtractionNotificationData, 'id' | 'timestamp'>) => {
    const notification: ExtractionNotificationData = {
      ...data,
      id: `${data.submissionId}-${Date.now()}`,
      timestamp: new Date(),
    };
    setNotifications(prev => [notification, ...prev]);
  };

  // Refresh all caches
  const [cacheRefreshMessage, setCacheRefreshMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleRefreshCache = async () => {
    setIsRefreshingCache(true);
    setCacheRefreshMessage(null);
    try {
      const token = await getAccessToken();
      const response = await authFetch(
        `${API_CONFIG.backendUrl}/api/v1/summary/admin/cache/refresh`,
        token,  // auth token (2nd param)
        { method: 'POST' }  // options (3rd param)
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to refresh cache (${response.status})`);
      }

      const result = await response.json();
      console.log('[CACHE_REFRESH]', result);
      setCacheRefreshMessage({ type: 'success', text: result.message || 'All caches refreshed' });

      // Auto-hide after 3 seconds
      setTimeout(() => setCacheRefreshMessage(null), 3000);
    } catch (err) {
      console.error('[CACHE_REFRESH] Error:', err);
      const errorMessage = err instanceof Error ? err.message : 'Failed to refresh cache';
      setCacheRefreshMessage({ type: 'error', text: errorMessage });

      // Auto-hide after 5 seconds
      setTimeout(() => setCacheRefreshMessage(null), 5000);
    } finally {
      setIsRefreshingCache(false);
    }
  };

  // Dismiss notification
  const handleDismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  // View results from notification
  const handleViewResults = (submissionId: string) => {
    const session = backgroundSessions.find(s => s.submissionId === submissionId);
    if (session?.result) {
      // Add to viewed results stack (for multiple parallel results)
      const viewedResult: ViewedResult = {
        submissionId: session.submissionId,
        patientId: session.patientId,
        templateName: session.templateName,
        transcript: session.result.transcript || '',
        coreData: session.result.coreData as Record<string, unknown> | null,
        metrics: {
          stitchingTime: session.result.metrics.stitchingTime,
          transcriptionTime: session.result.metrics.transcriptionTime,
          extractionTime: session.result.metrics.extractionTime,
        },
        audioQuality: session.result.audioQuality,
        timestamp: new Date(),
        templateContext: session.templateContext,
      };

      // Add to front of stack (most recent first)
      setViewedResults(prev => [viewedResult, ...prev]);

      // Also load into main display for immediate view
      if (session.result.coreData) {
        splitFullExtractionResults(
          session.result.coreData,
          {
            consultation_type: session.templateName,
            template_code: session.templateContext?.templateCode || null,
          },
          session.result.metrics.extractionTime || null
        );
      }
      setTranscript(session.result.transcript || '');
      setStitchingTime(session.result.metrics.stitchingTime || null);
      setTranscriptionTime(session.result.metrics.transcriptionTime || null);
      setCurrentAudioQuality(session.result.audioQuality || null);
    }

    // Dismiss the notification
    setNotifications(prev => prev.filter(n => n.submissionId !== submissionId));

    // Remove from background sessions (mark as viewed)
    setBackgroundSessions(prev => prev.filter(s => s.submissionId !== submissionId));
  };

  // Remove a result from the viewed stack
  const handleRemoveViewedResult = (submissionId: string) => {
    setViewedResults(prev => prev.filter(r => r.submissionId !== submissionId));
  };

  // Load a viewed result into main display
  const handleLoadViewedResult = (submissionId: string) => {
    const result = viewedResults.find(r => r.submissionId === submissionId);
    if (result) {
      // First, try to restore the template context if available
      if (result.templateContext) {
        // Find the matching template from activatedTemplates
        const matchingTemplate = activatedTemplates.find(
          t => t.template_code === result.templateContext?.templateCode
        );

        if (matchingTemplate) {
          // Select the template so splitFullExtractionResults can use it
          setSelectedTemplate(matchingTemplate);

          // Also restore the counsellor ID if different
          if (result.templateContext.doctorId && result.templateContext.doctorId !== selectedCounsellorId) {
            setSelectedCounsellorId(result.templateContext.doctorId);
          }
        }
      }

      // Load the extraction data
      if (result.coreData) {
        // Use a small delay to ensure template state is updated before splitting
        setTimeout(() => {
          splitFullExtractionResults(
            result.coreData!,
            {
              consultation_type: result.templateName,
              template_code: result.templateContext?.templateCode || null,
            },
            result.metrics.extractionTime || null
          );
        }, 0);
      } else {
        // No coreData, just show fallback
        setCoreExtractionData({
          success: true,
          insights: {},
          metadata: {
            correlation_id: null,
            submission_id: null,
            extraction_id: 'restored',
            counsellor_id: result.templateContext?.doctorId || null,
            student_id: null,
            template_code: result.templateContext?.consultationTypeCode || result.templateName || null,
            mode: 'full',
            segment_count: 0,
            processing_mode: null,
            timestamp: new Date().toISOString(),
          }
        });
      }

      setTranscript(result.transcript || '');
      setStitchingTime(result.metrics.stitchingTime || null);
      setTranscriptionTime(result.metrics.transcriptionTime || null);
      setCurrentAudioQuality(result.audioQuality || null);

      // Update current extraction ID for emotion analysis
      if (result.extractionId) {
        setCurrentExtractionId(result.extractionId);
      }
    }
  };

  // Open emotion analysis modal
  const handleOpenEmotionModal = async (extractionId: string) => {
    setShowEmotionModal(true);
    setEmotionData({ loading: true });

    try {
      const data = await getEmotionAnalysis(extractionId, getAccessToken());
      setEmotionData({
        // Unified emotions with source field
        unifiedEmotions: data.unified_emotions?.map(seg => ({
          segment_code: seg.segment_code,
          segment_name: seg.segment_name,
          source: seg.source,
          segment_value: seg.segment_value,
          created_at: seg.created_at,
        })),
        congruenceSummary: data.congruence_summary ? {
          overall_congruence: data.congruence_summary.overall_congruence,
          congruence_score: data.congruence_summary.congruence_score,
          has_mismatches: data.congruence_summary.has_mismatches,
        } : null,
        loading: false,
        // Started flags (to detect mode - if not started, don't show "in progress")
        emotionExtractionStarted: data.emotion_extraction_started,
        audioEmotionExtractionStarted: data.audio_emotion_extraction_started,
        congruenceAnalysisStarted: data.congruence_analysis_started,
        // Completed flags
        emotionExtractionCompleted: data.emotion_extraction_completed,
        audioEmotionExtractionCompleted: data.audio_emotion_extraction_completed,
        congruenceAnalysisCompleted: data.congruence_analysis_completed,
      });
    } catch (err) {
      console.error('Failed to fetch emotion analysis:', err);
      setEmotionData({
        loading: false,
        error: err instanceof Error ? err.message : 'Failed to load emotion analysis'
      });
    }
  };

  // Open triage suggestions modal (forceRegenerate=true when refreshing)
  const handleOpenTriageModal = async (extractionId: string, forceRegenerate: boolean = false) => {
    setShowTriageModal(true);
    setTriageData({ loading: true });

    try {
      const data = await getTriageSuggestions(extractionId, true, getAccessToken(), forceRegenerate);
      setTriageData({
        loading: false,
        extraction_id: data.extraction_id || undefined,
        specialty: data.specialty,
        consultation_type: data.consultation_type,
        critical_actions: data.critical_actions,
        important_considerations: data.important_considerations,
        nice_to_have: data.nice_to_have,
        matched_presentations: data.matched_presentations,
        identified_red_flags: data.identified_red_flags,
        gap_analysis: data.gap_analysis,
        total_suggestions: data.total_suggestions,
        generated_at: data.generated_at,
        processing_time_ms: data.processing_time_ms,
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load triage suggestions';
      // Only log as error if it's not a "triage disabled" warning
      if (errorMessage.includes('not enabled')) {
        console.warn('Triage disabled:', errorMessage);
      } else {
        console.error('Failed to fetch triage suggestions:', err);
      }
      setTriageData({
        loading: false,
        error: errorMessage
      });
    }
  };

  // Open interventions modal
  const handleOpenInterventionsModal = async (extractionId: string) => {
    setShowInterventionsModal(true);
    setInterventionsData({ interventions: [], loading: true });

    try {
      const token = await getAccessToken();
      const response = await authFetch(
        `${API_CONFIG.backendUrl}/api/v1/extractions/${extractionId}/interventions`,
        token
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch interventions: ${response.status}`);
      }

      const data = await response.json();
      setInterventionsData({
        interventions: data.interventions || [],
        loading: false,
        insightsEnabled: data.insights_enabled !== false, // Default to true if not present
      });
    } catch (err) {
      console.error('Failed to fetch interventions:', err);
      setInterventionsData({
        interventions: [],
        loading: false,
        error: err instanceof Error ? err.message : 'Failed to load interventions'
      });
    }
  };

  // Open EHR payload preview modal
  const handleOpenPayloadModal = async (extractionId: string, payloadType: 'raster' | 'aosta' | 'neopaed' | 'kg') => {
    setShowPayloadModal(true);
    setPayloadData({ loading: true, payloadType });

    try {
      const token = await getAccessToken();
      const response = await authFetch(
        `${API_CONFIG.backendUrl}/api/v1/ehr/payload-preview/${extractionId}?payload_type=${payloadType}`,
        token
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch payload: ${response.status}`);
      }

      const data = await response.json();
      setPayloadData({
        loading: false,
        payload: data.payload,
        payloadType: data.payload_type,
        templateCode: data.template_code
      });
    } catch (err) {
      console.error('Failed to fetch payload:', err);
      setPayloadData({
        loading: false,
        payloadType,
        error: err instanceof Error ? err.message : 'Failed to load payload'
      });
    }
  };

  // ============================================================================
  // Edit Mode Handlers
  // ============================================================================

  // Enter edit mode - copy current data to editable state
  const handleEnterEditMode = () => {
    if (coreExtractionData?.insights) {
      setEditedCoreData({ ...coreExtractionData.insights });
    }
    if (additionalExtractionData?.insights) {
      setEditedAdditionalData({ ...additionalExtractionData.insights });
    }
    setIsEditMode(true);
    setEditSaveError(null);
    setEditSaveSuccess(null);
  };

  // Cancel edit mode - discard changes
  const handleCancelEdit = () => {
    setIsEditMode(false);
    setEditedCoreData(null);
    setEditedAdditionalData(null);
    setEditSaveError(null);
    setEditSaveSuccess(null);
  };

  // Save edits to backend
  const handleSaveEdits = async () => {
    // Determine who is editing: assistant takes priority if selected
    const editedById = selectedAssistantId || selectedCounsellorId;
    const editedByType: 'doctor' | 'nurse' = selectedAssistantId ? 'nurse' : 'doctor';

    if (!currentExtractionId || !editedById) {
      setEditSaveError('Missing extraction ID or editor ID');
      return;
    }

    setIsSavingEdits(true);
    setEditSaveError(null);
    setEditSaveSuccess(null);
    setEditWarnings([]);

    try {
      // Combine core and additional data
      const combinedEditedData = {
        ...(editedCoreData || {}),
        ...(editedAdditionalData || {}),
      };

      const result = await saveExtractionEdits(
        currentExtractionId,
        combinedEditedData,
        editedById,
        getAccessToken(),
        editedByType
      );

      setEditSaveSuccess(`Saved successfully! Edit count: ${result.edit_count}${result.medicine_feedback_scheduled ? ' (Medicine feedback processing scheduled)' : ''}`);

      // Capture warnings from response
      const hasBlockingWarnings = result.warnings?.some(w => w.severity === 'warning' || w.severity === 'error');
      if (result.warnings && result.warnings.length > 0) {
        setEditWarnings(result.warnings);
      }

      // Update the display data with edited values
      if (editedCoreData && coreExtractionData) {
        setCoreExtractionData({
          ...coreExtractionData,
          insights: editedCoreData,
        });
      }
      if (editedAdditionalData && additionalExtractionData) {
        setAdditionalExtractionData({
          ...additionalExtractionData,
          insights: editedAdditionalData,
        });
      }

      // If warnings with severity warning/error exist, keep edit mode open longer
      // Otherwise exit edit mode after delay
      setTimeout(() => {
        setIsEditMode(false);
        setEditedCoreData(null);
        setEditedAdditionalData(null);
        setEditSaveSuccess(null);
        if (!hasBlockingWarnings) {
          setEditWarnings([]);
        }
      }, hasBlockingWarnings ? 8000 : 2000);

    } catch (err) {
      console.error('Failed to save edits:', err);
      setEditSaveError(err instanceof Error ? err.message : 'Failed to save edits');
    } finally {
      setIsSavingEdits(false);
    }
  };

  // Handle JSON text change in textarea
  const handleCoreDataChange = (newJsonText: string) => {
    try {
      const parsed = JSON.parse(newJsonText);
      setEditedCoreData(parsed);
      setEditSaveError(null);
    } catch {
      setEditSaveError('Invalid JSON format');
    }
  };

  const handleAdditionalDataChange = (newJsonText: string) => {
    try {
      const parsed = JSON.parse(newJsonText);
      setEditedAdditionalData(parsed);
      setEditSaveError(null);
    } catch {
      setEditSaveError('Invalid JSON format');
    }
  };

  // Handle template selection (toggle selection if clicking same template)
  const handleTemplateSelect = (templateId: string) => {
    // If clicking the currently selected template, deselect it
    if (selectedTemplate?.id === templateId) {
      setSelectedTemplate(null);
      clearResults();
      return;
    }

    // Otherwise, select the new template
    const template = activatedTemplates.find(t => t.id === templateId);
    setSelectedTemplate(template || null);
    clearResults();
  };

  const clearResults = () => {
    setCoreExtractionData(null);
    setAdditionalExtractionData(null);
    setError(null);
    setTranscript('');
    setResultsViewMode('json');
    // Clear translation state
    setTranslationData(null);
    setTranslationViewActive(false);
    setEditedTranslationData(null);
    setTranslationOutdated(false);
  };

  // Fetch counsellor's translation_language when counsellor changes
  useEffect(() => {
    if (!selectedCounsellorId) {
      setCounsellorTranslationLanguage(null);
      return;
    }
    const fetchLang = async () => {
      try {
        const accessToken = getAccessToken();
        const res = await authGet(`/api/v1/counsellors/${selectedCounsellorId}`, accessToken);
        if (res.ok) {
          const data = await res.json();
          const counsellor = data.doctor || data;
          setCounsellorTranslationLanguage(counsellor.translation_language || null);
        }
      } catch {
        // Non-critical - translation toggle just won't show
      }
    };
    fetchLang();
  }, [selectedCounsellorId]);

  // Language display names
  const LANGUAGE_LABELS: Record<string, string> = {
    tamil: 'தமிழ்',
    hindi: 'हिन्दी',
    telugu: 'తెలుగు',
    kannada: 'ಕನ್ನಡ',
    malayalam: 'മലയാളം',
    bengali: 'বাংলা',
    marathi: 'मराठी',
    gujarati: 'ગુજરાતી',
  };

  // Fetch translation for current extraction
  const handleFetchTranslation = async () => {
    if (!currentExtractionId) return;
    setTranslationLoading(true);
    try {
      const result = await getExtractionTranslation(currentExtractionId, getAccessToken());
      setTranslationData(result.translation);
      setTranslationViewActive(true);

      // Check if translation is outdated (English was edited after translation)
      if (coreExtractionData) {
        const extractionLastEdited = (coreExtractionData as unknown as Record<string, unknown>)?.last_edited_at as string | undefined;
        if (extractionLastEdited && result.translation.created_at) {
          setTranslationOutdated(new Date(extractionLastEdited) > new Date(result.translation.created_at));
        }
      }
    } catch (err) {
      if (err instanceof Error && err.message === 'NO_TRANSLATION') {
        // Translation not ready yet - might still be processing
        setTranslationData(null);
      } else {
        console.error('Failed to fetch translation:', err);
      }
    } finally {
      setTranslationLoading(false);
    }
  };

  // Toggle between English and translated view
  const handleToggleTranslation = () => {
    if (translationViewActive) {
      // Switch back to English
      setTranslationViewActive(false);
      setEditedTranslationData(null);
    } else {
      // Fetch and show translation
      handleFetchTranslation();
    }
  };

  // Save translated version edits
  const handleSaveTranslationEdits = async () => {
    const editedById = selectedAssistantId || selectedCounsellorId;
    const editedByType: 'doctor' | 'nurse' = selectedAssistantId ? 'nurse' : 'doctor';
    if (!currentExtractionId || !editedById || !editedTranslationData) return;

    setIsSavingEdits(true);
    setEditSaveError(null);
    try {
      const result = await saveTranslationEdits(
        currentExtractionId,
        editedTranslationData,
        editedById,
        getAccessToken(),
        editedByType,
      );
      setTranslationData(result.translation);
      setEditSaveSuccess('Translation edits saved!');
      setTimeout(() => {
        setIsEditMode(false);
        setEditedTranslationData(null);
        setEditSaveSuccess(null);
      }, 2000);
    } catch (err) {
      setEditSaveError(err instanceof Error ? err.message : 'Failed to save translation edits');
    } finally {
      setIsSavingEdits(false);
    }
  };

  // Retry translation
  const handleRetryTranslation = async () => {
    if (!currentExtractionId) return;
    setRetranslating(true);
    try {
      await retryExtractionTranslation(currentExtractionId, getAccessToken());
      setTranslationOutdated(false);
      // Poll for completion after a delay
      setTimeout(() => {
        handleFetchTranslation();
        setRetranslating(false);
      }, 8000);
    } catch (err) {
      console.error('Failed to retry translation:', err);
      setRetranslating(false);
    }
  };

  // Handle translation JSON text change in textarea
  const handleTranslationDataChange = (newJsonText: string) => {
    try {
      const parsed = JSON.parse(newJsonText);
      setEditedTranslationData(parsed);
      setEditSaveError(null);
    } catch {
      setEditSaveError('Invalid JSON format');
    }
  };

  // Get the JSON to display for translation view
  const getTranslationDisplayJson = (): Record<string, unknown> | null => {
    if (!translationData) return null;
    return (translationData.edited_translated_json || translationData.translated_extraction_json) as Record<string, unknown>;
  };

  // Format time helper
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Validation
  // Note: We no longer check !isSubmitting here - users can start new recordings
  // while previous ones process in the background
  const canStartRecording = (): boolean => {
    return Boolean(
      selectedCounsellorId &&
      selectedTemplate &&
      processingMode &&
      studentId.trim() &&
      !isRecording
    );
  };

  // Helper: Fetch with retry for transient errors
  const fetchWithRetry = async (url: string, maxRetries = 3, baseDelay = 500): Promise<Response> => {
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await authGet(url, getAccessToken());

        // Retry on 5xx errors or specific transient errors
        if (response.status >= 500 && attempt < maxRetries) {
          const errorText = await response.text();
          console.warn(`[FETCH_RETRY] Attempt ${attempt}/${maxRetries} failed with ${response.status}: ${errorText.slice(0, 100)}`);
          await new Promise(resolve => setTimeout(resolve, baseDelay * Math.pow(2, attempt - 1)));
          continue;
        }

        return response;
      } catch (error) {
        lastError = error as Error;
        console.warn(`[FETCH_RETRY] Attempt ${attempt}/${maxRetries} failed:`, error);

        if (attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, baseDelay * Math.pow(2, attempt - 1)));
        }
      }
    }

    throw lastError || new Error('Fetch failed after retries');
  };

  // Display full extraction results — shows all segments immediately,
  // then filters out "excluded" segments in the background once segment config loads
  const splitFullExtractionResults = async (
    insights: any,
    metadata: any,
    extractionTime: number | null
  ) => {
    if (!selectedTemplate) return;

    const buildMetadata = (segmentCount: number) => metadata || {
      correlation_id: null,
      submission_id: null,
      extraction_id: 'fallback',
      counsellor_id: selectedCounsellorId || null,
      student_id: null,
      template_code: selectedTemplate.template_code || null,
      mode: 'full',
      segment_count: segmentCount,
      processing_mode: null,
      timestamp: new Date().toISOString(),
    };

    // Show all results immediately (no network wait)
    setCoreExtractionData({
      success: true,
      insights: insights,
      metadata: buildMetadata(Object.keys(insights).length),
    });
    setCoreExtractionTime(extractionTime);
    setAdditionalExtractionData(null);

    // Background: fetch segment config and remove excluded segments
    try {
      const segmentUrl = `${API_CONFIG.backendUrl}/api/v1/summary/segments/${selectedTemplate.consultation_type_code}?counsellor_id=${selectedCounsellorId}&template_code=${encodeURIComponent(selectedTemplate.template_code)}`;

      const segmentsResponse = await fetchWithRetry(segmentUrl, 3, 500);
      if (!segmentsResponse.ok) return;

      const segmentsData = await segmentsResponse.json();
      const segments = segmentsData.segments || [];

      // Filter out excluded segments
      const excludedCodes = new Set(
        segments.filter((s: any) => s.category === 'excluded').map((s: any) => s.segment_code)
      );

      if (excludedCodes.size === 0) return; // Nothing to filter

      const filtered: any = {};
      for (const [code, data] of Object.entries(insights)) {
        if (!excludedCodes.has(code)) {
          filtered[code] = data;
        }
      }

      setCoreExtractionData({
        success: true,
        insights: filtered,
        metadata: buildMetadata(Object.keys(filtered).length),
      });
    } catch (error) {
      // Non-critical — results are already displayed
      console.warn('[SPLIT_EXTRACTION] Background filter failed (results still visible):', error);
    }
  };

  // Chunked recording functions
  const startChunkedRecording = async () => {
    if (!canStartRecording()) return;

    setError(null);
    setProcessingProgress(null);
    setChunksUploaded(0);
    setRecordingDuration(0);
    setStitchingTime(null);
    setTranscriptionTime(null);
    setCoreExtractionTime(null);
    setAdditionalExtractionTime(null);

    try {
      // ⭐ Always send the template code and name to enable parallel prompt generation optimization
      // The backend needs the template_code for DB lookups (unique identifier)
      // and template_name for human readability
      const templateCodeToUse = selectedTemplate?.template_code || 'Unknown';
      const templateNameToUse = selectedTemplate?.template_name || 'Unknown';

      // ⭐ Only send extraction_mode to backend when doing FULL extraction
      // For progressive extraction (core/additional), backend should only transcribe
      // Then frontend will call /extract API separately for progressive loading
      const backendExtractionMode = extractionMode === 'full' ? 'full' : undefined;

      recordingManagerRef.current = new RecordingManager();
      recordingManagerRef.current.setAccessToken(getAccessToken());
      await recordingManagerRef.current.startRecording(
        {
          template: templateCodeToUse,  // Template code for DB lookups
          templateName: templateNameToUse,  // Display name for readability
          doctorName: selectedCounsellorId || 'Unknown',
          nurseId: selectedAssistantId || undefined,  // Optional assistant_id if recording initiated by assistant
          patientId: studentId,
          transcriptionEngine: 'gemini',
          processingMode: processingMode,
          extractionMode: backendExtractionMode,  // undefined for progressive extraction
          chunkDurationSeconds: 10,
          isContinuation: isContinuation,
        },
        (chunkIndex) => {
          setChunksUploaded(chunkIndex + 1);
        },
        (abortMessage) => {
          // Early audio-quality hard-stop from backend: reset recording UI and
          // surface the reason (same reset path as a normal stop, minus submit).
          setIsRecording(false);
          setIsPaused(false);
          setInputMode(null);
          setChunksUploaded(0);
          setRecordingDuration(0);
          setError(abortMessage);
        }
      );

      setIsRecording(true);
      setIsPaused(false);
      setInputMode('mic');
    } catch (err) {
      setError((err as Error).message || 'Failed to start recording');
    }
  };

  const stopChunkedRecording = async () => {
    if (!recordingManagerRef.current) return;

    // Capture current session info before resetting
    const currentStudentId = studentId;
    const currentTemplateName = selectedTemplate?.template_name || 'Unknown';

    try {
      const submissionId = await recordingManagerRef.current.stopAndSubmit();

      // Reset UI immediately - user can now start a new recording
      setIsRecording(false);
      setIsPaused(false);
      setInputMode(null);
      setChunksUploaded(0);
      setRecordingDuration(0);

      // Create background session and start Realtime listener
      const backgroundSession: BackgroundSession = {
        submissionId,
        patientId: currentStudentId,
        templateName: currentTemplateName,
        status: 'processing',
        progress: 0,
        startedAt: new Date(),
        templateContext: selectedTemplate ? {
          templateCode: selectedTemplate.template_code,
          consultationTypeCode: selectedTemplate.consultation_type_code,
          doctorId: selectedCounsellorId || '',
        } : undefined,
      };

      addBackgroundSession(backgroundSession);
      console.log('[VHR_MIC] Recording submitted, processing in background:', submissionId);

    } catch (err) {
      setError((err as Error).message || 'Failed to submit recording');
      setIsRecording(false);
      setIsPaused(false);
      setInputMode(null);
    }
  };

  const pauseChunkedRecording = () => {
    if (recordingManagerRef.current) {
      recordingManagerRef.current.pause();
      setIsPaused(true);
    }
  };

  const resumeChunkedRecording = () => {
    if (recordingManagerRef.current) {
      recordingManagerRef.current.resume();
      setIsPaused(false);
    }
  };

  const cancelChunkedRecording = async () => {
    if (recordingManagerRef.current) {
      await recordingManagerRef.current.cancel();
      setIsRecording(false);
      setIsPaused(false);
      setInputMode(null);
      setChunksUploaded(0);
      setRecordingDuration(0);
    }
  };

  // File upload function (uses chunked recording API)
  const handleFileUpload = async (file: File) => {
    if (!canStartRecording()) return;

    // Capture current session info before any state changes
    const currentStudentId = studentId;
    const currentTemplateName = selectedTemplate?.template_name || 'Unknown';

    setInputMode('upload');
    setError(null);
    setSelectedFile(file);

    try {
      // Convert file to base64
      const base64Audio = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = reader.result as string;
          const base64 = result.split(',')[1];
          resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });

      // Create recording manager
      const recordingManager = new RecordingManager();
      recordingManager.setAccessToken(getAccessToken());

      // Use template_code for DB lookups (unique constraint) and template_name for display
      const templateCodeToUse = selectedTemplate?.template_code || 'Unknown';
      const templateNameToUse = selectedTemplate?.template_name || 'Unknown';

      // Only send extraction_mode to backend when doing FULL extraction
      const backendExtractionMode = extractionMode === 'full' ? 'full' : undefined;

      console.log('[FILE_UPLOAD] Template:', templateNameToUse, 'Student:', currentStudentId);

      // Start session WITHOUT microphone (for file uploads)
      await recordingManager.startSessionWithoutMicrophone({
        template: templateCodeToUse,
        templateName: templateNameToUse,
        doctorName: selectedCounsellorId || 'Unknown',
        patientId: currentStudentId,
        transcriptionEngine: 'gemini',
        processingMode: processingMode,
        extractionMode: backendExtractionMode,
        chunkDurationSeconds: 0,
        isContinuation: isContinuation,
      });

      // Upload entire file as single chunk with file's mime type
      const uploadResponse = await recordingManager.uploadChunk(
        base64Audio,
        0,
        true,
        file.type
      );

      // Get submission ID from upload response (last chunk returns it)
      const submissionId = uploadResponse.submissionId;

      if (!submissionId) {
        throw new Error('No submission ID received from backend');
      }

      // Reset UI immediately - user can now upload another file
      setInputMode(null);
      setSelectedFile(null);

      // Create background session and start Realtime listener
      const backgroundSession: BackgroundSession = {
        submissionId,
        patientId: currentStudentId,
        templateName: currentTemplateName,
        status: 'processing',
        progress: 0,
        startedAt: new Date(),
        templateContext: selectedTemplate ? {
          templateCode: selectedTemplate.template_code,
          consultationTypeCode: selectedTemplate.consultation_type_code,
          doctorId: selectedCounsellorId || '',
        } : undefined,
      };

      addBackgroundSession(backgroundSession);
      console.log('[FILE_UPLOAD] File uploaded, processing in background:', submissionId);

    } catch (err) {
      setError((err as Error).message || 'Failed to upload file');
      setInputMode(null);
      setSelectedFile(null);
    }
  };

  // Recording handlers (always use chunked recording)
  const handleStartRecording = async () => {
    await startChunkedRecording();
  };

  const handleStopRecording = async () => {
    await stopChunkedRecording();
  };

  const handleClearAll = () => {
    clearResults();
    setStudentId('');
    setInputMode(null);
    setSelectedFile(null);
    setProcessingProgress(null);
  };

  const isOphthalOrOptoTemplate = (template: ActivatedTemplate | null): boolean => {
    if (!template) return false;

    // Check consultation_type_code (stable identifiers from backend)
    // These match the consultation types that use two-part extraction or specialized HTML rendering
    const ophthalOptoCodes = [
      'OPTOMETRY',             // Optometry
      'OPHTHALMOLOGY',         // Ophthalmology (basic)
      'OPHTHAL_DISCHARGE',     // Ophthalmology Discharge
      'OPHTHAL_FULL',          // Ophthalmology Full Consultation
      'OPHTHAL_PRESCRIPTION',  // Ophthalmology Prescription (list format)
      'OPHTHAL_POSTOP_RX',     // Post-Operative Rx (table format with timings)
    ];

    return ophthalOptoCodes.includes(template.consultation_type_code);
  };

  // If merge screen is shown, render only the merge screen
  if (showMergeScreen) {
    return (
      <ExtractionMergeScreen
        initialStudentId={studentId}
        initialCounsellorId={selectedCounsellorId || undefined}
        onClose={() => setShowMergeScreen(false)}
      />
    );
  }

  return (
    <div className="h-full flex flex-col space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-lg shadow-lg p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold mb-2">Virtual Student Record (VSR)</h2>
            <p className="text-sm text-blue-100">
              Unified medical documentation with voice recording and file upload
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Cache Refresh Message */}
            {cacheRefreshMessage && (
              <span className={`text-xs px-2 py-1 rounded ${
                cacheRefreshMessage.type === 'success'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-red-100 text-red-800'
              }`}>
                {cacheRefreshMessage.text}
              </span>
            )}

            {/* Refresh Cache Button */}
            <button
              onClick={handleRefreshCache}
              disabled={isRefreshingCache}
              className="flex items-center px-3 py-2 bg-blue-500 hover:bg-blue-400 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg text-sm"
              title="Refresh all pipeline caches"
            >
              <svg
                className={`w-4 h-4 mr-1.5 ${isRefreshingCache ? 'animate-spin' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {isRefreshingCache ? 'Refreshing...' : 'Refresh Cache'}
            </button>

            {/* Audio Playback Button */}
            <button
              onClick={() => setShowAudioPlaybackModal(true)}
              className="flex items-center px-3 py-2 bg-purple-500 hover:bg-purple-400 text-white font-medium rounded-lg transition-colors shadow-md hover:shadow-lg text-sm"
              title="Play audio by submission ID"
            >
              <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Playback
            </button>

            {/* Merge Extractions Button */}
            <button
              onClick={() => setShowMergeScreen(true)}
              disabled={!selectedCounsellorId}
              className="flex items-center px-4 py-2 bg-white hover:bg-blue-50 text-blue-700 font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg"
            >
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
              Merge Extractions
            </button>
          </div>
        </div>
      </div>

      {/* Counsellor Selector */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <CounsellorSelector
          selectedCounsellorId={selectedCounsellorId}
          onCounsellorSelect={setSelectedCounsellorId}
          required={false}
        />
        {/* Recording History Button */}
        {selectedCounsellorId && (
          <button
            onClick={() => { setRecordingHistorySource('doctor'); setShowRecordingHistoryModal(true); }}
            className="mt-4 w-full px-4 py-2 text-sm bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition-colors flex items-center justify-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            View Recording History
          </button>
        )}
      </div>

      {/* Assistant Selector (Optional) */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <AssistantSelector
          selectedAssistantId={selectedAssistantId}
          onAssistantSelect={setSelectedAssistantId}
          required={false}
        />
        {selectedAssistantId && (
          <p className="mt-2 text-xs text-teal-600 dark:text-teal-400">
            Templates will be loaded from assistant&apos;s accessible templates
          </p>
        )}
        {/* Assistant Recording History Button */}
        {selectedAssistantId && (
          <button
            onClick={() => { setRecordingHistorySource('nurse'); setShowRecordingHistoryModal(true); }}
            className="mt-4 w-full px-4 py-2 text-sm bg-teal-50 text-teal-700 rounded-lg hover:bg-teal-100 transition-colors flex items-center justify-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            View Recording History
          </button>
        )}
      </div>

      {/* Activated Templates Selector */}
      <div className="bg-white rounded-lg shadow-md p-6">
        {!selectedCounsellorId ? (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
            <svg className="w-12 h-12 text-blue-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            <p className="text-sm font-medium text-blue-900">Select a counsellor to view activated templates</p>
            <p className="text-xs text-blue-700 mt-1">Choose a counsellor from the dropdown above</p>
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between mb-4">
              <label className="block text-sm font-medium text-gray-700">
                Activated Templates
              </label>
              {loadingTemplates && (
                <div className="flex items-center text-sm text-gray-500">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                  Loading templates...
                </div>
              )}
            </div>

            {!loadingTemplates && activatedTemplates.length === 0 && (
              <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                <svg className="w-16 h-16 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-sm font-medium text-gray-700 mb-2">No activated templates</p>
                <p className="text-xs text-gray-500">
                  This counsellor hasn't activated any templates yet.
                </p>
              </div>
            )}

            {!loadingTemplates && activatedTemplates.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {[...activatedTemplates].sort((a, b) => (a.template_name || '').localeCompare(b.template_name || '')).map((template) => (
                  <button
                    key={template.id}
                    onClick={() => handleTemplateSelect(template.id)}
                    disabled={isRecording || isSubmitting}
                    className={`
                      relative flex flex-col items-start p-4 rounded-lg border-2 transition-all text-left
                      ${
                        selectedTemplate?.id === template.id
                          ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
                          : 'border-gray-300 bg-white hover:border-gray-400 hover:bg-gray-50'
                      }
                      ${(isRecording || isSubmitting) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                    `}
                  >
                    <div className="w-full">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex-1 min-w-0">
                          <h4 className="text-sm font-semibold text-gray-900">
                            {template.template_name}
                          </h4>
                          <p className="text-xs text-gray-500 mt-0.5">
                            {template.template_code}
                          </p>
                        </div>
                        {selectedTemplate?.id === template.id && (
                          <svg className="w-5 h-5 text-blue-600 flex-shrink-0 ml-2" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                          </svg>
                        )}
                      </div>
                      <div className="inline-flex items-center px-2 py-1 rounded-md bg-blue-100 mb-2">
                        <span className="text-xs font-medium text-blue-700">
                          {template.consultation_type_name}
                        </span>
                      </div>
                      {template.description && (
                        <p className="text-xs text-gray-600 line-clamp-2">
                          {template.description}
                        </p>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Configuration & Recording */}
        <div className="space-y-4">
          {/* Processing Mode Selection */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <label className="block text-sm font-medium text-gray-700 mb-3">
              Processing Mode
            </label>
            <select
              value={processingMode}
              onChange={(e) => setProcessingMode(e.target.value)}
              disabled={isRecording || isSubmitting}
              className="w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed text-gray-900"
            >
              <option value="fast">Fast (Flash Extraction)</option>
              <option value="default">Default (Pro Extraction) - Recommended</option>
              <option value="thorough">Thorough (Pro Extraction with Enhanced Quality)</option>
            </select>
            <div className="mt-2 text-xs text-gray-600">
              {processingModes.find(m => m.mode_code === processingMode) && (
                <>
                  <p><strong>{processingModes.find(m => m.mode_code === processingMode)?.mode_name}</strong></p>
                  {processingModes.find(m => m.mode_code === processingMode)?.description && (
                    <p className="mt-1">{processingModes.find(m => m.mode_code === processingMode)?.description}</p>
                  )}
                  <p className="mt-1">
                    Estimated time: ~{processingModes.find(m => m.mode_code === processingMode)?.estimated_time_seconds}s
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Extraction Mode Selection */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <label className="block text-sm font-medium text-gray-700 mb-3">
              Extraction Mode
            </label>
            <select
              value={extractionMode}
              onChange={(e) => setExtractionMode(e.target.value as 'core' | 'additional' | 'full')}
              disabled={isRecording || isSubmitting}
              className="w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed text-gray-900"
            >
              <option value="full">Full - Backend Extraction (All Segments)</option>
              <option value="core">Core - Frontend Extraction (Essential Only)</option>
              <option value="additional">Additional - Frontend Extraction (Core + Supplementary)</option>
            </select>
            <div className="mt-2 text-xs text-gray-600">
              {extractionMode === 'full' && (
                <p>Backend handles complete extraction with all configured segments (~30-60s)</p>
              )}
              {extractionMode === 'core' && (
                <p>Transcribe first, then extract essential CORE segments on frontend (~25-35s)</p>
              )}
              {extractionMode === 'additional' && (
                <p>Transcribe first, then extract CORE + ADDITIONAL segments on frontend (~50-70s total)</p>
              )}
            </div>
          </div>

          {/* Student ID Selection */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <label className="block text-sm font-medium text-gray-700 mb-3">
              Student ID
            </label>
            {loadingStudents ? (
              <div className="flex items-center justify-center py-3">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500 mr-2"></div>
                <span className="text-gray-500 text-sm">Loading students...</span>
              </div>
            ) : studentsList.length > 0 ? (
              <select
                value={studentId}
                onChange={(e) => setStudentId(e.target.value)}
                disabled={isRecording || isSubmitting}
                className="w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed text-gray-900 bg-white"
              >
                <option value="">Select a student...</option>
                {studentsList.map((student) => (
                  <option key={student.id} value={student.student_id}>
                    {student.student_id}
                    {student.full_name ? ` - ${student.full_name}` : ''}
                    {student.school_name ? ` (${student.school_name})` : ''}
                    {student.add_info?.roomNo ? ` [Room ${student.add_info.roomNo}, Bed ${student.add_info.bedNo}]` : ''}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={studentId}
                onChange={(e) => setStudentId(e.target.value)}
                placeholder="Enter student ID (e.g., PAT-12345)"
                disabled={isRecording || isSubmitting}
                className="w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed text-gray-900"
              />
            )}
          </div>

          {/* Continuation Toggle - only visible when a student is selected */}
          {studentId && !isRecording && !isSubmitting && (
            <div className="bg-white rounded-lg shadow-md p-4">
              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isContinuation}
                  onChange={(e) => setIsContinuation(e.target.checked)}
                  disabled={isRecording || isSubmitting}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-900">Continue previous session</span>
                  <p className="text-xs text-gray-500">
                    Enable if this is a follow-up recording for the same visit (e.g., prescription-only after full session)
                  </p>
                </div>
              </label>
            </div>
          )}

          {/* Recording Controls */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Audio Input</h3>

            {/* Error Display */}
            {error && (
              <div className="bg-red-50 border-2 border-red-200 rounded-lg p-4 mb-4">
                <div className="flex items-start">
                  <svg className="w-5 h-5 text-red-600 mr-2 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                  <p className="text-sm text-red-800">{error}</p>
                </div>
              </div>
            )}

            {/* Buttons: Mic and Upload */}
            {!isRecording && !isSubmitting && !inputMode && (
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={handleStartRecording}
                  disabled={!canStartRecording()}
                  className="flex flex-col items-center justify-center p-6 border-2 border-blue-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <svg className="w-12 h-12 text-blue-600 mb-2" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z" clipRule="evenodd" />
                  </svg>
                  <span className="text-sm font-medium text-gray-900">Record</span>
                </button>

                <label className="flex flex-col items-center justify-center p-6 border-2 border-gray-300 rounded-lg hover:border-gray-400 hover:bg-gray-50 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">
                  <svg className="w-12 h-12 text-gray-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <span className="text-sm font-medium text-gray-900">Upload</span>
                  <input
                    type="file"
                    accept="audio/*"
                    className="hidden"
                    disabled={!canStartRecording()}
                    onChange={(e) => {
                      if (e.target.files?.[0]) {
                        handleFileUpload(e.target.files[0]);
                      }
                    }}
                  />
                </label>
              </div>
            )}

            {/* Recording in progress */}
            {isRecording && inputMode === 'mic' && (
              <div className="space-y-4">
                <div className="flex items-center justify-center space-x-4 py-6">
                  <div className="animate-pulse flex space-x-2">
                    <div className="w-3 h-8 bg-red-500 rounded"></div>
                    <div className="w-3 h-12 bg-red-500 rounded"></div>
                    <div className="w-3 h-6 bg-red-500 rounded"></div>
                  </div>
                </div>

                <div className="text-center space-y-2">
                  <p className="text-2xl font-mono font-bold text-gray-900">
                    {formatTime(recordingDuration)}
                  </p>
                  <p className="text-sm text-gray-600">Chunks uploaded: {chunksUploaded}</p>
                </div>

                <div className="flex space-x-2">
                  {!isPaused ? (
                    <button
                      onClick={pauseChunkedRecording}
                      className="flex-1 px-4 py-3 bg-yellow-600 hover:bg-yellow-700 text-white font-medium rounded-lg transition-colors"
                    >
                      ⏸ Pause
                    </button>
                  ) : (
                    <button
                      onClick={resumeChunkedRecording}
                      className="flex-1 px-4 py-3 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors"
                    >
                      ▶ Resume
                    </button>
                  )}
                  <button
                    onClick={handleStopRecording}
                    className="flex-1 px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
                  >
                    ⏹ Stop
                  </button>
                  <button
                    onClick={cancelChunkedRecording}
                    className="px-4 py-3 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg transition-colors"
                  >
                    ✖
                  </button>
                </div>
              </div>
            )}

            {/* Processing state */}
            {(isSubmitting || processingProgress) && (
              <div className="space-y-4">
                <div className="text-center py-6">
                  <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600 mx-auto mb-4"></div>
                  <p className="text-gray-700 font-medium">
                    {processingProgress?.status || 'Processing...'}
                  </p>
                  {processingProgress && (
                    <>
                      <p className="text-sm text-gray-600 mt-2">
                        {processingProgress.message}
                      </p>
                      <div className="mt-4 w-full bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${processingProgress.progress || 0}%` }}
                        ></div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {selectedFile && !isSubmitting && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <svg className="w-8 h-8 text-blue-600 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                    </svg>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{selectedFile.name}</p>
                      <p className="text-xs text-gray-600">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setSelectedFile(null);
                      setInputMode(null);
                    }}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    ✖
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Results */}
        <div className="space-y-4">
          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Extraction Results</h3>
              <div className="flex items-center space-x-3">
                {/* Translation Toggle */}
                {counsellorTranslationLanguage && (coreExtractionData || additionalExtractionData) && currentExtractionId && (
                  <div className="inline-flex items-center rounded-lg border border-gray-300 bg-gray-50 text-xs font-medium overflow-hidden">
                    <button
                      type="button"
                      onClick={() => { setTranslationViewActive(false); setEditedTranslationData(null); }}
                      className={`px-3 py-1.5 border-r border-gray-300 transition-colors ${
                        !translationViewActive ? 'bg-white text-gray-900 font-semibold' : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      EN
                    </button>
                    <button
                      type="button"
                      onClick={handleToggleTranslation}
                      disabled={translationLoading}
                      className={`px-3 py-1.5 transition-colors ${
                        translationViewActive ? 'bg-white text-gray-900 font-semibold' : 'text-gray-600 hover:bg-gray-100'
                      } ${translationLoading ? 'opacity-50' : ''}`}
                    >
                      {translationLoading ? '...' : LANGUAGE_LABELS[counsellorTranslationLanguage] || counsellorTranslationLanguage}
                    </button>
                  </div>
                )}
                {(coreExtractionData || additionalExtractionData) && (
                  <div className="inline-flex items-center rounded-lg border border-gray-300 bg-gray-50 text-xs font-medium overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setResultsViewMode('json')}
                      className={`px-3 py-1.5 border-r border-gray-300 transition-colors ${
                        resultsViewMode === 'json' ? 'bg-white text-gray-900' : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      JSON
                    </button>
                    <button
                      type="button"
                      onClick={() => setResultsViewMode('html')}
                      className={`px-3 py-1.5 border-r border-gray-300 transition-colors ${
                        resultsViewMode === 'html' ? 'bg-white text-gray-900' : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      Report
                    </button>
                    <button
                      type="button"
                      onClick={openHtmlInNewWindow}
                      className="px-3 py-1.5 text-gray-600 hover:bg-gray-100 transition-colors"
                      title="Open report in new window"
                    >
                      ↗
                    </button>
                  </div>
                )}
                {(coreExtractionData || additionalExtractionData || transcript) && (
                  <button
                    onClick={handleClearAll}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                  >
                    Clear All
                  </button>
                )}
              </div>
            </div>

            {/* Loading State - CORE Extraction */}
            {loadingCore && (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600 mb-4"></div>
                <p className="text-gray-600 font-medium">Extracting CORE segments...</p>
                <p className="text-sm text-gray-500 mt-2">
                  Processing with {processingModes.find(m => m.mode_code === processingMode)?.extraction_model || 'default model'}
                </p>
              </div>
            )}

            {/* Results Display - Progressive Loading */}
            {!loadingCore && (coreExtractionData || additionalExtractionData) && (
              <div className="space-y-4">
                {/* Overall Metadata */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-gray-600">Session Type</p>
                      <p className="font-semibold text-gray-900">
                        {/* Use template from extraction result if different from selected, otherwise use selected */}
                        {coreExtractionData?.metadata?.template_code
                          ? (activatedTemplates.find(t => t.template_code === coreExtractionData.metadata.template_code)?.consultation_type_name
                            || selectedTemplate?.consultation_type_name)
                          : selectedTemplate?.consultation_type_name}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">Processing Mode</p>
                      <p className="font-semibold text-gray-900">
                        {processingModes.find(m => m.mode_code === processingMode)?.mode_name || processingMode}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">CORE Segments</p>
                      <p className="font-semibold text-gray-900">
                        {coreExtractionData ? `${coreExtractionData.metadata.segment_count} ✅` : 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">ADDITIONAL Segments</p>
                      <p className="font-semibold text-gray-900">
                        {loadingAdditional ? (
                          <span className="text-blue-600">Loading... ⏳</span>
                        ) : additionalExtractionData ? (
                          <span>{additionalExtractionData.metadata.segment_count} ✅</span>
                        ) : (
                          <span className="text-gray-400">None</span>
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">Audio Stitching Time</p>
                      <p className="font-semibold text-gray-900">
                        {stitchingTime ? `${stitchingTime.toFixed(2)}s` : 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">Transcription Time</p>
                      <p className="font-semibold text-gray-900">
                        {transcriptionTime ? `${transcriptionTime.toFixed(2)}s` : 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">Core Extraction Time</p>
                      <p className="font-semibold text-gray-900">
                        {coreExtractionTime ? `${coreExtractionTime.toFixed(2)}s` : 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">Additional Extraction Time</p>
                      <p className="font-semibold text-gray-900">
                        {loadingAdditional ? (
                          <span className="text-blue-600">Loading... ⏳</span>
                        ) : additionalExtractionTime ? (
                          `${additionalExtractionTime.toFixed(2)}s`
                        ) : (
                          'N/A'
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">Total Processing Time</p>
                      <p className="font-semibold text-gray-900">
                        {(() => {
                          const times = [stitchingTime, transcriptionTime, coreExtractionTime, additionalExtractionTime].filter((t): t is number => t !== null);
                          if (times.length === 0) return 'N/A';
                          const total = times.reduce((sum, t) => sum + t, 0);
                          const allPresent = stitchingTime && transcriptionTime && coreExtractionTime;
                          return `${total.toFixed(2)}s${!additionalExtractionTime && allPresent ? ' (partial)' : ''}`;
                        })()}
                      </p>
                    </div>

                    {/* Audio Quality Indicator */}
                    {currentAudioQuality && (
                      <div className="col-span-2 pt-2 border-t border-gray-100">
                        <p className="text-gray-600 mb-1">Audio Quality</p>
                        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium ${
                          currentAudioQuality.overall_quality === 'good'
                            ? 'bg-green-50 text-green-700'
                            : currentAudioQuality.overall_quality === 'fair'
                            ? 'bg-amber-50 text-amber-700'
                            : currentAudioQuality.overall_quality === 'poor'
                            ? 'bg-red-50 text-red-700'
                            : 'bg-gray-50 text-gray-600'
                        }`}>
                          <span className={`w-2 h-2 rounded-full ${
                            currentAudioQuality.overall_quality === 'good'
                              ? 'bg-green-500'
                              : currentAudioQuality.overall_quality === 'fair'
                              ? 'bg-amber-500'
                              : currentAudioQuality.overall_quality === 'poor'
                              ? 'bg-red-500'
                              : 'bg-gray-400'
                          }`} />
                          <span className="capitalize">{currentAudioQuality.overall_quality}</span>
                          {currentAudioQuality.metrics?.snr_db != null && (
                            <span className="text-xs opacity-75">
                              (SNR: {currentAudioQuality.metrics.snr_db.toFixed(1)}dB)
                            </span>
                          )}
                        </div>
                        {currentAudioQuality.overall_quality !== 'good' && currentAudioQuality.summary_message && (
                          <p className={`mt-1 text-xs ${
                            currentAudioQuality.overall_quality === 'poor' ? 'text-red-600' : 'text-amber-600'
                          }`}>
                            {currentAudioQuality.summary_message}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Emotion Analysis & Triage Buttons */}
                    {currentExtractionId && (
                      <div className="col-span-2 pt-2 border-t border-gray-100 flex gap-2 flex-wrap">
                        <button
                          onClick={() => handleOpenEmotionModal(currentExtractionId)}
                          className="flex items-center gap-2 px-3 py-2 bg-purple-50 hover:bg-purple-100 text-purple-700 rounded-lg transition-colors text-sm font-medium"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                          </svg>
                          View Emotion Analysis
                        </button>
                        <button
                          onClick={() => handleOpenTriageModal(currentExtractionId)}
                          className="flex items-center gap-2 px-3 py-2 bg-teal-50 hover:bg-teal-100 text-teal-700 rounded-lg transition-colors text-sm font-medium"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                          </svg>
                          View Triage
                        </button>
                        <button
                          onClick={() => handleOpenInterventionsModal(currentExtractionId)}
                          className="flex items-center gap-2 px-3 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg transition-colors text-sm font-medium"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          View Interventions
                        </button>
                        {coreExtractionData?.metadata?.template_code?.toUpperCase().startsWith('RASTER_') && (
                          <button
                            onClick={() => handleOpenPayloadModal(currentExtractionId, 'raster')}
                            className="flex items-center gap-2 px-3 py-2 bg-orange-50 hover:bg-orange-100 text-orange-700 rounded-lg transition-colors text-sm font-medium"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                            View Raster Payload
                          </button>
                        )}
                        {coreExtractionData?.metadata?.template_code?.toUpperCase().startsWith('AOSTA_') && (
                          <button
                            onClick={() => handleOpenPayloadModal(currentExtractionId, 'aosta')}
                            className="flex items-center gap-2 px-3 py-2 bg-cyan-50 hover:bg-cyan-100 text-cyan-700 rounded-lg transition-colors text-sm font-medium"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                            View Aosta Payload
                          </button>
                        )}
                        {(coreExtractionData?.metadata?.template_code?.toUpperCase().startsWith('NEO_') || coreExtractionData?.metadata?.template_code?.toUpperCase().startsWith('NEONATAL_')) && (
                          <button
                            onClick={() => handleOpenPayloadModal(currentExtractionId, 'neopaed')}
                            className="flex items-center gap-2 px-3 py-2 bg-teal-50 hover:bg-teal-100 text-teal-700 rounded-lg transition-colors text-sm font-medium"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                            View Neopaed Payload
                          </button>
                        )}
                        {['CARDIO_INITIAL', 'CARDIO_REASSESS'].includes(coreExtractionData?.metadata?.template_code?.toUpperCase() ?? '') && (
                          <button
                            onClick={() => handleOpenPayloadModal(currentExtractionId, 'kg')}
                            className="flex items-center gap-2 px-3 py-2 bg-purple-50 hover:bg-purple-100 text-purple-700 rounded-lg transition-colors text-sm font-medium"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                            View KG Payload
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Edit Mode Controls */}
                {(coreExtractionData || additionalExtractionData) && currentExtractionId && selectedCounsellorId && (
                  <div className="flex items-center justify-between bg-gray-50 rounded-lg p-3 border border-gray-200">
                    <div className="flex items-center gap-2">
                      {isEditMode ? (
                        <>
                          <span className="text-sm text-orange-700 font-medium flex items-center gap-1">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                            Edit Mode Active
                          </span>
                          {editSaveError && (
                            <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">{editSaveError}</span>
                          )}
                          {editSaveSuccess && (
                            <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">{editSaveSuccess}</span>
                          )}
                        </>
                      ) : (
                        <span className="text-sm text-gray-600">Click Edit to modify extraction data</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {isEditMode ? (
                        <>
                          <button
                            onClick={handleCancelEdit}
                            disabled={isSavingEdits}
                            className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded transition-colors disabled:opacity-50"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={translationViewActive ? handleSaveTranslationEdits : handleSaveEdits}
                            disabled={isSavingEdits || !!editSaveError}
                            className="px-3 py-1.5 text-sm bg-green-600 hover:bg-green-700 text-white rounded font-medium transition-colors disabled:opacity-50 flex items-center gap-1"
                          >
                            {isSavingEdits ? (
                              <>
                                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                </svg>
                                Saving...
                              </>
                            ) : (
                              <>
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                                Save Edits
                              </>
                            )}
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={handleEnterEditMode}
                          className="px-3 py-1.5 text-sm bg-orange-500 hover:bg-orange-600 text-white rounded font-medium transition-colors flex items-center gap-1"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                          Edit
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* Edit Warnings */}
                {editWarnings.length > 0 && (
                  <div className="space-y-1.5">
                    {editWarnings.map((w, i) => (
                      <div
                        key={i}
                        className={`flex items-start gap-2 px-3 py-2 rounded text-xs ${
                          w.severity === 'error' ? 'bg-red-50 text-red-700 border border-red-200' :
                          w.severity === 'warning' ? 'bg-amber-50 text-amber-700 border border-amber-200' :
                          'bg-blue-50 text-blue-700 border border-blue-200'
                        }`}
                      >
                        <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${
                          w.severity === 'error' ? 'bg-red-200 text-red-800' :
                          w.severity === 'warning' ? 'bg-amber-200 text-amber-800' :
                          'bg-blue-200 text-blue-800'
                        }`}>{w.severity}</span>
                        <span>{w.message}</span>
                      </div>
                    ))}
                    <button
                      onClick={() => setEditWarnings([])}
                      className="text-[10px] text-gray-400 hover:text-gray-600 underline"
                    >
                      Dismiss warnings
                    </button>
                  </div>
                )}

                {/* Translation View */}
                {translationViewActive && translationData && (
                  <div>
                    {/* Translation Status Bar */}
                    <div className="flex items-center justify-between bg-purple-50 rounded-lg p-3 border border-purple-200 mb-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-purple-700 font-medium">
                          {LANGUAGE_LABELS[translationData.target_language] || translationData.target_language} Translation
                        </span>
                        {translationData.translation_time_seconds && (
                          <span className="text-xs text-purple-500">({translationData.translation_time_seconds}s)</span>
                        )}
                        {translationOutdated && (
                          <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-medium">
                            Outdated
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {(translationOutdated || translationData.translation_failed) && (
                          <button
                            onClick={handleRetryTranslation}
                            disabled={retranslating}
                            className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-700 text-white rounded font-medium transition-colors disabled:opacity-50"
                          >
                            {retranslating ? 'Re-translating...' : 'Re-translate'}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Translation Failed */}
                    {translationData.translation_failed && (
                      <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-3">
                        <p className="text-sm text-red-700">Translation failed: {translationData.translation_error || 'Unknown error'}</p>
                      </div>
                    )}

                    {/* Translation Not Completed Yet */}
                    {!translationData.translation_completed && !translationData.translation_failed && (
                      <div className="border-2 border-purple-300 rounded-lg p-8 flex flex-col items-center justify-center">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-purple-600 mb-3"></div>
                        <p className="text-purple-600 font-medium">Translating...</p>
                        <p className="text-sm text-purple-400 mt-1">Translation is still processing. Try again in a few seconds.</p>
                        <button
                          onClick={handleFetchTranslation}
                          className="mt-3 px-4 py-1.5 text-sm bg-purple-100 text-purple-700 rounded hover:bg-purple-200 transition-colors"
                        >
                          Refresh
                        </button>
                      </div>
                    )}

                    {/* Translation Completed - Show Full Translated JSON */}
                    {translationData.translation_completed && getTranslationDisplayJson() && (
                      <div className={`border-2 rounded-lg overflow-hidden ${isEditMode ? 'border-orange-400' : 'border-purple-500'}`}>
                        <div className={`px-4 py-3 border-b-2 flex items-center justify-between ${isEditMode ? 'bg-orange-50 border-orange-400' : 'bg-purple-50 border-purple-500'}`}>
                          <div className="flex items-center">
                            <svg className={`w-5 h-5 mr-2 ${isEditMode ? 'text-orange-600' : 'text-purple-600'}`} fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                            <h4 className={`font-bold ${isEditMode ? 'text-orange-900' : 'text-purple-900'}`}>
                              Translated Extraction {isEditMode ? '(Editing)' : ''}
                            </h4>
                          </div>
                          {translationData.translation_edit_count > 0 && (
                            <span className="text-xs text-purple-500">
                              Edited {translationData.translation_edit_count}x
                            </span>
                          )}
                        </div>
                        <div className="p-4 max-h-[600px] overflow-y-auto bg-white">
                          {isEditMode ? (
                            <textarea
                              value={JSON.stringify(editedTranslationData || getTranslationDisplayJson(), null, 2)}
                              onChange={(e) => handleTranslationDataChange(e.target.value)}
                              className="w-full h-[550px] text-xs font-mono text-gray-800 bg-orange-50 border border-orange-200 rounded p-2 focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none"
                              spellCheck={false}
                            />
                          ) : (
                            <pre className="text-xs font-mono text-gray-800 whitespace-pre-wrap">
                              {JSON.stringify(getTranslationDisplayJson(), null, 2)}
                            </pre>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Translation Loading State (before data fetched) */}
                {translationViewActive && !translationData && translationLoading && (
                  <div className="border-2 border-purple-300 rounded-lg p-8 flex flex-col items-center justify-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-purple-600 mb-3"></div>
                    <p className="text-purple-600 font-medium">Loading translation...</p>
                  </div>
                )}

                {/* Translation Not Available */}
                {translationViewActive && !translationData && !translationLoading && (
                  <div className="border-2 border-gray-300 rounded-lg p-8 flex flex-col items-center justify-center">
                    <p className="text-gray-600 font-medium">No translation available yet</p>
                    <p className="text-sm text-gray-400 mt-1">Translation may still be processing. Try refreshing in a few seconds.</p>
                    <button
                      onClick={handleFetchTranslation}
                      className="mt-3 px-4 py-1.5 text-sm bg-purple-100 text-purple-700 rounded hover:bg-purple-200 transition-colors"
                    >
                      Refresh
                    </button>
                  </div>
                )}

                {/* CORE Results (hidden when translation view is active) */}
                {!translationViewActive && coreExtractionData && (
                  <div className={`border-2 rounded-lg overflow-hidden ${isEditMode ? 'border-orange-400' : 'border-green-500'}`}>
                    <div className={`px-4 py-3 border-b-2 flex items-center justify-between ${isEditMode ? 'bg-orange-50 border-orange-400' : 'bg-green-50 border-green-500'}`}>
                      <div className="flex items-center">
                        <svg className={`w-5 h-5 mr-2 ${isEditMode ? 'text-orange-600' : 'text-green-600'}`} fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        <h4 className={`font-bold ${isEditMode ? 'text-orange-900' : 'text-green-900'}`}>
                          CORE Segments {isEditMode ? '(Editing)' : '(Essential)'}
                        </h4>
                      </div>
                      <span className={`text-xs font-medium ${isEditMode ? 'text-orange-700' : 'text-green-700'}`}>
                        {coreExtractionData.metadata.segment_count} segments
                      </span>
                    </div>
                    <div className="p-4 max-h-[400px] overflow-y-auto bg-white">
                      {isEditMode ? (
                        <textarea
                          value={JSON.stringify(editedCoreData || coreExtractionData.insights, null, 2)}
                          onChange={(e) => handleCoreDataChange(e.target.value)}
                          className="w-full h-[350px] text-xs font-mono text-gray-800 bg-orange-50 border border-orange-200 rounded p-2 focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none"
                          spellCheck={false}
                        />
                      ) : resultsViewMode === 'json' ? (
                        <pre className="text-xs font-mono text-gray-800 whitespace-pre-wrap">
                          {JSON.stringify(coreExtractionData.insights, null, 2)}
                        </pre>
                      ) : isOphthalOrOptoTemplate(selectedTemplate) ? (
                        <OphthalHtmlView
                          template={selectedTemplate}
                          coreData={coreExtractionData.insights}
                          additionalData={additionalExtractionData?.insights || null}
                        />
                      ) : (
                        <GenericReportView
                          template={selectedTemplate}
                          data={coreExtractionData.insights}
                          sectionLabel="Core"
                        />
                      )}
                    </div>
                  </div>
                )}

                {/* ADDITIONAL Results - Loading State (hidden when translation view is active) */}
                {!translationViewActive && loadingAdditional && (
                  <div className="border-2 border-blue-300 rounded-lg overflow-hidden">
                    <div className="bg-blue-50 px-4 py-3 border-b-2 border-blue-300">
                      <h4 className="font-bold text-blue-900">ADDITIONAL Segments (Loading...)</h4>
                    </div>
                    <div className="p-8 bg-white flex flex-col items-center justify-center">
                      <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-blue-600 mb-3"></div>
                      <p className="text-blue-600 font-medium">Extracting additional segments in background...</p>
                    </div>
                  </div>
                )}

                {/* Photo attachments — visible once an extraction exists */}
                {!translationViewActive && currentExtractionId && (
                  <ExtractionPhotosSection extractionId={currentExtractionId} />
                )}

                {/* ADDITIONAL Results - Completed (hidden when translation view is active) */}
                {!translationViewActive && !loadingAdditional && additionalExtractionData && (
                  <div className={`border-2 rounded-lg overflow-hidden ${isEditMode ? 'border-orange-400' : 'border-blue-500'}`}>
                    <div className={`px-4 py-3 border-b-2 flex items-center justify-between ${isEditMode ? 'bg-orange-50 border-orange-400' : 'bg-blue-50 border-blue-500'}`}>
                      <div className="flex items-center">
                        <svg className={`w-5 h-5 mr-2 ${isEditMode ? 'text-orange-600' : 'text-blue-600'}`} fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        <h4 className={`font-bold ${isEditMode ? 'text-orange-900' : 'text-blue-900'}`}>
                          ADDITIONAL Segments {isEditMode ? '(Editing)' : '(Supplementary)'}
                        </h4>
                      </div>
                      <span className={`text-xs font-medium ${isEditMode ? 'text-orange-700' : 'text-blue-700'}`}>
                        {additionalExtractionData.metadata.segment_count} segments
                      </span>
                    </div>
                    <div className="p-4 max-h-[400px] overflow-y-auto bg-white">
                      {isEditMode ? (
                        <textarea
                          value={JSON.stringify(editedAdditionalData || additionalExtractionData.insights, null, 2)}
                          onChange={(e) => handleAdditionalDataChange(e.target.value)}
                          className="w-full h-[350px] text-xs font-mono text-gray-800 bg-orange-50 border border-orange-200 rounded p-2 focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none"
                          spellCheck={false}
                        />
                      ) : resultsViewMode === 'json' ? (
                        <pre className="text-xs font-mono text-gray-800 whitespace-pre-wrap">
                          {JSON.stringify(additionalExtractionData.insights, null, 2)}
                        </pre>
                      ) : isOphthalOrOptoTemplate(selectedTemplate) ? (
                        <OphthalHtmlView
                          template={selectedTemplate}
                          coreData={coreExtractionData?.insights || null}
                          additionalData={additionalExtractionData.insights}
                        />
                      ) : (
                        <GenericReportView
                          template={selectedTemplate}
                          data={additionalExtractionData.insights}
                          sectionLabel="Additional"
                        />
                      )}
                    </div>
                  </div>
                )}

                {/* Copy JSON Button */}
                <button
                  onClick={async () => {
                    const combinedData = {
                      core: coreExtractionData?.insights || null,
                      additional: additionalExtractionData?.insights || null,
                      metadata: {
                        consultation_type: selectedTemplate?.consultation_type_name,
                        template_code: selectedTemplate?.template_code,
                        processing_mode: processingMode,
                        extraction_model: processingModes.find(m => m.mode_code === processingMode)?.extraction_model || 'default',
                        student_id: studentId,
                        counsellor_id: selectedCounsellorId,
                        core_segment_count: coreExtractionData?.metadata.segment_count || 0,
                        additional_segment_count: additionalExtractionData?.metadata.segment_count || 0,
                        total_segments: (coreExtractionData?.metadata.segment_count || 0) + (additionalExtractionData?.metadata.segment_count || 0),
                        extracted_at: new Date().toISOString()
                      }
                    };

                    try {
                      await navigator.clipboard.writeText(JSON.stringify(combinedData, null, 2));
                      setJsonCopied(true);
                      setTimeout(() => setJsonCopied(false), 2000);
                    } catch (err) {
                      console.error('Failed to copy JSON:', err);
                    }
                  }}
                  className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors flex items-center justify-center shadow-sm hover:shadow"
                >
                  {jsonCopied ? (
                    <>
                      <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Copied!
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      Copy JSON results
                    </>
                  )}
                </button>
              </div>
            )}

            {/* Results History Stack */}
            {viewedResults.length > 0 && (
              <div className="mt-6 border-t pt-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                  Results History ({viewedResults.length})
                </h4>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {viewedResults.map((result) => (
                    <div
                      key={result.submissionId}
                      className="bg-gray-50 rounded-lg p-3 border border-gray-200 hover:border-blue-300 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-gray-900 truncate">
                              {result.patientId}
                            </span>
                            <span className="text-xs text-gray-500">
                              • {result.templateName}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500 mt-1 flex items-center gap-3 flex-wrap">
                            <span>{result.timestamp.toLocaleTimeString()}</span>
                            {result.metrics.transcriptionTime && (
                              <span>🎙️ {result.metrics.transcriptionTime.toFixed(1)}s</span>
                            )}
                            {result.metrics.extractionTime && (
                              <span>⚡ {result.metrics.extractionTime.toFixed(1)}s</span>
                            )}
                            {result.audioQuality && (
                              <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs ${
                                result.audioQuality.overall_quality === 'good'
                                  ? 'bg-green-100 text-green-700'
                                  : result.audioQuality.overall_quality === 'fair'
                                  ? 'bg-amber-100 text-amber-700'
                                  : result.audioQuality.overall_quality === 'poor'
                                  ? 'bg-red-100 text-red-700'
                                  : 'bg-gray-100 text-gray-600'
                              }`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${
                                  result.audioQuality.overall_quality === 'good'
                                    ? 'bg-green-500'
                                    : result.audioQuality.overall_quality === 'fair'
                                    ? 'bg-amber-500'
                                    : result.audioQuality.overall_quality === 'poor'
                                    ? 'bg-red-500'
                                    : 'bg-gray-400'
                                }`} />
                                {result.audioQuality.overall_quality}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 ml-2">
                          <button
                            onClick={() => handleLoadViewedResult(result.submissionId)}
                            className="p-1.5 text-blue-600 hover:bg-blue-50 rounded"
                            title="Load this result"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                          </button>
                          <button
                            onClick={() => handleRemoveViewedResult(result.submissionId)}
                            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded"
                            title="Remove from history"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Empty State */}
            {!loadingCore && !coreExtractionData && !additionalExtractionData && !error && !isRecording && !isSubmitting && viewedResults.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                <svg className="w-16 h-16 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="font-medium">No extraction yet</p>
                <p className="text-sm mt-1">Record audio or upload a file to begin</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Background Processing Status Bar */}
      <BackgroundProcessingStatus sessions={backgroundSessions} />

      {/* Extraction Notifications */}
      <ExtractionNotifications
        notifications={notifications}
        onView={handleViewResults}
        onDismiss={handleDismissNotification}
      />

      {/* Emotion Analysis Modal */}
      <EmotionAnalysisModal
        isOpen={showEmotionModal}
        onClose={() => setShowEmotionModal(false)}
        data={emotionData}
        extractionId={currentExtractionId}
        onRefresh={currentExtractionId ? () => handleOpenEmotionModal(currentExtractionId) : undefined}
      />

      {/* Triage Suggestions Modal */}
      <TriageSuggestionsModal
        isOpen={showTriageModal}
        onClose={() => setShowTriageModal(false)}
        data={triageData}
        extractionId={currentExtractionId}
        onRefresh={currentExtractionId ? () => handleOpenTriageModal(currentExtractionId, true) : undefined}
        doctorId={selectedCounsellorId}
        enableFeedback={true}
      />

      {/* Interventions Modal */}
      <InterventionsModal
        isOpen={showInterventionsModal}
        onClose={() => setShowInterventionsModal(false)}
        interventions={interventionsData.interventions}
        loading={interventionsData.loading}
        error={interventionsData.error}
        extractionId={currentExtractionId}
        onRefresh={currentExtractionId ? () => handleOpenInterventionsModal(currentExtractionId) : undefined}
        insightsEnabled={interventionsData.insightsEnabled}
      />

      {/* Recording History Modal */}
      {(selectedCounsellorId || selectedAssistantId) && (
        <RecordingHistoryModal
          isOpen={showRecordingHistoryModal}
          onClose={() => setShowRecordingHistoryModal(false)}
          doctorId={recordingHistorySource === 'doctor' ? selectedCounsellorId || undefined : undefined}
          nurseId={recordingHistorySource === 'nurse' ? selectedAssistantId || undefined : undefined}
          templates={activatedTemplates}
          processingModes={processingModes}
          accessToken={getAccessToken()}
          onReprocessStarted={(info: ReprocessStartedInfo) => {
            console.log(`[VHR] Reprocess started: submission=${info.submissionId}, session=${info.sessionId}, template=${info.templateName}`);

            // Create background session for progress tracking
            const backgroundSession: BackgroundSession = {
              submissionId: info.submissionId,
              patientId: info.patientId,
              templateName: `${info.templateName} (Reprocess)`,
              status: 'processing',
              progress: 0,
              startedAt: new Date(),
              templateContext: {
                templateCode: info.templateCode,
                consultationTypeCode: info.consultationTypeCode,
                doctorId: selectedCounsellorId || '',
              },
            };

            // Add to background sessions and start Realtime listener
            addBackgroundSession(backgroundSession);

            // Close the modal
            setShowRecordingHistoryModal(false);
          }}
        />
      )}

      {/* Audio Playback by ID Modal */}
      <AudioPlaybackByIdModal
        isOpen={showAudioPlaybackModal}
        onClose={() => setShowAudioPlaybackModal(false)}
        accessToken={getAccessToken()}
      />

      {/* EHR Payload Preview Modal */}
      {showPayloadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col mx-4">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  {payloadData.payloadType === 'raster' ? 'Raster EMR Payload' : payloadData.payloadType === 'neopaed' ? 'Neopaed EHR Payload' : payloadData.payloadType === 'kg' ? 'KG School EHR Payload' : 'Aosta EHR Payload'}
                </h2>
                {payloadData.templateCode && (
                  <p className="text-sm text-gray-500">Template: {payloadData.templateCode}</p>
                )}
              </div>
              <button
                onClick={() => {
                  setShowPayloadModal(false);
                  setPayloadData({ loading: false });
                }}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {payloadData.loading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <span className="ml-3 text-gray-600">Loading payload...</span>
                </div>
              ) : payloadData.error ? (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                  {payloadData.error}
                </div>
              ) : payloadData.payload ? (
                <div className="space-y-4">
                  {/* Copy Button */}
                  <div className="flex justify-end">
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(JSON.stringify(payloadData.payload, null, 2));
                      }}
                      className="flex items-center gap-2 px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      Copy JSON
                    </button>
                  </div>
                  {/* JSON Display */}
                  <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm font-mono whitespace-pre-wrap">
                    {JSON.stringify(payloadData.payload, null, 2)}
                  </pre>
                </div>
              ) : (
                <div className="text-gray-500 text-center py-12">No payload data available</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Realtime Extraction Response Modal (auto-shows when result received via WebSocket) */}
      {showRealtimeModal && realtimeExtractionResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col mx-4">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-emerald-50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-emerald-500 rounded-full flex items-center justify-center">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Realtime Response Received</h2>
                  <p className="text-sm text-emerald-600">
                    via Supabase Realtime at {realtimeExtractionResult.receivedAt.toLocaleTimeString()}
                  </p>
                </div>
              </div>
              <button
                onClick={handleCloseRealtimeModal}
                className="p-2 hover:bg-emerald-100 rounded-lg transition-colors"
              >
                <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* Submission Info */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Submission ID:</span>
                    <p className="font-mono text-gray-900 truncate">{realtimeExtractionResult.submissionId}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Status:</span>
                    <p className="text-emerald-600 font-medium">
                      {(realtimeExtractionResult.response?.response as Record<string, unknown>)?.status as string || 'RECEIVED'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Info Banner */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800 flex items-start gap-2">
                <svg className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>
                  This is what EHR clients receive via Supabase Realtime WebSocket subscription to <code className="bg-blue-100 px-1 rounded">realtime_extraction_responses</code> table.
                </span>
              </div>

              {/* Result JSON */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-gray-700">Full Payload</h3>
                  <button
                    onClick={() => navigator.clipboard.writeText(JSON.stringify(realtimeExtractionResult.response, null, 2))}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    Copy JSON
                  </button>
                </div>
                <pre className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto max-h-80 text-xs">
                  {JSON.stringify(realtimeExtractionResult.response, null, 2)}
                </pre>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end">
              <button
                onClick={handleCloseRealtimeModal}
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 text-sm font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Generic Report View - renders any JSON extraction as a structured report
// ============================================================================

interface GenericReportViewProps {
  template: ActivatedTemplate | null;
  data: Record<string, any>;
  sectionLabel?: string;
}

const SECTION_ICONS: Record<string, string> = {
  patientInformation: '👤',
  chiefComplaints: '📋',
  historyOfPresentIllness: '📝',
  history: '📖',
  examination: '🔍',
  diagnosis: '🏥',
  prescription: '💊',
  investigations: '🔬',
  treatmentPlan: '📌',
  followUp: '📅',
  warnings: '⚠️',
  referralDetails: '🔄',
  emergencyContact: '🚨',
  reportMetadata: 'ℹ️',
};

const SECTION_ORDER = [
  'reportMetadata',
  'patientInformation',
  'chiefComplaints',
  'historyOfPresentIllness',
  'history',
  'examination',
  'diagnosis',
  'prescription',
  'investigations',
  'treatmentPlan',
  'followUp',
  'warnings',
  'referralDetails',
  'emergencyContact',
];

function GenericReportView({ template, data, sectionLabel }: GenericReportViewProps) {
  if (!data || Object.keys(data).length === 0) {
    return <div className="text-sm text-gray-500">No structured data available to render.</div>;
  }

  // Sort entries by SECTION_ORDER, unknown sections go to end
  const entries = Object.entries(data).sort(([a], [b]) => {
    const ai = SECTION_ORDER.indexOf(a);
    const bi = SECTION_ORDER.indexOf(b);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });

  return (
    <div className="space-y-4 text-sm text-gray-900">
      {/* Header */}
      <div className="border-b-2 border-gray-200 pb-3">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          {template?.consultation_type_name || 'Medical Session'}
        </div>
        <div className="text-base font-bold text-gray-900 mt-0.5">
          {template?.template_name || 'Session Report'}
          {sectionLabel && <span className="text-gray-400 font-normal ml-2">— {sectionLabel}</span>}
        </div>
      </div>

      {/* Sections */}
      <div className="space-y-3">
        {entries.map(([key, value]) => (
          <ReportSection key={key} sectionKey={key} value={value} />
        ))}
      </div>
    </div>
  );
}

function ReportSection({ sectionKey, value }: { sectionKey: string; value: any }) {
  const icon = SECTION_ICONS[sectionKey] || '📄';
  const title = formatSectionTitle(sectionKey);

  // Skip null/empty sections
  if (value === null || value === undefined) return null;
  if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0) return null;
  if (Array.isArray(value) && value.length === 0) return null;

  return (
    <section className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 px-4 py-2.5 border-b border-gray-200">
        <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wide flex items-center gap-1.5">
          <span>{icon}</span> {title}
        </h4>
      </div>
      <div className="px-4 py-3 bg-white">
        <ReportValue value={value} depth={0} />
      </div>
    </section>
  );
}

function ReportValue({ value, depth }: { value: any; depth: number }) {
  if (value === null || value === undefined || value === 'N/A') {
    return <span className="text-gray-400 italic text-xs">Not documented</span>;
  }

  if (typeof value === 'string') {
    // Check if it's a JSON string (like safety_summary)
    if (value.startsWith('{') || value.startsWith('[')) {
      try {
        const parsed = JSON.parse(value);
        return <ReportValue value={parsed} depth={depth} />;
      } catch {
        // Not JSON, render as string
      }
    }
    return <span className="text-gray-800 leading-relaxed">{value}</span>;
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return <span className="text-gray-800 font-medium">{String(value)}</span>;
  }

  // Array of strings (like chiefComplaints, when_to_seek_care)
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-gray-400 italic text-xs">None</span>;
    }

    // Array of primitives → bullet list
    if (typeof value[0] === 'string' || typeof value[0] === 'number') {
      return (
        <ul className="space-y-1">
          {value.map((item, idx) => (
            <li key={idx} className="flex items-start gap-2">
              <span className="text-gray-400 mt-0.5">•</span>
              <span className="text-gray-800">{String(item)}</span>
            </li>
          ))}
        </ul>
      );
    }

    // Array of objects (like diagnosis, medications) → table or cards
    if (typeof value[0] === 'object' && value[0] !== null) {
      const keys = Object.keys(value[0]);

      // If objects are small (≤5 keys), render as a table
      if (keys.length <= 5 && keys.length > 1) {
        return (
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr>
                  {keys.map(k => (
                    <th key={k} className="text-left px-3 py-2 bg-gray-50 font-semibold text-gray-600 uppercase tracking-wide border-b border-gray-200">
                      {formatSectionTitle(k)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {value.map((row: Record<string, any>, idx: number) => (
                  <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
                    {keys.map(k => (
                      <td key={k} className="px-3 py-2 text-gray-800 border-b border-gray-100">
                        {row[k] === 'N/A' ? <span className="text-gray-400 italic">N/A</span> : String(row[k] ?? '')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }

      // Larger objects → render as cards
      return (
        <div className="space-y-2">
          {value.map((item: Record<string, any>, idx: number) => (
            <div key={idx} className="border border-gray-100 rounded-md p-3 bg-gray-50/50">
              <ReportValue value={item} depth={depth + 1} />
            </div>
          ))}
        </div>
      );
    }
  }

  // Object → key-value pairs
  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value).filter(([, v]) => v !== null && v !== undefined);
    if (entries.length === 0) {
      return <span className="text-gray-400 italic text-xs">No details</span>;
    }

    // For nested objects at depth > 0, use a compact layout
    if (depth > 0) {
      return (
        <div className="space-y-2">
          {entries.map(([k, v]) => (
            <div key={k}>
              <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">
                {formatSectionTitle(k)}
              </div>
              <div className="text-gray-800 text-sm">
                <ReportValue value={v} depth={depth + 1} />
              </div>
            </div>
          ))}
        </div>
      );
    }

    // Top-level object fields in a section → grid layout
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
        {entries.map(([k, v]) => {
          // Long text values get full width
          const isLongText = typeof v === 'string' && v.length > 100;
          const isComplex = typeof v === 'object' && v !== null;
          const fullWidth = isLongText || isComplex;

          return (
            <div key={k} className={fullWidth ? 'md:col-span-2' : ''}>
              <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">
                {formatSectionTitle(k)}
              </div>
              <div className="text-gray-800 text-sm">
                <ReportValue value={v} depth={depth + 1} />
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return <span className="text-gray-800">{String(value)}</span>;
}

// ============================================================================

interface OphthalHtmlViewProps {
  template: ActivatedTemplate | null;
  coreData: Record<string, any> | null;
  additionalData: Record<string, any> | null;
}

function OphthalHtmlView({ template, coreData, additionalData }: OphthalHtmlViewProps) {
  const merged: Record<string, any> = {
    ...(coreData || {}),
    ...(additionalData || {}),
  };

  const entries = Object.entries(merged);

  if (entries.length === 0) {
    return (
      <div className="text-sm text-gray-500">
        No structured data available to render.
      </div>
    );
  }

  return (
    <div className="space-y-4 text-sm text-gray-900">
      <div className="border-b pb-2">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          {template?.consultation_type_name || 'Ophthalmology'}
        </div>
        <div className="text-base font-semibold text-gray-900">
          {template?.template_name || 'Session Summary'}
        </div>
      </div>

      <div className="space-y-3">
        {entries.map(([key, value]) => (
          <section key={key} className="border border-gray-100 rounded-md p-3 bg-gray-50">
            <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
              {formatSectionTitle(key)}
            </h4>
            <div className="text-sm text-gray-900">
              {renderSectionValue(value)}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function formatSectionTitle(key: string): string {
  const normalized = key.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function renderSectionValue(value: any) {
  if (value == null) {
    return <span className="text-gray-500">Not documented</span>;
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return <span>{String(value)}</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-gray-500">No items</span>;
    }

    if (typeof value[0] === 'string' || typeof value[0] === 'number' || typeof value[0] === 'boolean') {
      return (
        <ul className="list-disc list-inside space-y-0.5">
          {value.map((item, idx) => (
            <li key={idx}>{String(item)}</li>
          ))}
        </ul>
      );
    }

    return (
      <div className="space-y-2">
        {value.map((item, idx) => (
          <div key={idx} className="border border-gray-200 rounded p-2 bg-white">
            {renderObjectValue(item)}
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === 'object') {
    return renderObjectValue(value as Record<string, any>);
  }

  return <span>{String(value)}</span>;
}

function renderObjectValue(obj: Record<string, any>) {
  const entries = Object.entries(obj || {});
  if (entries.length === 0) {
    return <span className="text-gray-500">No details</span>;
  }

  return (
    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="flex flex-col mb-1">
          <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            {formatSectionTitle(k)}
          </dt>
          <dd className="text-gray-900 mt-0.5">
            {typeof v === 'object' && v !== null ? renderSectionValue(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function generateHtmlFromData(data: Record<string, any>, template: ActivatedTemplate | null): string {
  const sectionOrder = [
    'reportMetadata', 'patientInformation', 'chiefComplaints', 'historyOfPresentIllness',
    'history', 'examination', 'diagnosis', 'prescription', 'investigations',
    'treatmentPlan', 'followUp', 'warnings', 'referralDetails', 'emergencyContact',
  ];
  const sectionIcons: Record<string, string> = {
    patientInformation: '&#x1F464;', chiefComplaints: '&#x1F4CB;', historyOfPresentIllness: '&#x1F4DD;',
    history: '&#x1F4D6;', examination: '&#x1F50D;', diagnosis: '&#x1F3E5;', prescription: '&#x1F48A;',
    investigations: '&#x1F52C;', treatmentPlan: '&#x1F4CC;', followUp: '&#x1F4C5;', warnings: '&#x26A0;&#xFE0F;',
    referralDetails: '&#x1F504;', emergencyContact: '&#x1F6A8;', reportMetadata: '&#x2139;&#xFE0F;',
  };

  const entries = Object.entries(data).sort(([a], [b]) => {
    const ai = sectionOrder.indexOf(a);
    const bi = sectionOrder.indexOf(b);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });

  if (entries.length === 0) {
    return `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Medical Record</title></head>
      <body style="font-family: Arial, sans-serif; padding: 20px;"><p style="color: #999;">No data available.</p></body></html>`;
  }

  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const renderValue = (value: any, depth: number = 0): string => {
    if (value === null || value === undefined || value === 'N/A') {
      return '<span style="color: #9ca3af; font-style: italic; font-size: 12px;">Not documented</span>';
    }
    if (typeof value === 'string') {
      // Try parsing JSON strings
      if (value.startsWith('{') || value.startsWith('[')) {
        try { return renderValue(JSON.parse(value), depth); } catch { /* not JSON */ }
      }
      return `<span style="color: #1f2937; line-height: 1.6;">${esc(value)}</span>`;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return `<span style="color: #1f2937; font-weight: 500;">${String(value)}</span>`;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) return '<span style="color: #9ca3af; font-style: italic; font-size: 12px;">None</span>';
      // Array of primitives → bullet list
      if (typeof value[0] === 'string' || typeof value[0] === 'number') {
        return `<ul style="margin: 0; padding-left: 0; list-style: none;">${value.map(item =>
          `<li style="padding: 3px 0; color: #1f2937;">&#x2022; ${esc(String(item))}</li>`
        ).join('')}</ul>`;
      }
      // Array of objects → table
      if (typeof value[0] === 'object' && value[0] !== null) {
        const keys = Object.keys(value[0]);
        if (keys.length <= 5 && keys.length > 1) {
          return `<table style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <thead><tr>${keys.map(k => `<th style="text-align: left; padding: 6px 10px; background: #f3f4f6; font-size: 10px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid #e5e7eb;">${esc(formatSectionTitle(k))}</th>`).join('')}</tr></thead>
            <tbody>${value.map((row: Record<string, any>, i: number) =>
              `<tr style="background: ${i % 2 === 0 ? '#fff' : '#f9fafb'};">${keys.map(k =>
                `<td style="padding: 6px 10px; color: #1f2937; border-bottom: 1px solid #f3f4f6;">${row[k] === 'N/A' ? '<span style="color: #9ca3af; font-style: italic;">N/A</span>' : esc(String(row[k] ?? ''))}</td>`
              ).join('')}</tr>`
            ).join('')}</tbody></table>`;
        }
        return value.map(item => `<div style="border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; margin-bottom: 8px; background: #fafafa;">${renderValue(item, depth + 1)}</div>`).join('');
      }
    }
    if (typeof value === 'object' && value !== null) {
      const objEntries = Object.entries(value).filter(([, v]) => v !== null && v !== undefined);
      if (objEntries.length === 0) return '<span style="color: #9ca3af; font-style: italic; font-size: 12px;">No details</span>';
      const gridCols = depth > 0 ? '1fr' : 'repeat(2, 1fr)';
      return `<div style="display: grid; grid-template-columns: ${gridCols}; gap: 12px 24px;">
        ${objEntries.map(([k, v]) => {
          const isLong = typeof v === 'string' && v.length > 100;
          const isComplex = typeof v === 'object' && v !== null;
          const span = (isLong || isComplex) && depth === 0 ? 'grid-column: span 2;' : '';
          return `<div style="${span}">
            <div style="font-size: 10px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">${esc(formatSectionTitle(k))}</div>
            <div style="font-size: 13px; color: #1f2937;">${renderValue(v, depth + 1)}</div>
          </div>`;
        }).join('')}</div>`;
    }
    return `<span>${esc(String(value))}</span>`;
  };

  const sectionsHtml = entries
    .filter(([, value]) => {
      if (value === null || value === undefined) return false;
      if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0) return false;
      if (Array.isArray(value) && value.length === 0) return false;
      return true;
    })
    .map(([key, value]) => {
      const icon = sectionIcons[key] || '&#x1F4C4;';
      return `<section style="border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; margin-bottom: 16px;">
        <div style="background: #f8fafc; padding: 10px 16px; border-bottom: 1px solid #e5e7eb;">
          <h4 style="font-size: 11px; font-weight: 700; color: #374151; text-transform: uppercase; letter-spacing: 0.5px; margin: 0;">${icon} ${esc(formatSectionTitle(key))}</h4>
        </div>
        <div style="padding: 14px 16px; font-size: 14px; color: #1f2937; background: #fff;">
          ${renderValue(value, 0)}
        </div>
      </section>`;
    }).join('');

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${esc(template?.consultation_type_name || 'Medical Record')} - ${esc(template?.template_name || 'Session Report')}</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; padding: 24px; background: #fff; color: #1f2937; max-width: 900px; margin: 0 auto; }
    @media print { body { padding: 10px; } section { page-break-inside: avoid; } }
  </style>
</head>
<body>
  <div style="border-bottom: 2px solid #e5e7eb; padding-bottom: 14px; margin-bottom: 20px;">
    <div style="font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">
      ${esc(template?.consultation_type_name || 'Medical Session')}
    </div>
    <div style="font-size: 20px; font-weight: 700; color: #111827; margin-top: 4px;">
      ${esc(template?.template_name || 'Session Report')}
    </div>
  </div>
  ${sectionsHtml}
</body>
</html>`;
}

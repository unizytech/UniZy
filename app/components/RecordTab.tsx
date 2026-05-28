'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { startLiveTranscriptionSession } from '../services/geminiClient';
import type { LiveSessionManager, ProcessingMode, ActivatedTemplate, ExtractionMode, MedicalExtractionResponse } from "@lib/types";
import { extractMedicalSummary, handleApiError, getActivatedTemplates, getProcessingModes } from "@lib/summaryApi";
import { searchPatients, type PatientSearchResult } from "@lib/patientHistoryApi";
import DoctorSelector from './DoctorSelector';
import { useAuth } from '@lib/auth';
import { authPost } from '@lib/apiClient';

// Icons
const MicIcon = ({ className }: { className: string }) => (
  <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Zm0 12a5 5 0 0 1-5-5V5a5 5 0 0 1 10 0v6a5 5 0 0 1-5 5Z" />
    <path d="M10 19a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-3.1a7 7 0 0 0 6-6.9v-1a1 1 0 1 0-2 0v1a5 5 0 0 1-10 0v-1a1 1 0 1 0-2 0v1a7 7 0 0 0 6 6.9V19Z" />
  </svg>
);

const StopIcon = ({ className }: { className: string }) => (
  <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
    <path d="M7 7h10v10H7z" />
  </svg>
);

const PauseIcon = ({ className }: { className: string }) => (
  <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" transform="rotate(90 12 12)"/>
    <rect x="6" y="4" width="4" height="16" />
    <rect x="14" y="4" width="4" height="16" />
  </svg>
);

const PlayIcon = ({ className }: { className: string }) => (
  <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
);

// Helper components
const TranscriptionDisplay = ({ transcription, placeholder }: { transcription: string; placeholder: string }) => (
  <div className="w-full bg-slate-800 rounded-lg p-4 h-64 lg:h-80 relative flex-grow">
    <textarea
      readOnly
      value={transcription}
      placeholder={placeholder}
      className="w-full h-full bg-transparent text-slate-300 resize-none focus:outline-none"
    />
  </div>
);

const ErrorDisplay = ({ error }: { error: string | null }) => {
    if (!error) return null;
    return (
        <div className="w-full bg-red-900/50 text-red-300 border border-red-700 rounded-lg p-3 mt-4 text-center">
            <p>{error}</p>
        </div>
    );
};

const InsightsDisplay = ({
    insights,
    isExtracting,
    extractionTime
}: {
    insights: any | null,
    isExtracting: boolean,
    extractionTime: number | null
}) => {
    if (!isExtracting && !insights) return null;

    return (
        <div className="mt-6 w-full">
            <h3 className="text-xl font-semibold text-center mb-3 text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400">
                Medical Insights Extraction (Gemini 2.5 Pro)
            </h3>

            {/* Processing Status */}
            <div className="w-full bg-slate-800 rounded-lg p-4 mb-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center">
                        {isExtracting ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400 mr-2"></div>
                        ) : insights ? (
                            <svg className="w-4 h-4 mr-2 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                        ) : null}
                        <span className="text-slate-400 text-sm">Insights Extraction</span>
                    </div>
                    {extractionTime && <span className="text-xs text-slate-500">{extractionTime}s</span>}
                </div>
            </div>

            {/* Results Display */}
            {insights && (
                <div className="bg-slate-800 rounded-lg p-4">
                    <h4 className="text-lg font-semibold text-slate-200 mb-2 flex items-center justify-between">
                        <span>Medical Insights</span>
                        {extractionTime && <span className="text-xs text-slate-400">{extractionTime}s</span>}
                    </h4>
                    <div className="bg-slate-900 rounded p-3 h-96 overflow-auto">
                        {isExtracting ? (
                            <div className="flex justify-center items-center h-full">
                                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
                                <p className="ml-4 text-slate-400">Extracting...</p>
                            </div>
                        ) : (
                            <pre className="text-xs text-slate-300 whitespace-pre-wrap">
                                {insights?.error
                                    ? `Error: ${insights.error}`
                                    : JSON.stringify(insights, null, 2)}
                            </pre>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default function RecordTab() {
    // Auth
    const { getAccessToken } = useAuth();

    // Doctor selection
    const [selectedDoctorId, setSelectedDoctorId] = useState<string | null>(null);

    // Patient selection
    const [patientId, setPatientId] = useState<string>('');
    const [patientsList, setPatientsList] = useState<PatientSearchResult[]>([]);
    const [loadingPatients, setLoadingPatients] = useState(false);

    // Template selection
    const [selectedTemplate, setSelectedTemplate] = useState<ActivatedTemplate | null>(null);
    const [activatedTemplates, setActivatedTemplates] = useState<ActivatedTemplate[]>([]);
    const [loadingTemplates, setLoadingTemplates] = useState(false);

    // Processing mode selection - Live screen only allows ultra/ultra_fast
    const [processingMode, setProcessingMode] = useState<string>('ultra');
    const [processingModes, setProcessingModes] = useState<ProcessingMode[]>([]);
    const [loadingProcessingModes, setLoadingProcessingModes] = useState(false);

    // Extraction mode selection
    const [extractionMode, setExtractionMode] = useState<ExtractionMode>('full');

    // Recording state
    const [isRecording, setIsRecording] = useState(false);
    const [isPaused, setIsPaused] = useState(false);
    const [nativeTranscript, setNativeTranscript] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [status, setStatus] = useState('Select doctor and template to start recording');

    // Extraction state (NEW: structured segment data)
    const [coreExtractionData, setCoreExtractionData] = useState<MedicalExtractionResponse | null>(null);
    const [additionalExtractionData, setAdditionalExtractionData] = useState<MedicalExtractionResponse | null>(null);
    const [loadingCore, setLoadingCore] = useState(false);
    const [loadingAdditional, setLoadingAdditional] = useState(false);
    const [coreExtractionTime, setCoreExtractionTime] = useState<number | null>(null);
    const [additionalExtractionTime, setAdditionalExtractionTime] = useState<number | null>(null);

    // ⭐ Submission ID for linking extraction to recording session
    const [submissionId, setSubmissionId] = useState<string | null>(null);

    // ⭐ Live API session timing for usage tracking
    const [sessionStartTime, setSessionStartTime] = useState<number | null>(null);

    const sessionManagerRef = useRef<LiveSessionManager | null>(null);

    // ⭐ Backend-generated correlation_id for audio chunk upload during recording
    // Received from first /live/chunk response, used for subsequent chunks
    const correlationIdRef = useRef<string | null>(null);

    const handleTranscriptionUpdate = useCallback(async (text: string, isFinal: boolean) => {
        if (text) {
            // Add text to state for real-time display
            setNativeTranscript(prev => prev + text);
        }

        if (isFinal) {
            // Just add a space after completed turn, no translation yet
            setNativeTranscript(prev => prev.trim() + ' ');
        }
    }, []);

    // ⭐ Audio chunk upload callback - uploads chunks to backend in parallel with Gemini streaming
    // This enables audio emotion analysis for RecordTab sessions
    // Also triggers parallel prompt generation on first chunk (saves ~1.2-1.8s)
    const uploadLiveChunk = useCallback(async (
        chunkData: string,
        chunkIndex: number
    ): Promise<void> => {
        // For subsequent chunks, we need the correlation_id from the first chunk response
        if (chunkIndex > 0 && !correlationIdRef.current) {
            console.warn('[RecordTab] Cannot upload chunk - missing correlation_id from first chunk');
            return;
        }

        try {
            // Build payload - first chunk does NOT send correlation_id (backend generates it)
            const payload: Record<string, unknown> = {
                chunk_index: chunkIndex,
                audio_data: chunkData,
                mime_type: 'audio/pcm;rate=16000',
            };

            // Only send correlation_id for subsequent chunks (not first)
            if (chunkIndex > 0) {
                payload.correlation_id = correlationIdRef.current;
            }

            // PARALLEL PROMPT GENERATION: Send context with first chunk only
            // This allows backend to start generating prompts while recording continues
            if (chunkIndex === 0 && selectedDoctorId && selectedTemplate) {
                payload.doctor_id = selectedDoctorId;
                payload.template_code = selectedTemplate.template_code;
                if (patientId?.trim()) {
                    payload.patient_id = patientId.trim();
                }
                console.log('[RecordTab] First chunk - sending context for parallel prompt generation');
            }

            const response = await authPost('/api/v1/option1/recording/live/chunk', getAccessToken(), payload);

            // Store correlation_id from backend on first chunk
            if (chunkIndex === 0) {
                const data = await response.json();
                if (data?.correlation_id) {
                    correlationIdRef.current = data.correlation_id;
                    console.log('[RecordTab] Received correlation_id from backend:', data.correlation_id);
                }
            }

            console.log(`[RecordTab] ✓ Uploaded chunk ${chunkIndex}`);
        } catch (err) {
            // Non-fatal - emotion analysis will be skipped if chunks fail
            console.warn('[RecordTab] Chunk upload failed (non-fatal):', err);
        }
    }, [getAccessToken, selectedDoctorId, selectedTemplate, patientId]);

    const startRecording = useCallback(async () => {
        setError(null);
        setNativeTranscript('');
        setCoreExtractionData(null);
        setAdditionalExtractionData(null);
        setLoadingCore(false);
        setLoadingAdditional(false);
        setCoreExtractionTime(null);
        setAdditionalExtractionTime(null);
        setSessionStartTime(Date.now());  // Track session start for usage logging

        // Reset correlation_id - will be received from backend on first chunk
        correlationIdRef.current = null;

        setStatus('Requesting secure ephemeral token...');

        try {
            // Fetch ephemeral token from backend
            const tokenResponse = await authPost(
                '/api/ephemeral-token',
                getAccessToken(),
                {}
            );

            if (!tokenResponse.ok) {
                throw new Error('Failed to obtain ephemeral token from backend');
            }

            const tokenData = await tokenResponse.json();
            const ephemeralToken = tokenData.token;

            console.log('[RecordTab] Ephemeral token obtained, expires in', tokenData.expires_in, 'seconds (12 minutes)');

            setStatus('Connecting to Gemini Live session...');

            sessionManagerRef.current = await startLiveTranscriptionSession(
                handleTranscriptionUpdate,
                (err) => {
                    setStatus('Error occurred. Please try again.');
                    setError(err.message);
                    setIsRecording(false);
                },
                () => {
                    setStatus('Listening... Speak now!');
                },
                ephemeralToken,  // Pass the ephemeral token
                undefined,       // resumeHandle
                uploadLiveChunk  // ⭐ Audio chunk upload callback for emotion analysis
            );
            setIsRecording(true);
        } catch (err) {
            setStatus('Failed to connect. Please try again.');
            setError((err as Error).message);
            setIsRecording(false);
        }
    }, [handleTranscriptionUpdate, uploadLiveChunk, getAccessToken]);

    const togglePause = useCallback(() => {
        if (!sessionManagerRef.current) return;

        if (isPaused) {
            // Resume
            sessionManagerRef.current.resume();
            setIsPaused(false);
            setStatus('Listening... Speak now!');
            console.log('[RecordTab] Recording resumed');
        } else {
            // Pause
            sessionManagerRef.current.pause();
            setIsPaused(true);
            setStatus('Recording paused');
            console.log('[RecordTab] Recording paused');
        }
    }, [isPaused]);

    const stopRecording = useCallback(async () => {
        setIsRecording(false);
        setIsPaused(false);  // Reset pause state when stopping
        setStatus('Recording stopped. Finalizing audio stream...');

        // Calculate session duration for usage tracking
        const sessionEndTime = Date.now();
        const sessionDurationSeconds = sessionStartTime
            ? (sessionEndTime - sessionStartTime) / 1000
            : 0;

        // Wait 4 seconds before actually closing the session to ensure full audio is captured
        await new Promise(resolve => setTimeout(resolve, 4000));

        if (sessionManagerRef.current) {
            sessionManagerRef.current.close();
            sessionManagerRef.current = null;
        }

        // Get the complete native transcript
        const finalNativeText = nativeTranscript.trim();

        // ⭐ Log Live API usage (fire-and-forget, don't block extraction)
        if (sessionDurationSeconds > 0) {
            authPost('/api/v1/usage/live-api', getAccessToken(), {
                model: 'gemini-2.5-flash-native-audio-preview-09-2025',
                session_duration_seconds: sessionDurationSeconds,
                audio_duration_seconds: sessionDurationSeconds - 4, // Subtract 4s finalization wait
                doctor_id: selectedDoctorId,
                consultation_type_code: selectedTemplate?.consultation_type_code,
                template_code: selectedTemplate?.template_code,
            }).then(res => {
                if (res.ok) {
                    console.log('[RecordTab] ✓ Live API usage logged');
                } else {
                    console.warn('[RecordTab] Failed to log Live API usage');
                }
            }).catch(err => {
                console.warn('[RecordTab] Error logging Live API usage:', err);
            });
        }

        if (!finalNativeText) {
            setStatus('Recording stopped. No transcript to analyze.');
            return;
        }

        if (!selectedTemplate || !selectedDoctorId) {
            setError('Doctor and template selection required for extraction');
            setStatus('Recording stopped. Select doctor and template.');
            return;
        }

        // ⭐ STEP 1: Create live session for database tracking
        try {
            setStatus('Creating session...');
            console.log('[RecordTab] Creating live session for database tracking');

            const sessionResponse = await authPost(
                '/api/v1/option1/recording/live/session',
                getAccessToken(),
                {
                    doctor_id: selectedDoctorId,
                    patient_id: patientId.trim() || 'LIVE_RECORDING',  // Use selected patient or fallback
                    template_code: selectedTemplate.template_code,  // Template code for DB lookups (unique identifier)
                    template_name: selectedTemplate.template_name,  // Display name for readability
                    processing_mode: processingMode,
                    correlation_id: correlationIdRef.current,  // ⭐ Backend-generated correlation_id from first /live/chunk
                }
            );

            if (!sessionResponse.ok) {
                throw new Error('Failed to create live session');
            }

            const sessionData = await sessionResponse.json();
            // Note: /live/session returns correlation_id, which IS the submission_id for live sessions
            const newSubmissionId = sessionData.correlation_id;
            setSubmissionId(newSubmissionId);

            console.log('[RecordTab] ✓ Live session created:', sessionData.session_id);
            console.log('[RecordTab] Submission ID:', newSubmissionId);

            // ⭐ STEP 2: Progressive extraction with submission_id
            await handleProgressiveExtraction(finalNativeText, newSubmissionId);

        } catch (err) {
            console.error('[RecordTab] Failed to create live session:', err);
            setError('Failed to create session. Extraction skipped.');
            setStatus('Session creation failed. Click to start a new recording.');
        }
    }, [nativeTranscript, selectedTemplate, selectedDoctorId, patientId, processingMode, extractionMode, sessionStartTime]);

    // Progressive extraction using new /api/v1/summary/extract endpoint
    const handleProgressiveExtraction = async (transcriptText: string, subId: string) => {
        if (!transcriptText.trim() || !selectedTemplate || !selectedDoctorId) return;

        try {
            setLoadingCore(true);
            setCoreExtractionData(null);
            setAdditionalExtractionData(null);

            console.log('[RecordTab] Starting extraction with submission_id:', subId);
            console.log('[RecordTab] Extraction mode:', extractionMode);

            const startTime = performance.now();

            // ⭐ Option A: Full mode = single call, Additional/Core = progressive
            if (extractionMode === 'full') {
                // FULL mode: Single API call with mode='full' (all segments at once)
                setStatus('Extracting all segments...');
                console.log('[RecordTab] FULL mode - single extraction call');

                const fullResponse = await extractMedicalSummary({
                    transcript: transcriptText.trim(),
                    doctor_id: selectedDoctorId,
                    template_code: selectedTemplate.template_code,  // ⭐ Unique identifier for DB lookups
                    template_name: selectedTemplate.template_name,  // Display name for readability
                    processing_mode: processingMode,
                    mode: 'full',
                    submission_id: subId,  // ⭐ Pass submission_id for DB save
                }, getAccessToken());

                if (!fullResponse.success) {
                    throw new Error('Full extraction failed');
                }

                const fullTime = parseFloat(((performance.now() - startTime) / 1000).toFixed(2));
                setCoreExtractionData(fullResponse); // Display all results in CORE section
                setCoreExtractionTime(fullTime);
                setLoadingCore(false);

                console.log('[RecordTab] FULL extraction completed in', fullTime, 's');
                setStatus('Extraction complete. Click to start a new recording.');

            } else {
                // CORE or ADDITIONAL mode: Progressive loading (CORE first, then ADDITIONAL if needed)
                setStatus('Extracting CORE segments...');
                console.log('[RecordTab] Starting CORE extraction');

                const coreResponse = await extractMedicalSummary({
                    transcript: transcriptText.trim(),
                    doctor_id: selectedDoctorId,
                    template_code: selectedTemplate.template_code,  // ⭐ Unique identifier for DB lookups
                    template_name: selectedTemplate.template_name,  // Display name for readability
                    processing_mode: processingMode,
                    mode: 'core',
                    submission_id: subId,  // ⭐ Pass submission_id for DB save
                }, getAccessToken());

                if (!coreResponse.success) {
                    throw new Error('Core extraction failed');
                }

                const coreTime = parseFloat(((performance.now() - startTime) / 1000).toFixed(2));
                setCoreExtractionData(coreResponse);
                setCoreExtractionTime(coreTime);
                setLoadingCore(false);

                console.log('[RecordTab] CORE extraction completed in', coreTime, 's');
                setStatus('CORE segments extracted. Loading ADDITIONAL...');

                // Step 2: Extract ADDITIONAL segments in background (if extractionMode is 'additional')
                if (extractionMode === 'additional') {
                    extractAdditionalSegments(transcriptText, subId);
                } else {
                    setStatus('Extraction complete. Click to start a new recording.');
                }
            }

        } catch (err) {
            console.error('[RecordTab] Extraction failed:', err);
            setError(handleApiError(err));
            setLoadingCore(false);
            setStatus('Extraction failed. Click to start a new recording.');
        }
    };

    const extractAdditionalSegments = async (transcriptText: string, subId: string) => {
        if (!transcriptText.trim() || !selectedTemplate || !selectedDoctorId) return;

        try {
            setLoadingAdditional(true);

            console.log('[RecordTab] Starting ADDITIONAL extraction with submission_id:', subId);

            const additionalStartTime = performance.now();
            const additionalResponse = await extractMedicalSummary({
                transcript: transcriptText.trim(),
                doctor_id: selectedDoctorId,
                template_code: selectedTemplate.template_code,  // ⭐ Unique identifier for DB lookups
                template_name: selectedTemplate.template_name,  // Display name for readability
                processing_mode: processingMode,
                mode: 'additional',
                submission_id: subId,  // ⭐ Pass submission_id for DB save
            }, getAccessToken());

            if (additionalResponse.success) {
                const additionalTime = parseFloat(((performance.now() - additionalStartTime) / 1000).toFixed(2));
                setAdditionalExtractionData(additionalResponse);
                setAdditionalExtractionTime(additionalTime);
                console.log('[RecordTab] ADDITIONAL extraction completed in', additionalTime, 's');
                setStatus('All segments extracted. Click to start a new recording.');
            }
        } catch (err) {
            console.error('[RecordTab] Additional extraction failed:', err);
            // Don't show error to user - ADDITIONAL is optional
        } finally {
            setLoadingAdditional(false);
        }
    };

    // Load processing modes on mount
    useEffect(() => {
        loadProcessingModesFromDB();
    }, []);

    // Load activated templates when doctor is selected
    useEffect(() => {
        if (selectedDoctorId) {
            loadActivatedTemplatesFromDB();
        } else {
            setActivatedTemplates([]);
            setSelectedTemplate(null);
        }
    }, [selectedDoctorId]);

    // Load patients list when doctor is selected
    useEffect(() => {
        if (selectedDoctorId) {
            loadPatientsList();
        } else {
            setPatientsList([]);
            setPatientId('');
        }
    }, [selectedDoctorId]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (sessionManagerRef.current) {
                sessionManagerRef.current.close();
            }
        };
    }, []);

    const loadProcessingModesFromDB = async () => {
        try {
            setLoadingProcessingModes(true);
            const accessToken = getAccessToken();
            const response = await getProcessingModes(accessToken);

            // Live screen only allows ultra and ultra_fast modes
            const allowedModes = response.processing_modes.filter(
                m => m.mode_code === 'ultra' || m.mode_code === 'ultra_fast'
            );
            setProcessingModes(allowedModes);

            // Auto-select ultra mode if available, otherwise ultra_fast
            const ultraMode = allowedModes.find(m => m.mode_code === 'ultra');
            if (ultraMode) {
                setProcessingMode('ultra');
            } else if (allowedModes.length > 0) {
                setProcessingMode(allowedModes[0].mode_code);
            }
        } catch (err) {
            console.error('[RecordTab] Failed to load processing modes:', err);
        } finally {
            setLoadingProcessingModes(false);
        }
    };

    const loadActivatedTemplatesFromDB = async () => {
        if (!selectedDoctorId) return;

        try {
            setLoadingTemplates(true);
            const accessToken = getAccessToken();
            const response = await getActivatedTemplates(selectedDoctorId, accessToken);
            setActivatedTemplates(response.templates);
            // Auto-select first template
            if (response.templates.length > 0) {
                setSelectedTemplate(response.templates[0]);
            }
        } catch (err) {
            console.error('[RecordTab] Failed to load activated templates:', err);
            setActivatedTemplates([]);
            setSelectedTemplate(null);
        } finally {
            setLoadingTemplates(false);
        }
    };

    const loadPatientsList = async () => {
        if (!selectedDoctorId) return;

        try {
            setLoadingPatients(true);
            const accessToken = getAccessToken();
            // Use searchPatients with empty query to get all patients for this doctor
            const response = await searchPatients('', selectedDoctorId, 1, 100, accessToken);
            console.log('[RecordTab] Loaded patients:', response.total_count);
            setPatientsList(response.patients);
            // Auto-select first patient if available
            if (response.patients.length > 0) {
                setPatientId(response.patients[0].patient_id);
            }
        } catch (err) {
            console.error('[RecordTab] Failed to load patients list:', err);
            setPatientsList([]);
        } finally {
            setLoadingPatients(false);
        }
    };

    const canStartRecording = (): boolean => {
        return Boolean(
            selectedDoctorId &&
            selectedTemplate &&
            processingMode &&
            !isRecording
        );
    };

    return (
        <div className="w-full flex flex-col items-center space-y-4 max-w-4xl mx-auto">
            {/* Doctor Selector */}
            <div className="w-full bg-slate-800 rounded-lg p-4">
                <DoctorSelector
                    selectedDoctorId={selectedDoctorId}
                    onDoctorSelect={setSelectedDoctorId}
                    required={true}
                />
            </div>

            {/* Patient Selector */}
            {selectedDoctorId && (
                <div className="w-full bg-slate-800 rounded-lg p-4">
                    <label className="block text-sm font-medium text-slate-300 mb-3">
                        Patient ID (optional - enables patient context injection)
                    </label>
                    {loadingPatients ? (
                        <div className="flex items-center justify-center py-3">
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-400 mr-2"></div>
                            <span className="text-sm text-slate-400">Loading patients...</span>
                        </div>
                    ) : patientsList.length > 0 ? (
                        <select
                            value={patientId}
                            onChange={(e) => setPatientId(e.target.value)}
                            disabled={isRecording}
                            className="w-full bg-slate-700 text-slate-200 border border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <option value="">No patient (skip context injection)</option>
                            {patientsList.map((patient) => (
                                <option key={patient.id} value={patient.patient_id}>
                                    {patient.patient_id}
                                    {patient.full_name ? ` - ${patient.full_name}` : ''}
                                    {patient.hospital_name ? ` (${patient.hospital_name})` : ''}
                                    {patient.add_info?.roomNo ? ` [Room ${patient.add_info.roomNo}, Bed ${patient.add_info.bedNo}]` : ''}
                                </option>
                            ))}
                        </select>
                    ) : (
                        <input
                            type="text"
                            value={patientId}
                            onChange={(e) => setPatientId(e.target.value)}
                            placeholder="Enter patient ID (e.g., PAT-12345) or leave empty"
                            disabled={isRecording}
                            className="w-full bg-slate-700 text-slate-200 border border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed placeholder-slate-500"
                        />
                    )}
                    <p className="mt-2 text-xs text-slate-500">
                        Select a patient to enable cautions, past prescriptions, and summary context injection
                    </p>
                </div>
            )}

            {/* Template Selector */}
            {selectedDoctorId && (
                <div className="w-full bg-slate-800 rounded-lg p-4">
                    <label className="block text-sm font-medium text-slate-300 mb-3">
                        Activated Template
                    </label>
                    {loadingTemplates ? (
                        <div className="flex items-center justify-center py-3">
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-400 mr-2"></div>
                            <span className="text-sm text-slate-400">Loading templates...</span>
                        </div>
                    ) : activatedTemplates.length === 0 ? (
                        <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-3 text-sm text-yellow-300">
                            No activated templates. Please configure templates in Medical Config.
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {activatedTemplates.map((tmpl) => (
                                <button
                                    key={tmpl.id}
                                    onClick={() => setSelectedTemplate(tmpl)}
                                    disabled={isRecording}
                                    className={`p-3 rounded-lg border-2 text-left transition-all ${
                                        selectedTemplate?.id === tmpl.id
                                            ? 'border-blue-500 bg-blue-900/30 ring-2 ring-blue-400'
                                            : 'border-slate-600 bg-slate-700 hover:border-slate-500'
                                    } ${isRecording ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                                >
                                    <div className="font-medium text-slate-200 text-sm">{tmpl.template_name}</div>
                                    <div className="text-xs text-slate-500 mt-0.5">{tmpl.template_code}</div>
                                    <div className="text-xs text-slate-400 mt-1">{tmpl.consultation_type_name}</div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Processing Mode & Extraction Mode Selectors */}
            {selectedDoctorId && selectedTemplate && (
                <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Processing Mode */}
                    <div className="bg-slate-800 rounded-lg p-4">
                        <label className="block text-sm font-medium text-slate-300 mb-2">
                            Processing Mode
                        </label>
                        {loadingProcessingModes ? (
                            <div className="flex items-center justify-center py-2">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400 mr-2"></div>
                                <span className="text-xs text-slate-400">Loading...</span>
                            </div>
                        ) : (
                            <>
                                <select
                                    value={processingMode}
                                    onChange={(e) => setProcessingMode(e.target.value)}
                                    disabled={isRecording}
                                    className="w-full bg-slate-700 text-slate-200 border border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {processingModes.map((mode) => (
                                        <option key={mode.mode_code} value={mode.mode_code} disabled={!mode.is_active}>
                                            {mode.mode_name}
                                        </option>
                                    ))}
                                </select>
                                {processingModes.find(m => m.mode_code === processingMode) && (
                                    <p className="mt-2 text-xs text-slate-400">
                                        ~{processingModes.find(m => m.mode_code === processingMode)?.estimated_time_seconds}s per extraction
                                    </p>
                                )}
                            </>
                        )}
                    </div>

                    {/* Extraction Mode */}
                    <div className="bg-slate-800 rounded-lg p-4">
                        <label className="block text-sm font-medium text-slate-300 mb-2">
                            Extraction Mode
                        </label>
                        <select
                            value={extractionMode}
                            onChange={(e) => setExtractionMode(e.target.value as ExtractionMode)}
                            disabled={isRecording}
                            className="w-full bg-slate-700 text-slate-200 border border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <option value="core">CORE only (fast, essential segments)</option>
                            <option value="additional">CORE + ADDITIONAL (comprehensive)</option>
                            <option value="full">FULL (all segments)</option>
                        </select>
                        <p className="mt-2 text-xs text-slate-400">
                            {extractionMode === 'core' && 'Essential segments only (~20-30s)'}
                            {extractionMode === 'additional' && 'All segments progressively (~40-60s total)'}
                            {extractionMode === 'full' && 'Complete extraction with all data (~60-90s)'}
                        </p>
                    </div>
                </div>
            )}

            {/* Recording Controls */}
            <div className="flex flex-col items-center gap-2 my-6">
                <div className="flex items-center gap-4">
                    <button
                        onClick={isRecording ? stopRecording : startRecording}
                        disabled={!canStartRecording() && !isRecording}
                        className={`relative w-24 h-24 rounded-full flex items-center justify-center transition-all duration-300 ${
                            isRecording
                                ? 'bg-red-500 hover:bg-red-600 shadow-lg shadow-red-500/50'
                                : canStartRecording()
                                ? 'bg-blue-500 hover:bg-blue-600 shadow-lg shadow-blue-500/50'
                                : 'bg-slate-600 cursor-not-allowed opacity-50'
                        }`}
                        title={!canStartRecording() && !isRecording ? 'Please select doctor, template, and processing mode' : ''}
                    >
                        {isRecording ? <StopIcon className="w-10 h-10 text-white" /> : <MicIcon className="w-10 h-10 text-white" />}
                        {isRecording && <span className="absolute w-full h-full rounded-full bg-red-500 animate-ping opacity-75"></span>}
                    </button>

                {isRecording && (
                    <button
                        onClick={togglePause}
                        className={`w-16 h-16 rounded-full flex items-center justify-center transition-all duration-300 ${
                            isPaused
                                ? 'bg-green-500 hover:bg-green-600 shadow-lg shadow-green-500/50'
                                : 'bg-yellow-500 hover:bg-yellow-600 shadow-lg shadow-yellow-500/50'
                        }`}
                        title={isPaused ? 'Resume' : 'Pause'}
                    >
                        {isPaused ? <PlayIcon className="w-8 h-8 text-white" /> : <PauseIcon className="w-8 h-8 text-white" />}
                    </button>
                )}
                </div>
                <p className="text-slate-400 text-sm text-center">
                    {status}
                </p>
            </div>

            <ErrorDisplay error={error} />

            {/* Live Transcription */}
            <div className="w-full">
                <label className="text-center text-slate-300 mb-2 block font-medium">Live Transcription</label>
                <TranscriptionDisplay
                    transcription={nativeTranscript}
                    placeholder="Your speech will appear here in real-time..."
                />
            </div>

            {/* Structured Extraction Results (NEW) */}
            {(loadingCore || coreExtractionData || additionalExtractionData) && (
                <div className="w-full space-y-4">
                    <h3 className="text-xl font-semibold text-center text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400">
                        Medical Summary Extraction
                    </h3>

                    {/* Metadata */}
                    {(coreExtractionData || additionalExtractionData) && (
                        <div className="bg-slate-800 rounded-lg p-4">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                                <div>
                                    <p className="text-slate-400">Template</p>
                                    <p className="font-semibold text-slate-200">{selectedTemplate?.template_name}</p>
                                    <p className="text-xs text-slate-500 mt-0.5">{selectedTemplate?.template_code}</p>
                                </div>
                                <div>
                                    <p className="text-slate-400">Processing Mode</p>
                                    <p className="font-semibold text-slate-200">
                                        {processingModes.find(m => m.mode_code === processingMode)?.mode_name}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-slate-400">CORE Segments</p>
                                    <p className="font-semibold text-slate-200">
                                        {coreExtractionData ? `${coreExtractionData.metadata.segment_count} ✅` : 'N/A'}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-slate-400">ADDITIONAL</p>
                                    <p className="font-semibold text-slate-200">
                                        {loadingAdditional ? (
                                            <span className="text-blue-400">Loading... ⏳</span>
                                        ) : additionalExtractionData ? (
                                            <span>{additionalExtractionData.metadata.segment_count} ✅</span>
                                        ) : extractionMode === 'core' ? (
                                            <span className="text-slate-500">Skipped</span>
                                        ) : (
                                            <span className="text-slate-500">None</span>
                                        )}
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* CORE Results */}
                    {loadingCore ? (
                        <div className="bg-slate-800 rounded-lg p-8 flex flex-col items-center justify-center">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-blue-400 mb-3"></div>
                            <p className="text-slate-300 font-medium">Extracting CORE segments...</p>
                            <p className="text-sm text-slate-400 mt-2">
                                {processingModes.find(m => m.mode_code === processingMode)?.extraction_model || 'Processing'}
                            </p>
                        </div>
                    ) : coreExtractionData && (
                        <div className="border-2 border-green-500 rounded-lg overflow-hidden">
                            <div className="bg-green-900/30 px-4 py-3 border-b-2 border-green-500 flex items-center justify-between">
                                <div className="flex items-center">
                                    <svg className="w-5 h-5 text-green-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                                    </svg>
                                    <h4 className="font-bold text-green-200">CORE Segments (Essential)</h4>
                                </div>
                                <span className="text-xs text-green-300 font-medium">
                                    {coreExtractionData.metadata.segment_count} segments • {coreExtractionTime}s
                                </span>
                            </div>
                            <div className="p-4 max-h-96 overflow-y-auto bg-slate-900">
                                <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono">
                                    {JSON.stringify(coreExtractionData.insights, null, 2)}
                                </pre>
                            </div>
                        </div>
                    )}

                    {/* ADDITIONAL Results */}
                    {loadingAdditional && (
                        <div className="border-2 border-blue-400 rounded-lg overflow-hidden">
                            <div className="bg-blue-900/30 px-4 py-3 border-b-2 border-blue-400">
                                <h4 className="font-bold text-blue-200">ADDITIONAL Segments (Loading...)</h4>
                            </div>
                            <div className="p-8 bg-slate-900 flex flex-col items-center justify-center">
                                <div className="animate-spin rounded-full h-10 w-10 border-b-4 border-blue-400 mb-3"></div>
                                <p className="text-blue-300 font-medium text-sm">Extracting additional segments...</p>
                                <p className="text-xs text-slate-400 mt-2">CORE results available above</p>
                            </div>
                        </div>
                    )}

                    {!loadingAdditional && additionalExtractionData && (
                        <div className="border-2 border-blue-500 rounded-lg overflow-hidden">
                            <div className="bg-blue-900/30 px-4 py-3 border-b-2 border-blue-500 flex items-center justify-between">
                                <div className="flex items-center">
                                    <svg className="w-5 h-5 text-blue-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                                    </svg>
                                    <h4 className="font-bold text-blue-200">ADDITIONAL Segments (Supplementary)</h4>
                                </div>
                                <span className="text-xs text-blue-300 font-medium">
                                    {additionalExtractionData.metadata.segment_count} segments • {additionalExtractionTime}s
                                </span>
                            </div>
                            <div className="p-4 max-h-96 overflow-y-auto bg-slate-900">
                                <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono">
                                    {JSON.stringify(additionalExtractionData.insights, null, 2)}
                                </pre>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

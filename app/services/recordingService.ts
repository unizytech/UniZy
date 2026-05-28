/**
 * Recording Service for Live Audio Recording with Chunking
 *
 * This service handles:
 * - MediaRecorder API integration
 * - Audio chunking (configurable interval, default 10s)
 * - Communication with backend recording API
 *
 * Note: Progress updates are delivered via Supabase Realtime (WebSocket)
 * in VHRScreen.tsx, not through this service.
 */

import { API_CONFIG } from "@lib/config";

// ============================================================================
// Types
// ============================================================================

export interface RecordingConfig {
    template: string;  // Template code for database lookups (unique identifier)
    templateName?: string;  // Template display name (optional, for human readability)
    doctorName: string;  // Contains doctor_id UUID
    nurseId?: string;  // Optional nurse_id UUID if recording is initiated by a nurse
    patientId: string;
    transcriptionEngine?: string;
    processingMode?: string;  // Processing mode (ultra_fast, fast, default, thorough, ultra)
    extractionMode?: string;  // Extraction mode (core, additional, full)
    chunkDurationSeconds?: number;
    isContinuation?: boolean;  // Whether this recording continues a prior consultation (default: false)
}

export interface RecordingSession {
    correlationId: string;
    sessionId: string;
    startTime: number;
    chunkIndex: number;
    isRecording: boolean;
    isPaused: boolean;
}

export interface ChunkUploadResponse {
    message: string;
    chunkIndex: number;
    totalChunks: number;
    submissionId?: string; // Present if last chunk
}

// ============================================================================
// Recording Manager Class
// ============================================================================

export class RecordingManager {
    private mediaRecorder: MediaRecorder | null = null;
    private audioStream: MediaStream | null = null;
    private session: RecordingSession | null = null;
    private config: RecordingConfig | null = null;
    private lastCorrelationId: string | null = null;  // ⭐ Persists after session ends
    private accessToken: string | null = null;  // Auth token for API calls

    /**
     * Set the access token for authenticated API calls
     */
    setAccessToken(token: string | null) {
        this.accessToken = token;
    }

    /**
     * Get headers with optional auth token
     */
    private getHeaders(): Record<string, string> {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };
        if (this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`;
        }
        return headers;
    }

    /**
     * Start a new recording session
     */
    async startRecording(
        config: RecordingConfig,
        onChunkRecorded?: (chunkIndex: number) => void
    ): Promise<RecordingSession> {
        this.config = config;

        // Get microphone access
        try {
            this.audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err: any) {
            // Provide more specific error messages based on error type
            if (err.name === 'NotAllowedError') {
                throw new Error('Microphone access denied. Please allow microphone access in your browser settings and try again.');
            } else if (err.name === 'NotFoundError') {
                throw new Error('No microphone found. Please connect a microphone and try again.');
            } else if (err.name === 'NotReadableError') {
                throw new Error('Microphone is already in use by another application.');
            } else if (err.name === 'NotSupportedError') {
                throw new Error('Browser does not support microphone access. Please use a modern browser (Chrome, Firefox, Edge).');
            } else {
                throw new Error(`Failed to access microphone: ${err.message || 'Unknown error'}`);
            }
        }

        // Create MediaRecorder
        const mimeType = this.getSupportedMimeType();
        this.mediaRecorder = new MediaRecorder(this.audioStream, { mimeType });

        // Start backend recording session
        const sessionResponse = await fetch(
            `${API_CONFIG.backendUrl}/api/v1/option1/recording/start`,
            {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    template_code: config.template,  // Template code for DB lookups
                    template_name: config.templateName,  // Display name (optional)
                    doctor_id: config.doctorName,  // doctorName actually contains doctor_id
                    nurse_id: config.nurseId || null,  // Optional nurse_id if recording initiated by nurse
                    patient_id: config.patientId,
                    transcription_engine: config.transcriptionEngine || 'gemini',
                    processing_mode: config.processingMode || 'default',
                    // Only send extraction_mode if template is not TRANSCRIPT_ONLY
                    ...(config.template !== 'TRANSCRIPT_ONLY' && {
                        extraction_mode: config.extractionMode || 'full'
                    }),
                    chunk_duration_seconds: config.chunkDurationSeconds || 10,
                    ...(config.isContinuation && { is_continuation: true }),
                }),
            }
        );

        if (!sessionResponse.ok) {
            throw new Error('Failed to start recording session');
        }

        const sessionData = await sessionResponse.json();

        // Initialize session
        this.session = {
            correlationId: sessionData.correlation_id,
            sessionId: sessionData.session_id,
            startTime: Date.now(),
            chunkIndex: 0,
            isRecording: true,
            isPaused: false,
        };

        // ⭐ Store correlation_id separately so it persists after session ends
        this.lastCorrelationId = sessionData.correlation_id;

        // Configure time-sliced recording
        const chunkDuration = (config.chunkDurationSeconds || 10) * 1000; // Convert to ms

        this.mediaRecorder.ondataavailable = async (event) => {
            // Capture session reference at start to handle race conditions
            const currentSession = this.session;
            if (event.data.size > 0 && currentSession) {
                const currentChunkIndex = currentSession.chunkIndex;
                try {
                    // Upload chunk to backend
                    await this.uploadChunk(event.data, currentChunkIndex, false);

                    // Check session still exists after async operation
                    if (this.session && onChunkRecorded) {
                        onChunkRecorded(currentChunkIndex);
                    }

                    // Only increment if session still exists
                    if (this.session) {
                        this.session.chunkIndex++;
                    }
                } catch (err) {
                    console.error('[RecordingService] Chunk upload error:', err);
                    // Don't throw - let recording continue
                }
            }
        };

        // Start recording with time slicing
        this.mediaRecorder.start(chunkDuration);

        return this.session;
    }

    /**
     * Start a recording session WITHOUT microphone access (for file uploads)
     * This creates a backend session but skips MediaRecorder setup
     */
    async startSessionWithoutMicrophone(config: RecordingConfig): Promise<RecordingSession> {
        this.config = config;

        // Start backend recording session (no microphone needed)
        const sessionResponse = await fetch(
            `${API_CONFIG.backendUrl}/api/v1/option1/recording/start`,
            {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    template_code: config.template,  // Template code for DB lookups
                    template_name: config.templateName,  // Display name (optional)
                    doctor_id: config.doctorName,  // doctorName actually contains doctor_id
                    patient_id: config.patientId,
                    transcription_engine: config.transcriptionEngine || 'gemini',
                    processing_mode: config.processingMode || 'default',
                    // Only send extraction_mode if template is not TRANSCRIPT_ONLY
                    ...(config.template !== 'TRANSCRIPT_ONLY' && {
                        extraction_mode: config.extractionMode || 'full'
                    }),
                    chunk_duration_seconds: 0, // File upload = single chunk
                    ...(config.isContinuation && { is_continuation: true }),
                }),
            }
        );

        if (!sessionResponse.ok) {
            const errorData = await sessionResponse.json().catch(() => ({}));
            const errorDetail = errorData.detail || `HTTP ${sessionResponse.status}: ${sessionResponse.statusText}`;
            throw new Error(`Failed to start recording session: ${JSON.stringify(errorDetail)}`);
        }

        const sessionData = await sessionResponse.json();

        // Initialize session (without MediaRecorder)
        this.session = {
            correlationId: sessionData.correlation_id,
            sessionId: sessionData.session_id,
            startTime: Date.now(),
            chunkIndex: 0,
            isRecording: false, // Not actually recording
            isPaused: false,
        };

        // ⭐ Store correlation_id separately so it persists after session ends
        this.lastCorrelationId = sessionData.correlation_id;

        return this.session;
    }

    /**
     * Pause recording
     */
    pause(): void {
        if (this.mediaRecorder && this.session?.isRecording && !this.session.isPaused) {
            this.mediaRecorder.pause();
            if (this.session) {
                this.session.isPaused = true;
            }
        }
    }

    /**
     * Resume recording
     */
    resume(): void {
        if (this.mediaRecorder && this.session?.isPaused) {
            this.mediaRecorder.resume();
            if (this.session) {
                this.session.isPaused = false;
            }
        }
    }

    /**
     * Stop recording and submit for processing
     */
    async stopAndSubmit(): Promise<string> {
        if (!this.mediaRecorder || !this.session) {
            throw new Error('No active recording session');
        }

        // Capture session reference before async operations
        const sessionSnapshot = {
            chunkIndex: this.session.chunkIndex,
            correlationId: this.session.correlationId
        };

        return new Promise((resolve, reject) => {
            // Set flag to mark next chunk as last
            let isLastChunkProcessed = false;

            // Override ondataavailable to mark the final chunk
            this.mediaRecorder!.ondataavailable = async (event) => {
                if (isLastChunkProcessed) return; // Prevent double processing
                isLastChunkProcessed = true;

                // Handle case where recording stopped with no/empty audio data
                if (event.data.size === 0) {
                    this.cleanup();
                    reject(new Error('No audio data recorded. Please record for at least a few seconds.'));
                    return;
                }

                try {
                    // Upload final chunk with is_last=true (use captured chunkIndex)
                    const response = await this.uploadChunk(event.data, sessionSnapshot.chunkIndex, true);

                    if (!response.submissionId) {
                        throw new Error('No submission ID received from backend');
                    }

                    // Clean up AFTER successful upload
                    this.cleanup();

                    resolve(response.submissionId);
                } catch (err) {
                    this.cleanup();
                    reject(err);
                }
            };

            // Stop recording - this will trigger ondataavailable with the final chunk
            this.mediaRecorder!.stop();
        });
    }

    /**
     * Cancel recording session
     */
    async cancel(): Promise<void> {
        if (!this.session) {
            return;
        }

        try {
            // Stop MediaRecorder if active
            if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
                this.mediaRecorder.stop();
            }

            // Cancel session on backend
            const cancelResponse = await fetch(`${API_CONFIG.backendUrl}/api/v1/option1/recording/cancel`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    correlation_id: this.session.correlationId,
                }),
            });
        } finally {
            this.cleanup();
        }
    }

    /**
     * Get current session info
     */
    getSession(): RecordingSession | null {
        return this.session;
    }

    /**
     * Get recording duration in seconds
     */
    getRecordingDuration(): number {
        if (!this.session) return 0;
        return Math.floor((Date.now() - this.session.startTime) / 1000);
    }

    /**
     * Get correlation ID for the current recording session
     * Used to link extraction requests to the recording session in database
     * ⭐ Returns lastCorrelationId if session has ended (persists after stopRecording)
     */
    getCorrelationId(): string | null {
        return this.session?.correlationId || this.lastCorrelationId || null;
    }

    // ========================================================================
    // Private Methods
    // ========================================================================

    /**
     * Upload audio chunk (accepts Blob or base64 string)
     * Made public for file upload use cases
     */
    async uploadChunk(
        audioData: Blob | string,
        chunkIndex: number,
        isLast: boolean,
        mimeType?: string
    ): Promise<ChunkUploadResponse> {
        if (!this.session) {
            throw new Error('No active session');
        }

        // Convert blob to base64 if needed
        let base64Audio: string;
        if (typeof audioData === 'string') {
            // Already base64
            base64Audio = audioData;
        } else {
            // Convert Blob to base64
            base64Audio = await this.blobToBase64(audioData);
        }

        const response = await fetch(
            `${API_CONFIG.backendUrl}/api/v1/option1/recording/chunk`,
            {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    correlation_id: this.session.correlationId,
                    chunk_index: chunkIndex,
                    audio_data: base64Audio,
                    mime_type: mimeType || this.mediaRecorder?.mimeType || 'audio/webm',
                    is_last: isLast,
                }),
            }
        );

        if (!response.ok) {
            throw new Error('Failed to upload chunk');
        }

        return await response.json();
    }

    private async blobToBase64(blob: Blob): Promise<string> {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64 = reader.result as string;
                // Remove data URL prefix (e.g., "data:audio/webm;base64,")
                const base64Data = base64.split(',')[1];
                resolve(base64Data);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    private getSupportedMimeType(): string {
        const types = [
            'audio/webm',
            'audio/webm;codecs=opus',
            'audio/ogg;codecs=opus',
            'audio/mp4',
        ];

        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }

        return 'audio/webm'; // Fallback
    }

    private cleanup(): void {
        // Stop audio stream
        if (this.audioStream) {
            this.audioStream.getTracks().forEach((track) => track.stop());
            this.audioStream = null;
        }

        // Clean up MediaRecorder
        this.mediaRecorder = null;
        this.session = null;
    }
}

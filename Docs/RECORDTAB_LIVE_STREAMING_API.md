# RecordTab Live Streaming API Reference

## Overview

RecordTab uses Gemini Live API for real-time transcription while simultaneously uploading audio chunks to the backend for emotion analysis. This enables combined emotion analysis (audio + transcript) without blocking the extraction pipeline.


## API Call Sequence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RECORDING PHASE                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Frontend: GET /api/ephemeral-token                                       │
│     → Returns: { token, expires_in }                                         │
│                                                                              │
│  2. Frontend: Connect to Gemini Live API (WebSocket)                         │
│     → Real-time transcription begins                                         │
│                                                                              │
│  3. PARALLEL (during recording):                                             │
│     ┌────────────────────────────────┐  ┌─────────────────────────────────┐ │
│     │ Audio → Gemini Live WebSocket  │  │ Audio → POST /live/chunk        │ │
│     │ (real-time transcript)         │  │ (every ~4 seconds)              │ │
│     └────────────────────────────────┘  └─────────────────────────────────┘ │
│                                              │                               │
│                                              ▼                               │
│                                    ┌─────────────────────────────────┐      │
│                                    │ First chunk (index=0):          │      │
│                                    │ • NO correlation_id sent        │      │
│                                    │ • Includes doctor_id,           │      │
│                                    │   template_code, patient_id     │      │
│                                    │ • Backend generates UUID        │      │
│                                    │ • Response: {correlation_id}    │      │
│                                    │ → Triggers parallel prompt gen  │      │
│                                    └─────────────────────────────────┘      │
│                                              │                               │
│                                              ▼                               │
│                                    ┌─────────────────────────────────┐      │
│                                    │ Subsequent chunks (index > 0):  │      │
│                                    │ • MUST include correlation_id   │      │
│                                    │   from first chunk response     │      │
│                                    └─────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         STOP & EXTRACT PHASE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  5. User clicks Stop                                                         │
│     → setStatus('Recording stopped. Finalizing audio stream...')             │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  WAIT 3 SECONDS (Finalization Buffer)                                 │  │
│  │                                                                       │  │
│  │  Purpose: Capture audio that was sent to Gemini but not yet          │  │
│  │           transcribed due to 1-2 second transmission/processing lag   │  │
│  │                                                                       │  │
│  │  During this wait:                                                    │  │
│  │  • Gemini Live WebSocket stays OPEN                                   │  │
│  │  • Transcription updates keep arriving via onTranscriptionUpdate      │  │
│  │  • nativeTranscript state accumulates all late-arriving text          │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  6. Frontend: Close Gemini WebSocket (flushes final audio chunk)             │
│     → sessionManagerRef.current.close()                                      │
│     → Any remaining audio buffer is flushed as final chunk                   │
│                                                                              │
│  7. Frontend: Get complete transcript                                        │
│     → finalNativeText = nativeTranscript.trim()                              │
│     → Transcript now includes all lagged transcription chunks                │
│                                                                              │
│  8. Frontend: POST /live/session                                             │
│     → Creates recording_sessions record                                      │
│     → Returns: { correlation_id, session_id }                                │
│                                                                              │
│  9. Frontend: POST /extract                                                  │
│     → Runs extraction from transcript                                        │
│     → Schedules async audio emotion (non-blocking)                           │
│     → Returns: { success, insights, metadata }                               │
│     → Webhook fires immediately (before emotion completes)                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                      BACKGROUND (async, non-blocking)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  8. Backend: schedule_live_audio_emotion()                                   │
│     → Stitch audio chunks from memory                                        │
│     → Save stitched audio to recording_sessions                              │
│     → Run combined emotion analysis (audio + transcript)                     │
│     → Trigger consultation insights pipeline                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. `POST /api/v1/option1/recording/live/chunk`

**Purpose**: Upload audio chunks during live Gemini streaming (parallel to transcription)

**When to call**: Every ~4 seconds during recording (fire-and-forget)

**Request**:
```json
{
  // First chunk (index=0): DO NOT send correlation_id - backend generates it
  // Subsequent chunks: MUST include correlation_id from first chunk response
  "correlation_id": "string",   // Required for chunk_index > 0, omit for chunk_index=0
  "chunk_index": 0,             // Sequential: 0, 1, 2, ...
  "audio_data": "string",       // Base64-encoded PCM audio
  "mime_type": "audio/pcm;rate=16000",

  // OPTIONAL: Context for parallel prompt generation (send with first chunk only)
  "doctor_id": "uuid-string",   // Optional: Doctor UUID (for parallel prompt gen)
  "template_code": "string",    // Optional: Template code (for parallel prompt gen)
  "patient_id": "string"        // Optional: Patient ID (for patient context injection)
}
```

**Response**:
```json
{
  "message": "Chunk stored",
  "chunk_index": 0,             // Echo back for confirmation
  "correlation_id": "string"    // Backend-generated UUID (use for subsequent chunks)
}
```

**Validation Rules**:
| chunk_index | correlation_id | Result |
|-------------|----------------|--------|
| 0 | Not provided | ✅ Backend generates UUID |
| 0 | Provided | ❌ Error 400: "must not be provided for first chunk" |
| > 0 | Valid UUID | ✅ Uses provided |
| > 0 | Not provided | ❌ Error 400: "required for chunk_index > 0" |

---

### 2. `POST /api/v1/option1/recording/live/session`

**Purpose**: Create recording session after recording stops

**When to call**: After stopping recording, before extraction

**Request**:
```json
{
  "doctor_id": "uuid-string",      // Required: Doctor UUID
  "patient_id": "string",          // Patient ID (or 'LIVE_RECORDING' fallback)
  "template_code": "string",       // Template code for DB lookups
  "template_name": "string",       // Display name
  "processing_mode": "ultra",      // "ultra" | "ultra_fast"
  "correlation_id": "uuid-string"  // Backend-generated from first /live/chunk response
}
```

**Response**:
```json
{
  "correlation_id": "uuid-string", // Same as input (or generated if not provided)
  "session_id": "uuid-string",     // UUID of created session
  "message": "Live session created successfully"
}
```


---

### 3. `POST /api/v1/summary/extract`

**Purpose**: Extract medical insights from transcript

**When to call**: After `/live/session` returns

**Request**:
```json
{
  "transcript": "string",          // Full transcript from Gemini Live
  "submission_id": "uuid-string",  // correlation_id from /live/session
  "template_code": "string",       // Template code
  "template_name": "string",       // Optional display name
  "processing_mode": "ultra",      // "ultra" | "ultra_fast" | "default"
  "mode": "full"                   // "core" | "additional" | "full"
}
```

**Response**:
```json
{
  "success": true,
  "insights": { },                 // Extracted medical data
  "metadata": {
    "correlation_id": "string",
    "submission_id": "string",
    "extraction_id": "string"
  }
}
```


---

## Frontend Implementation

### RecordTab.tsx Key Code

```typescript
// 1. Backend-generated correlation_id ref (received from first /live/chunk response)
const correlationIdRef = useRef<string | null>(null);

// 2. Chunk upload callback - receives correlation_id from backend on first chunk
const uploadLiveChunk = useCallback(async (
  chunkData: string,
  chunkIndex: number
): Promise<void> => {
  // Subsequent chunks need correlation_id from first chunk
  if (chunkIndex > 0 && !correlationIdRef.current) return;

  // Build payload - first chunk does NOT send correlation_id
  const payload: Record<string, unknown> = {
    chunk_index: chunkIndex,
    audio_data: chunkData,
    mime_type: 'audio/pcm;rate=16000',
  };

  // Only send correlation_id for subsequent chunks
  if (chunkIndex > 0) {
    payload.correlation_id = correlationIdRef.current;
  }

  // First chunk includes context for parallel prompt generation
  if (chunkIndex === 0) {
    payload.doctor_id = selectedDoctorId;
    payload.template_code = selectedTemplate?.template_code;
    payload.patient_id = patientId;
  }

  const response = await authPost('/api/v1/option1/recording/live/chunk', getAccessToken(), payload);

  // Store backend-generated correlation_id from first chunk response
  if (chunkIndex === 0 && response?.correlation_id) {
    correlationIdRef.current = response.correlation_id;
    console.log('[RecordTab] Received correlation_id from backend:', response.correlation_id);
  }
}, [getAccessToken, selectedDoctorId, selectedTemplate, patientId]);

// 3. Start recording - reset correlation_id (will be received from backend)
const startRecording = useCallback(async () => {
  correlationIdRef.current = null;  // Will be set by first /live/chunk response

  // ... fetch ephemeral token ...

  sessionManagerRef.current = await startLiveTranscriptionSession(
    handleTranscriptionUpdate,
    handleError,
    handleConnected,
    ephemeralToken,
    undefined,        // resumeHandle
    uploadLiveChunk   // chunk callback
  );
}, []);

// 4. Stop recording - pass backend-generated correlation_id to /live/session
const stopRecording = useCallback(async () => {
  // ... close Gemini session ...

  await authPost('/live/session', getAccessToken(), {
    doctor_id: selectedDoctorId,
    patient_id: patientId,
    template_code: selectedTemplate.template_code,
    processing_mode: processingMode,
    correlation_id: correlationIdRef.current,  // From first /live/chunk response
  });

  // ... call /extract ...
}, []);
```

### geminiClient.ts Key Code

```typescript
export async function startLiveTranscriptionSession(
  onTranscriptionUpdate: (text: string, isFinal: boolean) => void,
  onError: (error: Error) => void,
  onOpen: () => void,
  ephemeralToken?: string,
  resumeHandle?: string,
  onChunkReady?: (chunkData: string, chunkIndex: number) => Promise<void>
): Promise<LiveSessionManager> {

  // Chunk buffering (~4 seconds at 16kHz)
  const CHUNK_SIZE_SAMPLES = 64000;
  let chunkBuffer: Int16Array[] = [];
  let chunkIndex = 0;

  scriptProcessor.onaudioprocess = (audioProcessingEvent) => {
    // ... existing: send to Gemini ...

    // Buffer for chunk upload
    if (onChunkReady) {
      chunkBuffer.push(int16.slice());

      const totalSamples = chunkBuffer.reduce((sum, arr) => sum + arr.length, 0);
      if (totalSamples >= CHUNK_SIZE_SAMPLES) {
        const base64 = combineAndEncode(chunkBuffer);
        onChunkReady(base64, chunkIndex++);  // Fire-and-forget
        chunkBuffer = [];
      }
    }
  };

  // Flush remaining on close
  const close = () => {
    if (onChunkReady && chunkBuffer.length > 0) {
      const base64 = combineAndEncode(chunkBuffer);
      onChunkReady(base64, chunkIndex);  // Final chunk
    }
    // ... existing close logic ...
  };
}
```

---

## Timing & Performance

| Phase | Duration | Blocking? |
|-------|----------|-----------|
| Recording + chunk upload | N seconds | Parallel |
| Prompt generation (parallel) | ~1.5s | No (during recording) |
| **Finalization buffer** | **4 seconds** | **Yes** |
| /live/session | ~100ms | Yes |
| /extract (transcript only) | ~15-17s | Yes |
| Webhook fires | Immediate | - |
| Audio stitch + emotion | ~8-12s | No (background) |
| Consultation insights | ~3-5s | No (background) |

**Finalization Buffer (3 seconds)**

When the user clicks Stop, the frontend waits 3 seconds before closing the Gemini WebSocket. This handles the 1-2 second lag between:
- Audio being sent to Gemini
- Transcription response arriving back

```
User clicks Stop
      │
      ▼
setStatus('Recording stopped. Finalizing audio stream...')
      │
      ▼ ──────────────────────────────────────────────────────┐
      │                                                        │
      │   WAIT 3 SECONDS                                       │
      │   - Gemini Live WebSocket stays open                   │
      │   - Transcription updates keep arriving                │
      │   - nativeTranscript state accumulates                 │
      │                                                        │
      ▼ ◄──────────────────────────────────────────────────────┘
      │
sessionManagerRef.current.close()  // NOW close the session
      │
      ▼
finalNativeText = nativeTranscript.trim()  // Has complete transcript
      │
      ▼
Proceed to extraction
```

**Why 3 seconds?**
- 1-2s: Audio transmission lag
- 1-2s: Gemini processing time
- Buffer for safety margin

**Code location**: `RecordTab.tsx` line ~310:
```typescript
await new Promise(resolve => setTimeout(resolve, 4000));
```

**Optimization: Parallel Prompt Generation**

| Metric | Without Parallel | With Parallel | Saved |
|--------|-----------------|---------------|-------|
| List check | 0.3-3.0s | SKIPPED | ~0.3s |
| Prompt generation | 1.2-1.8s | SKIPPED | ~1.5s |
| **Total savings** | - | - | **~1.2-1.8s** |

**Key**: Prompts are pre-generated during recording (triggered by first chunk). By the time `/extract` is called, prompts are ready and cached.

---

## Error Handling

| Failure | Impact | Recovery |
|---------|--------|----------|
| `/live/chunk` fails | Emotion uses transcript-only | Graceful degradation |
| No chunks uploaded | No audio emotion | Falls back to text emotion |
| `/live/session` fails | No extraction possible | Error shown to user |
| Emotion extraction fails | No emotion segments | Consultation insights still runs |

---

## Verification Logs

```
# Recording Start
[RecordTab] First chunk - sending context for parallel prompt generation
[LIVE_CHUNK] Generated correlation_id: abc-123-...
[RecordTab] Received correlation_id from backend: abc-123-...
[RecordTab] ✓ Uploaded chunk 0

# Parallel Prompt Generation (during recording)
[LIVE_CHUNK] First chunk with context - starting parallel prompt generation
[LIVE_PROMPT] Starting parallel prompt generation for abc-123-...
[LIVE_PROMPT] ✅ Pre-generated prompts for abc-123-... in 1.234s

# More Chunks (now include correlation_id from first chunk)
[RecordTab] ✓ Uploaded chunk 1
[GeminiClient] Flushed final chunk 2 (32000 samples)

# Session + Extraction
[RecordTab] ✓ Live session created: session-uuid
[EXTRACTION_SERVICE] ✅ Using pre-generated prompts from /live/chunk (parallel optimization)
[TIMING_LIST_CHECK] ⚡ SKIPPED - using cached from /live/chunk
[LIVE_PROMPT] ✅ Cache HIT for abc-123-... (age=8.5s)

# Background Processing
[EXTRACT] Found 3 audio chunks for live session - scheduling async processing
[LIVE_AUDIO] Starting async processing for abc-123-... (3 chunks)
[LIVE_AUDIO] Stitched 384000 bytes (audio/pcm;rate=16000)
[LIVE_AUDIO] ✓ Completed async processing
[EMOTION:COMBINED] Extraction successful: 7 segments
[CONSULTATION_INSIGHTS] ✓ Full pipeline complete
```

---

## Architecture Diagram

```
┌──────────────┐     ┌───────────────┐     ┌─────────────┐
│  RecordTab   │────▶│ Gemini Live   │────▶│ Transcript  │
│  (Frontend)  │     │    (WS)       │     │             │
└──────┬───────┘     └───────────────┘     └──────┬──────┘
       │                                          │
       │ POST /live/chunk (parallel)              │
       ▼                                          ▼
┌──────────────┐     ┌───────────────┐     ┌─────────────┐
│ Memory Store │     │   /extract    │────▶│  Webhook    │ ← IMMEDIATE
│   (chunks)   │     │  (cached!)    │     │  Response   │
└──────┬───────┘     └───────┬───────┘     └─────────────┘
       │                     │
       │ First chunk         │ Uses pre-generated prompts
       │ triggers:           │ (list check + prompt gen SKIPPED)
       ▼                     │
┌──────────────┐             │
│ Prompt Cache │─────────────┘
│ (by corr_id) │             asyncio.create_task (non-blocking)
└──────────────┘                    ▼
       │               ┌───────────────────────────────────┐
       │               │ Audio Stitch → Emotion → Insights │
       │               └───────────────────────────────────┘
       ▼
┌──────────────┐
│ Audio Stitch │────▶ Audio Emotion ────▶ Consultation Insights
│  (async BG)  │
└──────────────┘
```

---


---

*Last updated: January 12, 2026*

---

## Changelog

**January 12, 2026**:
- **Breaking Change**: `correlation_id` now generated by backend on first `/live/chunk` call
- Frontend no longer pre-generates `correlation_id` with `crypto.randomUUID()`
- First chunk (index=0) must NOT include `correlation_id`
- Backend returns `correlation_id` in response for use in subsequent chunks

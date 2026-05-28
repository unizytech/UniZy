# Complete Workflow Trace: Frontend → Backend → Database

This document traces the complete flow for three main workflows in the application.

---

## Workflow 1: VHRScreen.tsx - Live Recording (Microphone)

### User Flow Overview
User selects doctor → template → processing mode → extraction mode → clicks Record button → speaks → clicks Stop → sees progressive extraction results

### Frontend: VHRScreen.tsx

#### A. Recording Start (extraction_mode: 'full')

**Line 269-303:** `startChunkedRecording()`

```typescript
// Frontend State Updates
extractionMode = 'full' // User selected FULL mode
processingMode = 'default' // e.g., 'fast', 'default', 'thorough'

// Creates RecordingManager
recordingManagerRef.current = new RecordingManager()

// Starts recording with configuration
await recordingManagerRef.current.startRecording({
  template: 'TRANSCRIPT_ONLY',  // ⚠️ ALWAYS uses TRANSCRIPT_ONLY for mic recording
  doctorName: selectedDoctorId,
  patientId: patientId,
  transcriptionEngine: 'gemini',
  processingMode: processingMode,  // e.g., 'default'
  chunkDurationSeconds: 10,
}, onChunkUploaded)
```

**What happens:**
1. MediaRecorder starts capturing audio
2. Every 10 seconds, audio chunk is uploaded to backend
3. Frontend shows: chunks uploaded count, recording duration

#### B. Recording Stop

**Line 305-346:** `stopChunkedRecording()`

```typescript
// 1. Submit final chunk
const submissionId = await recordingManagerRef.current.stopAndSubmit()

// 2. Connect to SSE stream for progress
recordingManagerRef.current.streamProcessingProgress(
  submissionId,
  (progress) => { setProcessingProgress(progress) },
  (sseResult) => {
    // Store transcript and metrics
    setTranscript(sseResult.transcript)
    setStitchingTime(sseResult.metrics?.stitching_time)
    setTranscriptionTime(sseResult.metrics?.transcription_time)

    // ⭐ TRIGGER FRONTEND EXTRACTION (since we used TRANSCRIPT_ONLY)
    handleProgressiveExtraction(sseResult.transcript)
  }
)
```

#### C. Progressive Extraction (Frontend)

**Line 180-266:** `handleProgressiveExtraction()`

```typescript
// STEP 1: Extract CORE segments (immediate)
setLoadingCore(true)
const coreResponse = await extractMedicalSummary({
  transcript: transcriptText,
  consultation_type_code: selectedTemplate.consultation_type_code,
  doctor_id: selectedDoctorId,
  template_name: selectedTemplate.template_name_override,
  mode: 'core',  // ⭐ Only CORE segments
  model: extractionModel,  // From processing mode
})

setCoreExtractionData(coreResponse)
setLoadingCore(false)

// STEP 2: Extract ADDITIONAL segments (if mode is 'additional')
if (extractionMode === 'additional') {
  extractAdditionalSegments(extractionModel, transcriptText)
}
```

**Line 227-266:** `extractAdditionalSegments()`

```typescript
setLoadingAdditional(true)
const additionalResponse = await extractMedicalSummary({
  transcript: transcriptText,
  template_name: selectedTemplate.template_name_override,
  mode: 'additional',  // ⭐ Only ADDITIONAL segments
  model: extractionModel,
})

setAdditionalExtractionData(additionalResponse)
setLoadingAdditional(false)
```

---

### Backend API Calls (Microphone Recording - FULL mode)

#### 1. POST /api/v1/option1/recording/start

**File:** `backend/routers/recording_session.py:126-180`

```python
# Request body
{
  "doctor_id": "uuid",
  "patient_id": "PAT-12345",
  "template_name": "TRANSCRIPT_ONLY",  # ⚠️ Frontend sends TRANSCRIPT_ONLY
  "processing_mode": "default",
  "extraction_mode": None,  # ⚠️ None because TRANSCRIPT_ONLY
  "chunk_duration_seconds": 10
}

# Create database session
session_id = create_recording_session(
    doctor_id=doctor_uuid,
    patient_id=patient_id,
    template_name="TRANSCRIPT_ONLY",  # Stored in DB
    extraction_mode=None,  # ⚠️ NULL in database
    processing_mode="default",
    chunk_duration_seconds=10,
)

# Response
{
  "correlation_id": "uuid-correlation",
  "session_id": "uuid-session",
  "message": "Recording session started"
}
```

**Database Operations:**
```sql
-- Table: recording_sessions
INSERT INTO recording_sessions (
  id,
  correlation_id,
  doctor_id,
  patient_id,
  template_name,           -- 'TRANSCRIPT_ONLY'
  extraction_mode,         -- NULL
  processing_mode,         -- 'default'
  consultation_type_id,    -- NULL (will be set during extraction)
  session_status,          -- 'active'
  chunk_duration_seconds,  -- 10
  created_at,
  updated_at
) VALUES (...)
```

#### 2. POST /api/v1/option1/recording/chunk (Multiple calls, every 10 seconds)

**File:** `backend/routers/recording_session.py:183-229`

```python
# Request body (for each chunk)
{
  "correlation_id": "uuid-correlation",
  "chunk_index": 0,  # Increments: 0, 1, 2, ...
  "audio_data": "base64-encoded-audio",
  "mime_type": "audio/webm",
  "duration_seconds": 10.0,
  "is_last": false  # true on final chunk
}

# Save chunk to database
save_audio_chunk(
    correlation_id=correlation_id,
    chunk_index=chunk_index,
    audio_data=audio_data,
    mime_type=mime_type,
    duration_seconds=duration_seconds,
)

# When is_last = true:
submission_id = create_processing_job(session_id)
asyncio.create_task(process_recording_async(submission_id))

# Response (last chunk only)
{
  "message": "Final chunk uploaded",
  "chunkIndex": 5,
  "totalChunks": 6,
  "submissionId": "uuid-submission"  # ⚠️ Only on last chunk
}
```

**Database Operations:**
```sql
-- Table: audio_chunks (for each chunk)
INSERT INTO audio_chunks (
  id,
  session_id,
  chunk_index,
  audio_data,
  mime_type,
  duration_seconds,
  uploaded_at
) VALUES (...)

-- When is_last = true:
-- Table: processing_jobs
INSERT INTO processing_jobs (
  id,                    -- submission_id
  session_id,
  job_status,           -- 'pending'
  started_at,
  created_at
) VALUES (...)
```

#### 3. Background Processing (RecordingProcessor)

**File:** `backend/services/recording_processor.py`

```python
async def process_recording_async(submission_id: uuid.UUID):
    processor = RecordingProcessor(submission_id, emit_event_callback)
    await processor.process()

# process() method flow:
# 1. LOADING: Load session and chunks from DB
# 2. STITCHING: Combine audio chunks into single file
# 3. TRANSCRIBING: Call Gemini API for transcription
# 4. EXTRACTING: ⚠️ SKIPPED (because template_name = 'TRANSCRIPT_ONLY')
# 5. SAVING: Save full audio to DB, delete chunks
# 6. COMPLETED: Send final SSE event with transcript
```

**Extraction Logic (Line 268-271):**
```python
# Check if we should extract
if not extraction_mode or template_name == "TRANSCRIPT_ONLY":
    logger.info("[EXTRACTION] TRANSCRIPT_ONLY mode - skipping extraction")
    return None  # ⚠️ No extraction, returns None
```

**Database Operations:**
```sql
-- Update job status through various stages
UPDATE processing_jobs
SET job_status = 'loading' WHERE id = submission_id;
-- ... 'stitching', 'transcribing', 'saving', 'completed'

-- Save full audio (after stitching)
UPDATE recording_sessions
SET
  full_audio_data = stitched_audio,
  audio_mime_type = 'audio/webm',
  session_status = 'completed',
  total_duration_seconds = duration
WHERE id = session_id;

-- Delete chunks (cleanup)
DELETE FROM audio_chunks WHERE session_id = session_id;
```

#### 4. GET /api/v1/option1/recording/processing/{submission_id}/stream (SSE)

**File:** `backend/routers/recording_session.py:232-344`

**Frontend receives SSE events:**
```typescript
// Event 1: { type: 'progress', status: 'LOADING', progress: 10 }
// Event 2: { type: 'progress', status: 'STITCHING', progress: 30 }
// Event 3: { type: 'progress', status: 'TRANSCRIBING', progress: 50 }
// Event 4: { type: 'progress', status: 'SAVING', progress: 80 }
// Event 5: {
//   type: 'complete',
//   transcript: "full transcript text",
//   insights: null,  // ⚠️ NULL because TRANSCRIPT_ONLY
//   metrics: { stitching_time: 2.5, transcription_time: 15.3, extraction_time: null }
// }
```

#### 5. POST /api/v1/summary/extract (CORE extraction - Frontend call)

**File:** `backend/routers/summary.py:327-436`

**⚠️ Frontend triggers extraction after receiving transcript**

```python
# Request body
{
  "transcript": "full transcript text",
  "template_name": "Prakash_Outpatient full",  # From selectedTemplate
  "doctor_id": "uuid",
  "mode": "core",  # ⭐ CORE only
  "model": "gemini-2.5-pro",
  "correlation_id": None  # ⚠️ No correlation_id for mic recording FULL mode
}

# WORKFLOW 2: Standalone Extraction (without correlation_id)
# This flow does NOT save to database

# Extract segments from database configuration
result = await extract_summary_dynamic(
    transcript=transcript,
    consultation_type_id=consultation_type_id,  # Derived from template
    doctor_id=doctor_id,
    template_name=template_name,
    mode='core',  # Only CORE segments
    model=extraction_model,
)

# Response
{
  "success": true,
  "data": { "DIAGNOSIS": "...", "CHIEF_COMPLAINTS": "...", ... },  # CORE segments only
  "metadata": {
    "consultation_type": "OP",
    "mode": "core",
    "segment_count": 8,
    "model": "gemini-2.5-pro",
    "extraction_time": 25.3
  }
}
```

**⚠️ Database Operations:** NONE (standalone extraction doesn't save)

#### 6. POST /api/v1/summary/extract (ADDITIONAL extraction - Frontend call)

**Only if extractionMode === 'additional'**

```python
# Request body
{
  "transcript": "full transcript text",
  "template_name": "Prakash_Outpatient full",
  "doctor_id": "uuid",
  "mode": "additional",  # ⭐ ADDITIONAL only
  "model": "gemini-2.5-pro",
  "correlation_id": None
}

# Extract ADDITIONAL segments only
result = await extract_summary_dynamic(
    mode='additional',  # Only ADDITIONAL segments
    ...
)

# Response
{
  "success": true,
  "data": { "PATIENT_INFO": "...", "INVESTIGATIONS": "...", ... },  # ADDITIONAL segments only
  "metadata": {
    "mode": "additional",
    "segment_count": 10,
    "extraction_time": 32.1
  }
}
```

**⚠️ Database Operations:** NONE (standalone extraction doesn't save)

---

## Workflow 2: VHRScreen.tsx - File Upload

### Frontend: VHRScreen.tsx

#### A. File Upload (extraction_mode: 'full' vs 'core'/'additional')

**Line 449-590:** `handleFileUpload()`

```typescript
// User selects file from file picker
const file: File  // Audio file

// Determine extraction strategy based on extractionMode
const templateNameToUse = extractionMode === 'full'
  ? (selectedTemplate?.template_name_override || 'Unknown')  // Real template
  : 'TRANSCRIPT_ONLY';  // Defer to frontend

const extractionModeToUse = extractionMode === 'full'
  ? extractionMode  // 'full'
  : undefined;  // NULL (TRANSCRIPT_ONLY)
```

#### B. Two Different Paths

**Path 1: extractionMode = 'full' (Backend Extraction)**

```typescript
// Line 483-502
templateNameToUse = "Prakash_Outpatient full"  // Real template
extractionModeToUse = "full"  // Tell backend to extract

// Start session WITHOUT microphone
await recordingManager.startSessionWithoutMicrophone({
  template: "Prakash_Outpatient full",  // ⚠️ Real template
  extractionMode: "full",  // ⚠️ Backend will extract
  ...
})
```

**Path 2: extractionMode = 'core' or 'additional' (Frontend Extraction)**

```typescript
// Line 483-502
templateNameToUse = "TRANSCRIPT_ONLY"  // Defer extraction
extractionModeToUse = undefined  // NULL

// Start session WITHOUT microphone
await recordingManager.startSessionWithoutMicrophone({
  template: "TRANSCRIPT_ONLY",  // ⚠️ No backend extraction
  extractionMode: undefined,  // ⚠️ NULL
  ...
})
```

#### C. Upload File as Single Chunk

```typescript
// Line 505-510: Convert file to base64
const base64Audio = await convertFileToBase64(file)

// Upload entire file as single chunk
const uploadResponse = await recordingManager.uploadChunk(
  base64Audio,
  0,        // chunk_index = 0
  true,     // is_last = true ⚠️ Single chunk
  file.type // mime_type
)

const submissionId = uploadResponse.submissionId
```

#### D. SSE Progress + Result Handling

```typescript
// Line 520-583: Connect to SSE
recordingManager.streamProcessingProgress(
  submissionId,
  (progress) => { setProcessingProgress(progress) },
  (sseResult) => {
    setTranscript(sseResult.transcript)

    // ⭐ BRANCHING LOGIC based on extractionMode
    if (extractionMode === 'full') {
      // Backend handled extraction - display ALL segments
      if (sseResult.insights) {
        setCoreExtractionData(fullExtractionResponse)  // Show all segments
        setAdditionalExtractionData(fullExtractionResponse)  // Show in both sections
      }
    } else {
      // Frontend extraction needed - trigger progressive extraction
      handleProgressiveExtraction(sseResult.transcript)  // Same as mic recording
    }
  }
)
```

---

### Backend API Calls (File Upload)

#### Path 1: extractionMode = 'full' (Backend Extraction)

**1. POST /api/v1/option1/recording/start**

```python
# Request
{
  "template_name": "Prakash_Outpatient full",  # ⚠️ Real template
  "extraction_mode": "full",  # ⚠️ Backend will extract
  "chunk_duration_seconds": 0,  # File upload indicator
}

# Database
INSERT INTO recording_sessions (
  template_name = 'Prakash_Outpatient full',
  extraction_mode = 'full',  # ⚠️ NOT NULL
  ...
)
```

**2. POST /api/v1/option1/recording/chunk**

```python
# Request
{
  "chunk_index": 0,
  "is_last": true,  # ⚠️ Single chunk upload
  "audio_data": "entire-file-base64",
  "mime_type": "audio/mp3",  # File's actual type
}

# Creates processing job immediately (is_last = true)
submission_id = create_processing_job(session_id)
```

**3. Background Processing**

```python
# RecordingProcessor.process()
# 1. LOADING
# 2. STITCHING (trivial - single chunk)
# 3. TRANSCRIBING
# 4. EXTRACTING ⚠️ RUNS (because extraction_mode = 'full')
# 5. SAVING

# Extraction flow (Line 447-503)
result = await perform_template_extraction(
    transcript=transcript,
    session_id=session_id,
    extraction_model=extraction_model,  # from processing_mode
    submission_id=submission_id
)

# ⚠️ perform_template_extraction() does EVERYTHING:
# - Derives consultation_type_id from template
# - Updates session.consultation_type_id in DB
# - Calls extract_summary_dynamic(mode='full')  # ALL segments
# - Saves to medical_extractions table
# - Saves to extraction_segments table
# - Schedules emotion extraction (20s delay)
```

**Database Operations:**
```sql
-- Update session with consultation_type_id
UPDATE recording_sessions
SET consultation_type_id = 'uuid-consultation-type'
WHERE id = session_id;

-- Save extraction results
INSERT INTO medical_extractions (
  id,
  session_id,
  consultation_type_id,
  doctor_id,
  patient_id,
  extraction_mode,      -- 'full'
  model_used,           -- 'gemini-2.5-pro'
  full_extraction_json, -- { "DIAGNOSIS": "...", ... }  ALL segments
  created_at
) VALUES (...)

-- Save individual segments
INSERT INTO extraction_segments (
  id,
  extraction_id,
  segment_code,         -- 'DIAGNOSIS', 'CHIEF_COMPLAINTS', ...
  segment_value,        -- "Hypertension with ..."
  created_at
) VALUES (...)
-- ... repeat for ALL segments (CORE + ADDITIONAL)

-- Schedule emotion extraction (background task)
-- Runs after 20 seconds delay
```

**4. SSE Response**

```json
{
  "type": "complete",
  "transcript": "full transcript",
  "insights": {
    "DIAGNOSIS": "...",
    "CHIEF_COMPLAINTS": "...",
    "PATIENT_INFO": "...",
    "INVESTIGATIONS": "..."
    // ... ALL segments (CORE + ADDITIONAL)
  },
  "metrics": {
    "stitching_time": 0.1,
    "transcription_time": 18.5,
    "extraction_time": 45.2  // ⚠️ Full extraction time
  }
}
```

**Frontend displays:** All segments in both CORE and ADDITIONAL sections

---

#### Path 2: extractionMode = 'core' or 'additional' (Frontend Extraction)

**1-3. Same as mic recording (TRANSCRIPT_ONLY flow)**

```python
# Backend does:
# - Transcribe only
# - No extraction
# - No database save for extraction
# - Returns transcript only

# SSE Response
{
  "type": "complete",
  "transcript": "full transcript",
  "insights": null,  # ⚠️ NULL
  "metrics": {
    "extraction_time": null  # ⚠️ No extraction
  }
}
```

**4. Frontend triggers extraction (same as mic recording)**

See Workflow 1, steps 5-6 for CORE and ADDITIONAL extraction calls.

---

## Workflow 3: RecordTab.tsx - WebSocket Live Recording

### Frontend: RecordTab.tsx

**Ultra Mode Only** (processing_mode = 'ultra' or 'ultra_fast')

#### A. Recording Start

**Line 166-213:** `startRecording()`

```typescript
// 1. Fetch ephemeral token from backend
const tokenResponse = await fetch('/api/ephemeral-token', { method: 'POST' })
const { token } = await tokenResponse.json()

// 2. Start WebSocket session with Gemini Live API
sessionManagerRef.current = await startLiveTranscriptionSession(
  handleTranscriptionUpdate,  // Callback for live transcript chunks
  onError,
  onOpen,
  token  // Ephemeral token (12 min expiry)
)

// 3. Audio stream from mic → WebSocket → Gemini → Live transcript
```

**What happens:**
- Client opens WebSocket to Gemini Live API (not our backend!)
- Audio chunks stream directly to Gemini (bypasses our backend)
- Transcript updates arrive in real-time
- Frontend accumulates transcript in state

#### B. Recording Stop

**Line 233-262:** `stopRecording()`

```typescript
// 1. Wait 4 seconds for audio buffer to flush
await new Promise(resolve => setTimeout(resolve, 4000))

// 2. Close WebSocket
sessionManagerRef.current.close()

// 3. Get final transcript
const finalNativeText = nativeTranscript.trim()

// 4. ⭐ TRIGGER FRONTEND EXTRACTION
await handleProgressiveExtraction(finalNativeText)
```

#### C. Progressive Extraction

**Line 265-339:** `handleProgressiveExtraction()` and `extractAdditionalSegments()`

**Identical to VHRScreen.tsx mic recording:**

```typescript
// STEP 1: Extract CORE
const coreResponse = await extractMedicalSummary({
  transcript: transcriptText,
  doctor_id: selectedDoctorId,
  template_name: selectedTemplate.template_name_override,
  processing_mode: processingMode,  // 'ultra' or 'ultra_fast'
  mode: 'core',
})

// STEP 2: Extract ADDITIONAL (if extractionMode !== 'core')
if (extractionMode !== 'core') {
  const additionalResponse = await extractMedicalSummary({
    mode: 'additional',
    ...
  })
}
```

---

### Backend API Calls (WebSocket Live Recording)

#### 1. POST /api/ephemeral-token

**File:** `backend/routers/ephemeral_token.py`

```python
# Generate ephemeral token for Gemini Live API
import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
response = client.models.generate_token(
    model='models/gemini-2.0-flash-live',
    config={
        'ttl_seconds': 720,  # 12 minutes
    }
)

# Response
{
  "token": "ephemeral-token-xyz123",
  "expires_in": 720,
  "new_session_expire_time": "2025-11-11T10:47:00Z",
  "expire_time": "2025-11-11T10:47:00Z"
}
```

**⚠️ No database operations** - This is a stateless token generation

#### 2. WebSocket to Gemini Live API (External)

**Client WebSocket connection:**
```
wss://generativelanguage.googleapis.com/v1alpha/models/gemini-2.0-flash-live:streamGenerateContent
```

**Not our backend!** Audio streams directly to Google's servers.

**⚠️ No database operations** - No session tracking in our DB

#### 3. POST /api/v1/summary/extract (CORE) - Frontend call after stop

**Same as VHRScreen.tsx mic recording, step 5**

```python
# Request
{
  "transcript": "live transcript text",
  "template_name": "Prakash_OP Concise",
  "doctor_id": "uuid",
  "processing_mode": "ultra",
  "mode": "core",
  "correlation_id": None  # ⚠️ No correlation_id
}

# WORKFLOW 2: Standalone extraction (no DB save)
# Returns CORE segments only
```

**⚠️ Database Operations:** NONE

#### 4. POST /api/v1/summary/extract (ADDITIONAL) - Frontend call

**Same as VHRScreen.tsx mic recording, step 6**

**⚠️ Database Operations:** NONE

---

## Summary of Database Operations by Workflow

### Workflow 1: VHRScreen.tsx Mic Recording (FULL mode)

| Table | Operation | When | Data |
|-------|-----------|------|------|
| `recording_sessions` | INSERT | Recording start | `template_name='TRANSCRIPT_ONLY'`, `extraction_mode=NULL` |
| `audio_chunks` | INSERT (multiple) | Each 10s chunk | Audio data |
| `processing_jobs` | INSERT | Last chunk upload | `job_status='pending'` |
| `recording_sessions` | UPDATE | After stitching | `full_audio_data`, `session_status='completed'` |
| `audio_chunks` | DELETE | After stitching | All chunks for session |
| `processing_jobs` | UPDATE (multiple) | During processing | `job_status='loading'`, `'stitching'`, etc. |
| **⚠️ medical_extractions** | **NONE** | **Never** | **Frontend extraction doesn't save** |
| **⚠️ extraction_segments** | **NONE** | **Never** | **Frontend extraction doesn't save** |

### Workflow 2A: VHRScreen.tsx File Upload (extractionMode = 'full')

| Table | Operation | When | Data |
|-------|-----------|------|------|
| `recording_sessions` | INSERT | Upload start | `template_name='Prakash_Outpatient full'`, `extraction_mode='full'` |
| `audio_chunks` | INSERT | File upload | Single chunk with full audio |
| `processing_jobs` | INSERT | Immediately | `job_status='pending'` |
| `recording_sessions` | UPDATE (1) | After extraction | `consultation_type_id=UUID` (derived from template) |
| `recording_sessions` | UPDATE (2) | After saving | `full_audio_data`, `session_status='completed'` |
| `audio_chunks` | DELETE | After stitching | Single chunk |
| `medical_extractions` | INSERT | After extraction | **⭐ Saves to DB** - `extraction_mode='full'`, all segments in JSON |
| `extraction_segments` | INSERT (multiple) | After extraction | **⭐ One row per segment** (CORE + ADDITIONAL) |
| `processing_jobs` | UPDATE (multiple) | During processing | Status updates |

**⚠️ Emotion extraction scheduled** - Background task runs after 20s

### Workflow 2B: VHRScreen.tsx File Upload (extractionMode = 'core' or 'additional')

**Same as Workflow 1** - No database save for extraction (frontend-only extraction)

### Workflow 3: RecordTab.tsx WebSocket Live Recording

| Table | Operation | When | Data |
|-------|-----------|------|------|
| **NONE** | **NONE** | **NONE** | **⚠️ No database operations at all** |

**Completely stateless:**
- No session tracking
- No audio storage
- No extraction storage
- Frontend-only extraction (no DB save)

---

## Key Differences: extraction_mode Behavior

### extractionMode = 'full' (Backend Extraction)

**VHRScreen.tsx File Upload:**
```typescript
// Frontend sends real template
template: "Prakash_Outpatient full"
extraction_mode: "full"

// Backend extracts ALL segments
// ✅ Saves to medical_extractions table
// ✅ Saves to extraction_segments table
// ✅ Updates session.consultation_type_id
// ✅ Schedules emotion extraction

// SSE returns complete insights
insights: { ...all CORE + ADDITIONAL segments... }

// Frontend displays in both sections
```

### extractionMode = 'core' or 'additional' (Frontend Extraction)

**VHRScreen.tsx Mic Recording OR File Upload:**
```typescript
// Frontend sends TRANSCRIPT_ONLY
template: "TRANSCRIPT_ONLY"
extraction_mode: undefined  // NULL

// Backend only transcribes
// ❌ No extraction
// ❌ No database save
// ❌ No emotion extraction

// SSE returns transcript only
insights: null

// Frontend extracts progressively
// ❌ No database save (standalone extraction)
```

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ WORKFLOW 1: VHRScreen.tsx - Mic Recording (extractionMode='full')  │
└─────────────────────────────────────────────────────────────────────┘

Frontend                     Backend                          Database
────────                     ───────                          ────────

Select: FULL mode
Click Record
  │
  ├─► POST /recording/start ──► INSERT recording_sessions
  │   template='TRANSCRIPT_ONLY'   (template_name, extraction_mode=NULL)
  │   extraction_mode=undefined
  │
  ├─► POST /chunk (0) ───────► INSERT audio_chunks (chunk 0)
  ├─► POST /chunk (1) ───────► INSERT audio_chunks (chunk 1)
  ├─► POST /chunk (2) ───────► INSERT audio_chunks (chunk 2)
  │   ...
  │
Click Stop
  │
  ├─► POST /chunk (last) ────► INSERT audio_chunks (last chunk)
  │   is_last=true             INSERT processing_jobs
  │                            START background processing
  │
  ├─► GET /processing/stream ─┐
  │   (SSE connection)         │
  │                            │ STITCHING ──► UPDATE jobs, DELETE chunks
  │                            │ TRANSCRIBING ─► UPDATE jobs
  │                            │ EXTRACTING ──► ❌ SKIPPED (TRANSCRIPT_ONLY)
  │                            │ SAVING ──────► UPDATE sessions (full_audio)
  │                            │
  │◄─ Event: transcript ───────┘
  │
  │  (Frontend receives transcript only, no insights)
  │
  ├─► POST /summary/extract ──► extract_summary_dynamic(mode='core')
  │   mode='core'               ❌ NO database save (standalone)
  │
  │◄─ CORE segments
  │
  ├─► POST /summary/extract ──► extract_summary_dynamic(mode='additional')
  │   mode='additional'         ❌ NO database save (standalone)
  │
  │◄─ ADDITIONAL segments
  │
Display CORE + ADDITIONAL


┌─────────────────────────────────────────────────────────────────────┐
│ WORKFLOW 2A: VHRScreen.tsx - File Upload (extractionMode='full')   │
└─────────────────────────────────────────────────────────────────────┘

Frontend                     Backend                          Database
────────                     ───────                          ────────

Select: FULL mode
Select file
  │
  ├─► POST /recording/start ──► INSERT recording_sessions
  │   template='Prakash_...'    (template_name='Prakash_...',
  │   extraction_mode='full'     extraction_mode='full')
  │
  ├─► POST /chunk ───────────► INSERT audio_chunks (single chunk)
  │   is_last=true              INSERT processing_jobs
  │                             START background processing
  │
  ├─► GET /processing/stream ─┐
  │   (SSE connection)         │
  │                            │ STITCHING ──► (trivial)
  │                            │ TRANSCRIBING ─► Gemini transcribe
  │                            │ EXTRACTING ──► ✅ perform_template_extraction()
  │                            │                 │
  │                            │                 ├─► UPDATE sessions
  │                            │                 │   (consultation_type_id)
  │                            │                 │
  │                            │                 ├─► extract_summary_dynamic
  │                            │                 │   (mode='full', ALL segments)
  │                            │                 │
  │                            │                 ├─► INSERT medical_extractions
  │                            │                 │   (full JSON with all segments)
  │                            │                 │
  │                            │                 ├─► INSERT extraction_segments
  │                            │                 │   (one row per segment)
  │                            │                 │
  │                            │                 └─► Schedule emotion extraction
  │                            │                     (20s delay, background)
  │                            │ SAVING ──────► UPDATE sessions (full_audio)
  │                            │
  │◄─ Event: complete ─────────┘
  │   transcript + insights (ALL segments)
  │
Display ALL segments


┌─────────────────────────────────────────────────────────────────────┐
│ WORKFLOW 2B: VHRScreen.tsx - File Upload (extractionMode='core')   │
└─────────────────────────────────────────────────────────────────────┘

Same as WORKFLOW 1 (Mic Recording)
- Backend: TRANSCRIPT_ONLY flow
- Frontend: Progressive extraction
- Database: No extraction save


┌─────────────────────────────────────────────────────────────────────┐
│ WORKFLOW 3: RecordTab.tsx - WebSocket Live (Ultra mode)            │
└─────────────────────────────────────────────────────────────────────┘

Frontend                     Backend                          Database
────────                     ───────                          ────────

Click Record
  │
  ├─► POST /ephemeral-token ──► Generate Gemini ephemeral token
  │                             ❌ NO database operations
  │◄─ ephemeral token
  │
  ├─► WebSocket to Gemini ───► (External - Google's servers)
  │   Live API                  ❌ NOT our backend!
  │   (Audio streaming)         ❌ NO database operations
  │
  │◄─ Live transcript chunks
  │
Click Stop
  │
  ├─► Close WebSocket
  │
  ├─► POST /summary/extract ──► extract_summary_dynamic(mode='core')
  │   mode='core'               ❌ NO database save (standalone)
  │
  │◄─ CORE segments
  │
  ├─► POST /summary/extract ──► extract_summary_dynamic(mode='additional')
  │   mode='additional'         ❌ NO database save (standalone)
  │
  │◄─ ADDITIONAL segments
  │
Display CORE + ADDITIONAL
```

---

## extraction_mode Values and Their Behavior

| extractionMode (Frontend) | template_name | extraction_mode (DB) | Backend Extraction | DB Save | Emotion Analysis |
|---------------------------|---------------|----------------------|--------------------|---------|------------------|
| `'full'` | Real template | `'full'` | ✅ Yes (ALL segments) | ✅ Yes | ✅ Yes |
| `'core'` | `'TRANSCRIPT_ONLY'` | `NULL` | ❌ No | ❌ No | ❌ No |
| `'additional'` | `'TRANSCRIPT_ONLY'` | `NULL` | ❌ No | ❌ No | ❌ No |

**Frontend Extraction (mode='core' or 'additional'):**
- Always uses standalone `/summary/extract` endpoint
- NO correlation_id provided
- NO database save (WORKFLOW 2 path)
- Returns extraction results only in API response

**Backend Extraction (mode='full'):**
- Uses `perform_template_extraction()` function
- Saves to `medical_extractions` and `extraction_segments` tables
- Updates `session.consultation_type_id`
- Schedules emotion extraction (if enabled for consultation type)

---

## Database Tables Reference

### recording_sessions
- Stores recording session metadata
- `template_name`: Either real template OR 'TRANSCRIPT_ONLY'
- `extraction_mode`: 'full' OR NULL
- `consultation_type_id`: NULL initially, updated during extraction (if extraction_mode='full')

### audio_chunks
- Temporary storage for audio chunks during upload
- Deleted after stitching into `full_audio_data`

### processing_jobs
- Tracks background processing status
- `job_status`: 'pending', 'loading', 'stitching', 'transcribing', 'extracting', 'saving', 'completed', 'failed'

### medical_extractions
- **Only populated when extraction_mode='full'**
- Stores complete extraction results as JSON
- Links to `session_id`, `consultation_type_id`, `doctor_id`, `patient_id`

### extraction_segments
- **Only populated when extraction_mode='full'**
- One row per extracted segment (e.g., DIAGNOSIS, CHIEF_COMPLAINTS, etc.)
- Links to `extraction_id` (medical_extractions.id)

---

## Emotion Extraction

**When it runs:**
- Only when `extraction_mode='full'`
- Only if `consultation_type.enable_emotion_analysis = true`
- Scheduled as background task with 20-second delay

**Database:**
- Results stored in emotion analysis tables (not shown in this trace)

**Code:**
```python
# backend/services/extraction_service.py:198-214
if enable_emotion:
    from services.background_tasks import schedule_emotion_extraction

    await schedule_emotion_extraction(
        transcript=transcript,
        extraction_id=extraction_id,
        consultation_type_id=consultation_type_id,
        delay_seconds=20
    )
```

---

## Common Misconceptions

### ❌ "VHRScreen mic recording saves extractions to DB"
**FALSE** - Mic recording uses TRANSCRIPT_ONLY, frontend extraction doesn't save.

### ❌ "RecordTab saves sessions to database"
**FALSE** - RecordTab uses WebSocket directly to Gemini, no DB involvement at all.

### ❌ "All extractions update consultation_type_id"
**FALSE** - Only backend extraction (mode='full') updates consultation_type_id.

### ❌ "extractionMode 'core' and 'additional' are saved separately"
**FALSE** - These are frontend-only extractions, no DB save.

### ✅ "Only file upload with mode='full' saves to database"
**TRUE** - This is the ONLY workflow that saves extraction results to DB.

# Development Plan

**Last Updated:** 2025-11-07 00:48:31

## Current Plan

# VHR Screen Implementation Plan (Revised)

## Overview
Create a new VHR (Virtual Health Record) screen by duplicating MedicalSummaryTab and integrating recording capabilities from Home (Option1Tab) and Live (RecordTab) screens. Use their exact API patterns and implementation logic.

## Phase 1: Create Base VHR Screen (Duplicate MedicalSummaryTab)

### 1.1 Create New Component
- **File**: `app/components/VHRScreen.tsx`
- Copy entire `app/components/MedicalSummaryTab.tsx` as starting point
- Rename component from `MedicalSummaryTab` to `VHRScreen`
- Update header: "Virtual Health Record (VHR)"

### 1.2 Add Patient ID Input
- Add state: `const [patientId, setPatientId] = useState<string>('')`
- Add input field after processing mode selector, before transcript section
- UI: Text input with label "Patient ID" and validation
- For now: Accept any dummy value (e.g., "PAT-12345")

### 1.3 Add to Main App Navigation
- Update `app/page.tsx` to add VHR tab/screen
- Keep existing Medical Summary screen intact (no modifications)

## Phase 2: Replace Transcript Input with Recording Controls

### 2.1 Add Recording State (Copy from Option1Tab.tsx)
**Reference: Option1Tab.tsx lines 40-64**
```typescript
// Input mode
const [inputMode, setInputMode] = useState<'mic' | 'upload' | null>(null);

// Chunked recording state (for fast/default/thorough modes)
const recordingManagerRef = useRef<RecordingManager | null>(null);
const [isRecording, setIsRecording] = useState(false);
const [isPaused, setIsPaused] = useState(false);
const [recordingDuration, setRecordingDuration] = useState(0);
const [chunksUploaded, setChunksUploaded] = useState(0);
const [isSubmitting, setIsSubmitting] = useState(false);
const [processingProgress, setProcessingProgress] = useState<ProcessingProgress | null>(null);
const eventSourceRef = useRef<EventSource | null>(null);

// WebSocket recording state (for ultra mode)
const sessionManagerRef = useRef<LiveSessionManager | null>(null);
const [liveTranscript, setLiveTranscript] = useState('');
const [isExtracting, setIsExtracting] = useState(false);

// Final transcript (from either method)
const [transcript, setTranscript] = useState('');
```

### 2.2 Create Recording Controls UI
Replace transcript textarea with:
- **Two Buttons (mutually exclusive):**
  - 🎤 Mic Button - Start/Stop/Pause recording
  - 📁 Upload Button - Open file picker
- **Recording Display:**
  - Chunked: Timer + chunk counter
  - WebSocket: Real-time transcript display
- **File Upload Display:**
  - File name + processing progress

## Phase 3: Implement Recording Methods (Using Exact Patterns)

### 3.1 Import Required Dependencies

**From Option1Tab.tsx (lines 1-12):**
```typescript
import { RecordingManager } from '../services/recordingService';
```

**From RecordTab.tsx (lines 1-10):**
```typescript
import { 
  startLiveTranscriptionSession,
  LiveSessionManager 
} from '../services/geminiClient';
```

### 3.2 Chunked Recording Implementation (fast/default/thorough)

**EXACT COPY FROM Option1Tab.tsx**

#### 3.2.1 Start Recording Function
**Reference: Option1Tab.tsx lines 92-125**
```typescript
const handleStartRecording = async () => {
  try {
    setIsRecording(true);
    setInputMode('mic');
    
    // Create RecordingManager instance
    recordingManagerRef.current = new RecordingManager();
    
    // Configuration from state
    const config = {
      template: selectedTemplate?.template_code || 'OP_CORE',
      doctorName: selectedDoctorId || 'Unknown',
      patientId: patientId || 'UNKNOWN',
      transcriptionEngine: 'gemini',
      processingMode: processingMode, // 'fast' | 'default' | 'thorough'
      chunkDurationSeconds: 10,
    };
    
    // Start recording with callback
    await recordingManagerRef.current.startRecording(
      config,
      (chunkIndex: number) => {
        setChunksUploaded(chunkIndex + 1);
      }
    );
    
    // Start duration timer
    const timer = setInterval(() => {
      setRecordingDuration((prev) => prev + 1);
    }, 1000);
    
  } catch (error) {
    console.error('Failed to start recording:', error);
    setIsRecording(false);
    setInputMode(null);
  }
};
```

#### 3.2.2 Stop Recording Function
**Reference: Option1Tab.tsx lines 141-188**
```typescript
const handleStopAndSubmit = async () => {
  if (!recordingManagerRef.current) return;
  
  try {
    setIsSubmitting(true);
    
    // Stop recording and upload final chunk
    const submissionId = await recordingManagerRef.current.stopAndSubmit();
    
    // Connect to SSE endpoint for progress
    const eventSource = new EventSource(
      `${API_BASE_URL}/api/v1/option1/recording/processing/${submissionId}/stream`
    );
    eventSourceRef.current = eventSource;
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.event === 'progress') {
        setProcessingProgress({
          stage: data.stage,
          percentage: data.percentage,
          message: data.message,
        });
      } else if (data.event === 'complete') {
        // Extract transcript from result
        setTranscript(data.data.transcript);
        
        // Close SSE connection
        eventSource.close();
        eventSourceRef.current = null;
        
        // Reset recording state
        setIsRecording(false);
        setIsSubmitting(false);
        setProcessingProgress(null);
        
        // Trigger progressive extraction (CORE then ADDITIONAL)
        handleProgressiveExtraction(data.data.transcript);
      } else if (data.event === 'error') {
        console.error('Processing error:', data.error);
        eventSource.close();
        setIsSubmitting(false);
      }
    };
    
    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      eventSource.close();
      setIsSubmitting(false);
    };
    
  } catch (error) {
    console.error('Failed to stop recording:', error);
    setIsSubmitting(false);
  }
};
```

#### 3.2.3 Cancel Recording Function
**Reference: Option1Tab.tsx lines 190-198**
```typescript
const handleCancelRecording = async () => {
  if (!recordingManagerRef.current) return;
  
  try {
    await recordingManagerRef.current.cancel();
    setIsRecording(false);
    setIsPaused(false);
    setInputMode(null);
    setChunksUploaded(0);
    setRecordingDuration(0);
  } catch (error) {
    console.error('Failed to cancel recording:', error);
  }
};
```

### 3.3 WebSocket Recording Implementation (ultra mode)

**EXACT COPY FROM RecordTab.tsx**

#### 3.3.1 Start Recording Function
**Reference: RecordTab.tsx lines 145-189**
```typescript
const startWebSocketRecording = async () => {
  try {
    setIsRecording(true);
    setInputMode('mic');
    setLiveTranscript('');
    
    // Fetch ephemeral token from backend
    const tokenResponse = await fetch(`${API_BASE_URL}/api/ephemeral-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    
    if (!tokenResponse.ok) {
      throw new Error('Failed to fetch ephemeral token');
    }
    
    const { token } = await tokenResponse.json();
    
    // Start live transcription session
    const sessionManager = await startLiveTranscriptionSession(
      token,
      (text: string, isFinal: boolean) => {
        // Update transcript in real-time
        setLiveTranscript((prev) => {
          if (isFinal) {
            return prev + text + ' ';
          }
          return prev;
        });
      },
      (error: Error) => {
        console.error('Transcription error:', error);
        setIsRecording(false);
        setInputMode(null);
      }
    );
    
    sessionManagerRef.current = sessionManager;
    
  } catch (error) {
    console.error('Failed to start WebSocket recording:', error);
    setIsRecording(false);
    setInputMode(null);
  }
};
```

#### 3.3.2 Stop Recording Function
**Reference: RecordTab.tsx lines 209-268**
```typescript
const stopWebSocketRecording = async () => {
  if (!sessionManagerRef.current) return;
  
  try {
    // Close WebSocket connection
    await sessionManagerRef.current.stop();
    sessionManagerRef.current = null;
    
    // Store final transcript
    setTranscript(liveTranscript.trim());
    
    // Reset recording state
    setIsRecording(false);
    
    // Trigger progressive extraction (CORE then ADDITIONAL)
    handleProgressiveExtraction(liveTranscript.trim());
    
  } catch (error) {
    console.error('Failed to stop WebSocket recording:', error);
    setIsRecording(false);
  }
};
```

### 3.4 File Upload Implementation

**EXACT COPY FROM Option1Tab.tsx lines 200-315**

```typescript
const handleFileUpload = async (file: File) => {
  try {
    setInputMode('upload');
    setIsSubmitting(true);
    
    // Show info for ultra mode
    if (processingMode === 'ultra') {
      console.info('File upload uses standard processing (not ultra mode)');
    }
    
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
    
    // Create recording session (same API as live recording)
    const recordingManager = new RecordingManager();
    
    const config = {
      template: selectedTemplate?.template_code || 'OP_CORE',
      doctorName: selectedDoctorId || 'Unknown',
      patientId: patientId || 'UNKNOWN',
      transcriptionEngine: 'gemini',
      processingMode: processingMode,
      chunkDurationSeconds: 0, // Not used for file upload
    };
    
    await recordingManager.startRecording(config, () => {});
    
    // Upload entire file as single chunk
    await recordingManager.uploadChunk(base64Audio, 0, true);
    
    // Get submission ID
    const submissionId = await recordingManager.stopAndSubmit();
    
    // Connect to SSE for progress (same as mic recording)
    const eventSource = new EventSource(
      `${API_BASE_URL}/api/v1/option1/recording/processing/${submissionId}/stream`
    );
    eventSourceRef.current = eventSource;
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.event === 'progress') {
        setProcessingProgress({
          stage: data.stage,
          percentage: data.percentage,
          message: data.message,
        });
      } else if (data.event === 'complete') {
        // Extract transcript from result
        setTranscript(data.data.transcript);
        
        // Close SSE connection
        eventSource.close();
        eventSourceRef.current = null;
        
        // Reset state
        setIsSubmitting(false);
        setProcessingProgress(null);
        
        // Trigger progressive extraction
        handleProgressiveExtraction(data.data.transcript);
      } else if (data.event === 'error') {
        console.error('Processing error:', data.error);
        eventSource.close();
        setIsSubmitting(false);
      }
    };
    
  } catch (error) {
    console.error('Failed to upload file:', error);
    setIsSubmitting(false);
    setInputMode(null);
  }
};
```

### 3.5 Conditional Recording Dispatcher

```typescript
const handleStartRecording = async () => {
  if (processingMode === 'ultra') {
    await startWebSocketRecording();
  } else {
    await handleStartChunkedRecording();
  }
};

const handleStopRecording = async () => {
  if (processingMode === 'ultra') {
    await stopWebSocketRecording();
  } else {
    await handleStopAndSubmit();
  }
};
```

## Phase 4: Progressive Extraction Integration

### 4.1 Progressive Extraction Function
**Reference: MedicalSummaryTab.tsx lines 84-155**

This function is called automatically after recording completes (either chunked or WebSocket)

```typescript
const handleProgressiveExtraction = async (transcriptText: string) => {
  if (!transcriptText.trim() || !selectedTemplate) return;
  
  const extractionModel = getExtractionModel(processingMode);
  
  try {
    // Step 1: Extract CORE segments (immediate)
    setLoadingCore(true);
    setCoreExtractionData(null);
    setAdditionalExtractionData(null);
    
    const coreResponse = await extractMedicalSummary({
      transcript: transcriptText.trim(),
      consultation_type_code: selectedTemplate.consultation_type_code as ConsultationTypeCode,
      counsellor_id: selectedDoctorId || undefined,
      template_code: selectedTemplate.template_code,
      mode: 'core',
      model: extractionModel,
    });
    
    if (!coreResponse.success) {
      throw new Error('Core extraction failed');
    }
    
    setCoreExtractionData(coreResponse);
    setLoadingCore(false);
    
    // Step 2: Extract ADDITIONAL segments in background
    extractAdditionalSegments(extractionModel, transcriptText.trim());
    
  } catch (err) {
    console.error('Core extraction failed:', err);
    setLoadingCore(false);
  }
};

const extractAdditionalSegments = async (extractionModel: string, transcriptText: string) => {
  if (!transcriptText.trim() || !selectedTemplate) return;
  
  try {
    setLoadingAdditional(true);
    
    const additionalResponse = await extractMedicalSummary({
      transcript: transcriptText.trim(),
      consultation_type_code: selectedTemplate.consultation_type_code as ConsultationTypeCode,
      counsellor_id: selectedDoctorId || undefined,
      template_code: selectedTemplate.template_code,
      mode: 'additional',
      model: extractionModel,
    });
    
    if (additionalResponse.success) {
      setAdditionalExtractionData(additionalResponse);
    }
  } catch (err) {
    console.error('Additional extraction failed:', err);
  } finally {
    setLoadingAdditional(false);
  }
};
```

### 4.2 API Endpoint Used
**Backend**: `POST /api/v1/summary/extract`

**Request Format:**
```typescript
{
  transcript: string,
  consultation_type_code: 'OP' | 'DISCHARGE' | 'RESPIRATORY',
  counsellor_id?: string,
  template_code: string,
  mode: 'core' | 'additional' | 'full',
  model: 'gemini-2.5-flash' | 'gemini-2.5-pro'
}
```

## Phase 5: UI Layout & Controls

### 5.1 Recording Controls UI

**From Option1Tab.tsx lines 653-734 (Chunked Recording):**
```tsx
{inputMode === 'mic' && !isRecording && (
  <button onClick={handleStartRecording}>
    🎤 Start Recording
  </button>
)}

{isRecording && !isPaused && (
  <>
    <button onClick={handlePauseRecording}>⏸ Pause</button>
    <button onClick={handleStopRecording}>⏹ Stop</button>
    <button onClick={handleCancelRecording}>✖ Cancel</button>
    <div>Duration: {formatTime(recordingDuration)}</div>
    <div>Chunks: {chunksUploaded}</div>
  </>
)}
```

**From RecordTab.tsx lines 308-334 (WebSocket Recording):**
```tsx
{inputMode === 'mic' && !isRecording && (
  <button onClick={handleStartRecording}>
    🎤 Start Recording
  </button>
)}

{isRecording && (
  <>
    <button onClick={handleStopRecording}>⏹ Stop</button>
    <div>Real-time Transcript:</div>
    <div>{liveTranscript}</div>
  </>
)}
```

### 5.2 File Upload UI

**From Option1Tab.tsx lines 735-780:**
```tsx
{!isRecording && inputMode !== 'mic' && (
  <input
    type="file"
    accept="audio/*"
    onChange={(e) => {
      if (e.target.files?.[0]) {
        handleFileUpload(e.target.files[0]);
      }
    }}
  />
)}
```

### 5.3 Processing Progress UI

**From Option1Tab.tsx lines 565-581 (SSE Progress):**
```tsx
{processingProgress && (
  <div>
    <div>Stage: {processingProgress.stage}</div>
    <div>Progress: {processingProgress.percentage}%</div>
    <div>{processingProgress.message}</div>
    <progress value={processingProgress.percentage} max={100} />
  </div>
)}
```

## Phase 6: Validation & Error Handling

### 6.1 Input Validation
```typescript
const canStartRecording = () => {
  return (
    selectedDoctorId &&
    selectedTemplate &&
    processingMode &&
    patientId.trim() !== '' &&
    !isRecording &&
    !isSubmitting
  );
};
```

### 6.2 Error Handling
- Network errors during recording
- Token generation failures (ultra mode)
- Recording permission denied
- File format validation
- SSE connection failures

## Phase 7: Testing

### 7.1 Test Matrix

| Mode | Mic Recording | File Upload | Expected API |
|------|---------------|-------------|--------------|
| Ultra | WebSocket (RecordTab pattern) | Chunked (Option1Tab pattern) | ephemeral-token + Gemini Live |
| Fast | Chunked (Option1Tab pattern) | Chunked (Option1Tab pattern) | /api/v1/option1/recording/* |
| Default | Chunked (Option1Tab pattern) | Chunked (Option1Tab pattern) | /api/v1/option1/recording/* |
| Thorough | Chunked (Option1Tab pattern) | Chunked (Option1Tab pattern) | /api/v1/option1/recording/* |

### 7.2 Progressive Extraction Testing
- ✅ CORE extraction completes first
- ✅ ADDITIONAL extraction loads in background
- ✅ Results display with green/blue borders
- ✅ Download combines both datasets

## File Changes Summary

**New Files:**
- `app/components/VHRScreen.tsx` - Main VHR component (copies exact patterns from Option1Tab + RecordTab)

**Modified Files:**
- `app/page.tsx` - Add VHR tab to navigation

**Reused (No Changes):**
- `app/components/MedicalSummaryTab.tsx` - Keep intact
- `app/components/Option1Tab.tsx` - Reference only
- `app/components/RecordTab.tsx` - Reference only
- `app/services/recordingService.ts` - Import and use RecordingManager
- `app/services/geminiClient.ts` - Import and use startLiveTranscriptionSession
- `lib/processingModes.ts` - Import and use getExtractionModel

## Key Implementation Points

1. **Chunked Recording (fast/default/thorough):**
   - Copy exact implementation from Option1Tab.tsx lines 92-315
   - Uses RecordingManager class
   - APIs: `/api/v1/option1/recording/start`, `/chunk`, `/stream`
   - SSE progress tracking

2. **WebSocket Recording (ultra):**
   - Copy exact implementation from RecordTab.tsx lines 145-268
   - Uses ephemeral tokens + geminiClient
   - APIs: `/api/ephemeral-token` + Gemini Live WebSocket
   - Real-time transcript display

3. **File Upload (all modes):**
   - Copy exact implementation from Option1Tab.tsx lines 200-315
   - Always uses chunked recording API
   - Single chunk upload with `is_last=true`

4. **Progressive Extraction (all modes):**
   - Copy exact implementation from MedicalSummaryTab.tsx lines 84-155
   - API: `POST /api/v1/summary/extract` with mode='core' then mode='additional'
   - Triggered automatically after recording completes

## Success Criteria

✅ VHR screen functional without breaking existing screens
✅ Exact API patterns from Option1Tab and RecordTab preserved
✅ Chunked recording works (fast/default/thorough modes)
✅ WebSocket recording works (ultra mode)
✅ File upload works in all modes
✅ Progressive extraction displays correctly (CORE → ADDITIONAL)
✅ All state management, error handling, and cleanup logic replicated

---

*This file is automatically updated by Claude Code hooks when plans are created.*

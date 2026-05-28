# API Flow Analysis - Frontend to Backend

## Overview
Analysis of all API calls from frontend components to backend endpoints, specifically focusing on which endpoints were affected by the insights.py refactoring.

---

## VHRScreen.tsx API Flow

### 1. Chunked Recording Flow (Fast/Default/Thorough modes)
```
User Action: Click "Record" button
↓
Frontend: startChunkedRecording()
↓
RecordingManager.startRecording() → POST /api/v1/option1/recording/start
↓
MediaRecorder captures audio chunks → POST /api/v1/option1/recording/chunk (multiple)
↓
User clicks "Stop"
↓
RecordingManager.stopAndSubmit() → POST /api/v1/option1/recording/chunk (is_last=true)
↓
SSE Stream: GET /api/v1/option1/recording/processing/{submission_id}/stream
  - Returns: { transcript, insights (if backend extraction), metrics }
↓
Frontend: handleProgressiveExtraction()
↓
extractMedicalSummary() → POST /api/v1/summary/extract
  Parameters: {
    transcript,
    consultation_type_code,
    doctor_id,
    template_name,
    mode: 'core',
    model
  }
↓
Display CORE results
↓
extractAdditionalSegments() (if extractionMode === 'additional')
↓
extractMedicalSummary() → POST /api/v1/summary/extract
  Parameters: {
    transcript,
    consultation_type_code,
    doctor_id,
    template_name,
    mode: 'additional',
    model
  }
↓
Display ADDITIONAL results
```

**Endpoints Used:**
- ✅ `/api/v1/option1/recording/start` - **NOT AFFECTED** (recording API)
- ✅ `/api/v1/option1/recording/chunk` - **NOT AFFECTED** (recording API)
- ✅ `/api/v1/option1/recording/processing/{id}/stream` - **NOT AFFECTED** (SSE API)
- ✅ `/api/v1/summary/extract` - **NOT AFFECTED** (uses extract_summary_dynamic, not insights.py)

**Uses insights.py?** ❌ **NO** - Uses `/api/v1/summary/extract` which calls `extract_summary_dynamic()` directly

---

### 2. WebSocket Recording Flow (Ultra mode)
```
User Action: Click "Record" button (with ultra mode selected)
↓
Frontend: startWebSocketRecording()
↓
Fetch ephemeral token: POST /api/ephemeral-token
↓
startLiveTranscriptionSession(token)
↓
WebSocket connection to Gemini Live API (client-side, uses ephemeral token)
↓
Real-time transcription displayed as user speaks
↓
User clicks "Stop"
↓
Frontend: stopWebSocketRecording()
↓
Close WebSocket session
↓
Frontend: handleProgressiveExtraction()
↓
extractMedicalSummary() → POST /api/v1/summary/extract (mode: 'core')
↓
Display CORE results
↓
extractMedicalSummary() → POST /api/v1/summary/extract (mode: 'additional')
↓
Display ADDITIONAL results
```

**Endpoints Used:**
- ✅ `/api/ephemeral-token` - **NOT AFFECTED** (ephemeral token generation)
- ✅ Gemini Live API (WebSocket) - **NOT AFFECTED** (external Google API)
- ✅ `/api/v1/summary/extract` - **NOT AFFECTED** (uses extract_summary_dynamic)

**Uses insights.py?** ❌ **NO** - Uses `/api/v1/summary/extract`

---

### 3. File Upload Flow
```
User Action: Click "Upload" and select file
↓
Frontend: handleFileUpload()
↓
Convert file to base64
↓
RecordingManager.startSessionWithoutMicrophone()
  → POST /api/v1/option1/recording/start
↓
RecordingManager.uploadChunk(base64, 0, is_last=true, mimeType)
  → POST /api/v1/option1/recording/chunk
↓
SSE Stream: GET /api/v1/option1/recording/processing/{submission_id}/stream
↓
If extractionMode === 'full':
  - Backend handles extraction, display all results
Else:
  - Frontend: handleProgressiveExtraction()
  - extractMedicalSummary() → POST /api/v1/summary/extract (mode: 'core')
  - extractMedicalSummary() → POST /api/v1/summary/extract (mode: 'additional')
```

**Endpoints Used:**
- ✅ `/api/v1/option1/recording/start` - **NOT AFFECTED**
- ✅ `/api/v1/option1/recording/chunk` - **NOT AFFECTED**
- ✅ `/api/v1/option1/recording/processing/{id}/stream` - **NOT AFFECTED**
- ✅ `/api/v1/summary/extract` - **NOT AFFECTED**

**Uses insights.py?** ❌ **NO** - Uses `/api/v1/summary/extract`

---

## RecordTab.tsx API Flow

### Live Recording with Progressive Extraction
```
User Action: Select doctor, template, and click "Start Recording"
↓
Frontend: startRecording()
↓
Fetch ephemeral token: POST /api/ephemeral-token
↓
startLiveTranscriptionSession(token)
↓
WebSocket connection to Gemini Live API (client-side)
↓
Real-time transcription displayed
↓
User clicks "Stop"
↓
Frontend: stopRecording()
↓
Close WebSocket session
↓
Frontend: handleProgressiveExtraction()
↓
extractMedicalSummary() → POST /api/v1/summary/extract
  Parameters: {
    transcript,
    doctor_id,
    template_name,
    processing_mode,
    mode: 'core'
  }
↓
Display CORE results
↓
If extractionMode !== 'core':
  extractAdditionalSegments()
  → extractMedicalSummary() with mode: 'additional'
↓
Display ADDITIONAL results
```

**Endpoints Used:**
- ✅ `/api/ephemeral-token` - **NOT AFFECTED**
- ✅ Gemini Live API (WebSocket) - **NOT AFFECTED**
- ✅ `/api/v1/summary/extract` - **NOT AFFECTED**

**Uses insights.py?** ❌ **NO** - Uses `/api/v1/summary/extract`

---

## Summary of Findings

### ❌ `/api/insights` Endpoint Status: **ORPHANED - NOT USED**

The refactored `/api/insights` endpoint is **NOT called by any frontend code**. All frontend components use `/api/v1/summary/extract` instead.

### Endpoints Actually Used:

| Endpoint | Used By | Affected by insights.py Refactoring? |
|----------|---------|-------------------------------------|
| `/api/v1/summary/extract` | VHRScreen, RecordTab | ❌ **NO** - Different router |
| `/api/v1/option1/recording/*` | VHRScreen (recording) | ❌ **NO** - Recording API |
| `/api/ephemeral-token` | VHRScreen, RecordTab | ❌ **NO** - Token generation |
| Gemini Live API | VHRScreen, RecordTab | ❌ **NO** - External API |

### `/api/insights` Endpoint Reference in Config

Found in `lib/config.ts`:
```typescript
export const API_ENDPOINTS = {
  insights: `${BACKEND_API_URL}/api/insights`,  // ⚠️ DEFINED BUT NOT USED
  ephemeralToken: `${BACKEND_API_URL}/api/ephemeral-token`,
} as const;
```

**Note**: The `API_ENDPOINTS.insights` is defined but **never imported or used** in any component.

---

## Impact Assessment

### ✅ Zero Impact on Current Frontend
The insights.py refactoring has **ZERO IMPACT** on the current frontend because:
1. VHRScreen uses `/api/v1/summary/extract` (not `/api/insights`)
2. RecordTab uses `/api/v1/summary/extract` (not `/api/insights`)
3. No component imports or uses `API_ENDPOINTS.insights`

### Potential Future Use Cases
The `/api/insights` endpoint could be used for:
- Quick transcript-only extraction without doctor/template context
- Testing extraction without database dependencies
- External API integrations
- Mobile apps (if they don't use the full template system)

### Recommended Actions

1. **Option A: Keep `/api/insights` for future use**
   - Document it as a simplified extraction endpoint
   - Update examples to show use cases
   - Keep it as alternative to `/api/v1/summary/extract`

2. **Option B: Remove `/api/insights` entirely**
   - Remove from `backend/routers/insights.py`
   - Remove from `backend/main.py` router registration
   - Remove from `lib/config.ts` API_ENDPOINTS
   - Update documentation

3. **Option C: Deprecate and mark for removal** (Recommended)
   - Add deprecation warning in docstring
   - Keep for backward compatibility
   - Plan removal in future version

---

## Extraction Flow Comparison

### Old (Psychiatry Templates - REMOVED):
```
POST /api/insights
Body: {
  transcript: "...",
  templates: ["SMALL", "CONCISE"]  // Hardcoded psychiatry templates
}
↓
Lambda functions with hardcoded UUID
↓
Multiple psychiatry extraction functions
↓
Parallel processing
```

### New (Dynamic Database-Driven):
```
POST /api/insights
Body: {
  transcript: "...",
  consultation_type_code: "OP",
  mode: "core",
  doctor_id: null,
  model: "gemini-2.5-pro"
}
↓
Database lookup: OP → UUID
↓
extract_summary_dynamic()
↓
Dynamic prompt generation from database
```

### Actual Frontend (Both VHRScreen and RecordTab):
```
POST /api/v1/summary/extract
Body: {
  transcript: "...",
  consultation_type_code: "OP",
  doctor_id: "doctor-uuid",
  template_name: "template-name",
  mode: "core",
  model: "gemini-2.5-pro"
}
↓
Database lookup: OP + template_name → configuration
↓
extract_summary_dynamic()
↓
Dynamic prompt generation with template overrides
```

---

## Conclusion

**The insights.py refactoring does NOT affect VHRScreen or RecordTab.**

Both components use a completely different API (`/api/v1/summary/extract`) that was not modified in this refactoring. The `/api/insights` endpoint exists but is orphaned - no frontend code uses it.

**Date**: 2025-11-10
**Analysis Version**: 1.0

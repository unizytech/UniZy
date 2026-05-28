# Merge API Documentation

This document describes the backend merge API endpoints and how to integrate them into a React Native application. The merge feature allows combining multiple medical extractions into a unified record.

## Table of Contents
- [Overview](#overview)
- [ID Relationships](#id-relationships)
- [API Endpoints](#api-endpoints)
- [TypeScript Types](#typescript-types)
- [Usage Flow](#usage-flow)
- [React Native Integration Examples](#react-native-integration-examples)

---

## Overview

The merge system supports:
1. **Multiple Extraction Merge** - Combine 2+ extractions from the database
2. **JSON Upload Merge** - Upload external JSON data and merge with existing extractions
3. **Schema Transformation** - Automatically transform OPHTHAL_OCR (external OCR data) to OPHTHAL_FULL format
4. **Category-based Deep Merge** - Intelligent merging within category families (e.g., OPHTHALMOLOGY_FAMILY)

### Merge Strategies

| Strategy | Description |
|----------|-------------|
| `latest_wins` | Later extractions override earlier ones (default) |
| `first_wins` | Earlier extractions take precedence |
| `smart_merge` | Intelligent field-level merging based on data quality |

---

## ID Relationships

Understanding the relationship between different IDs is crucial for using the merge API:

```
Recording Flow:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  1. POST /recording/start                                               │
│     └── Returns: correlation_id (same as session_id)                    │
│                                                                         │
│  2. POST /recording/chunk (multiple times)                              │
│     └── Uses: correlation_id                                            │
│     └── Final chunk returns: submission_id                              │
│                                                                         │
│  3. GET /recording/processing/{submission_id}/stream                    │
│     └── SSE progress updates                                            │
│     └── On completion: extraction saved to database                     │
│                                                                         │
│  4. GET /extractions/by-submission/{submission_id}                      │
│     └── Returns: extraction_id (for merge API)                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### ID Types

| ID Type | Generated When | Stored In | Purpose |
|---------|---------------|-----------|---------|
| `session_id` / `correlation_id` | Recording starts | `recording_sessions.id` | Links all chunks of a recording |
| `submission_id` | Final chunk uploaded | `processing_jobs.submission_id` | Tracks processing job, SSE endpoint |
| `extraction_id` | Extraction saved | `medical_extractions.id` | **Used by merge API** |

### Converting Between IDs

If you only have a `submission_id` (from recording flow) and need an `extraction_id` (for merge API):

```
GET /api/v1/extractions/by-submission/{submission_id}
```

If you only have a `session_id` (from recording start):

```
GET /api/v1/extractions/by-session/{session_id}
```

### Direct Merge with Submission IDs

**NEW:** The merge API now accepts `source_submission_ids` directly, eliminating the need for a separate lookup step:

```json
// Instead of this (two-step):
// 1. GET /extractions/by-submission/{submission_id} → extraction_id
// 2. POST /merge with source_extraction_ids

// You can now do this (one-step):
POST /api/v1/extractions/merge
{
  "source_submission_ids": ["submission-uuid-1", "submission-uuid-2"],
  "target_consultation_type_code": "OPHTHAL_FULL",
  "doctor_id": "doctor-uuid"
}
```

The backend automatically resolves submission_ids to extraction_ids.

---

## API Endpoints

Base URL: `http://localhost:8000` (or your production backend URL)

### 1. Preview Merge

**POST** `/api/v1/extractions/merge/preview`

Generates a preview of the merged result without saving to database. Validation is performed automatically.

#### Request Body

**Option A: Using extraction_ids**
```json
{
  "source_extraction_ids": ["uuid-1", "uuid-2"],
  "target_consultation_type_code": "OPHTHAL_FULL",
  "doctor_id": "doctor-uuid",
  "uploaded_json": {
    "data": { ... },
    "source_type": "OPHTHAL_OCR"
  }
}
```

**Option B: Using submission_ids (recommended for recording flow)**
```json
{
  "source_submission_ids": ["submission-uuid-1", "submission-uuid-2"],
  "target_consultation_type_code": "OPHTHAL_FULL",
  "doctor_id": "doctor-uuid"
}
```

#### Request Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_extraction_ids` | `string[]` | No* | Array of extraction UUIDs to merge |
| `source_submission_ids` | `string[]` | No* | Array of submission UUIDs (auto-resolved to extraction_ids) |
| `target_consultation_type_code` | `string` | Yes | Target consultation type code |
| `doctor_id` | `string` | Yes | Doctor UUID performing the merge |
| `uploaded_json` | `object` | No | External JSON data to include in merge |

*Use either `source_extraction_ids` OR `source_submission_ids`, not both.

#### Response
```json
{
  "success": true,
  "extraction_id": null,
  "submission_id": null,
  "merged_data": {
    "patientInfo": { ... },
    "clinicalHistory": { ... },
    "examination": { ... }
  },
  "merge_metadata": {
    "source_count": 3,
    "target_type_code": "OPHTHAL_FULL",
    "merge_timestamp": "2025-12-02T10:30:00Z",
    "doctor_confirmed": false,
    "conflict_count": 1,
    "conflicts_resolved": ["diagnosis"],
    "cross_type_scenario": "SAME_TYPE",
    "consultation_types_merged": ["OPHTHAL_FULL", "OPHTHAL_FULL"]
  },
  "preview": true
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| `success` | `boolean` | Whether preview was successful |
| `extraction_id` | `null` | Always null for preview (not saved) |
| `submission_id` | `null` | Always null for preview (not saved) |
| `merged_data` | `object` | Preview of the merged extraction data |
| `merge_metadata` | `object` | Metadata about the merge operation |
| `preview` | `boolean` | Always `true` for preview |

---

### 2. Execute Merge

**POST** `/api/v1/extractions/merge`

Performs the merge and saves the result to the database.

#### Request Body

**Option A: Using extraction_ids**
```json
{
  "source_extraction_ids": ["uuid-1", "uuid-2"],
  "target_consultation_type_code": "OPHTHAL_FULL",
  "doctor_id": "doctor-uuid",
  "merge_notes": "Merged pre-op and post-op extractions",
  "uploaded_json": {
    "data": { ... },
    "source_type": "OPHTHAL_OCR"
  }
}
```

**Option B: Using submission_ids (recommended for recording flow)**
```json
{
  "source_submission_ids": ["submission-uuid-1", "submission-uuid-2"],
  "target_consultation_type_code": "OPHTHAL_FULL",
  "doctor_id": "doctor-uuid",
  "merge_notes": "Merged pre-op and post-op extractions"
}
```

#### Request Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_extraction_ids` | `string[]` | No* | Array of extraction UUIDs to merge |
| `source_submission_ids` | `string[]` | No* | Array of submission UUIDs (auto-resolved to extraction_ids) |
| `target_consultation_type_code` | `string` | Yes | Target consultation type code |
| `doctor_id` | `string` | Yes | Doctor UUID performing the merge |
| `merge_notes` | `string` | No | Merge notes/comments |
| `uploaded_json` | `object` | No | External JSON data to include |

*Use either `source_extraction_ids` OR `source_submission_ids`, not both.

#### Response
```json
{
  "success": true,
  "extraction_id": "new-extraction-uuid",
  "submission_id": "new-submission-uuid",
  "merged_data": { ... },
  "merge_metadata": {
    "source_count": 3,
    "target_type_code": "OPHTHAL_FULL",
    "merge_timestamp": "2025-12-02T10:30:00Z",
    "doctor_confirmed": true,
    "conflict_count": 1,
    "conflicts_resolved": ["diagnosis"],
    "cross_type_scenario": "SAME_TYPE",
    "consultation_types_merged": ["OPHTHAL_FULL", "OPHTHAL_FULL"]
  },
  "preview": false
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| `success` | `boolean` | Whether merge was successful |
| `extraction_id` | `string` | UUID of the new merged extraction |
| `submission_id` | `string` | Submission UUID for tracking/lookup (use with `/by-submission/{id}`) |
| `merged_data` | `object` | The merged extraction data |
| `merge_metadata` | `object` | Metadata about the merge operation |
| `preview` | `boolean` | Always `false` for execute (indicates data was saved) |

---

### 3. Get Patient Timeline

**GET** `/api/v1/extractions/patient/{patient_id}/timeline`

Lists all extractions for a patient chronologically, useful for selecting merge sources.

#### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `patient_id` | `string` | Patient identifier |

#### Query Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `consultation_type_code` | `string` | Filter by consultation type |

#### Response
```json
{
  "patient_id": "patient-123",
  "extractions": [
    {
      "extraction_id": "uuid-1",
      "consultation_type_code": "OPHTHAL_FULL",
      "consultation_type_name": "Ophthalmology Full Consultation",
      "created_at": "2025-12-01T14:20:00Z",
      "doctor_name": "Dr. Smith",
      "is_merged": false,
      "source_count": 1,
      "segment_count": 25
    }
  ],
  "total_count": 5
}
```

---

### 4. Get Merge Lineage

**GET** `/api/v1/extractions/{extraction_id}/merge-info`

Get details about which extractions were merged to create a merged extraction.

#### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `extraction_id` | `string` | The merged extraction UUID |

#### Response
```json
{
  "merged_extraction_id": "uuid-merged",
  "is_merged": true,
  "source_extractions": [
    {
      "source_extraction_id": "uuid-1",
      "consultation_type_code": "OPHTHAL_FULL",
      "created_at": "2025-12-01T10:00:00Z",
      "doctor_name": "Dr. Smith",
      "merge_order": 1,
      "merge_strategy": "ai_contextual"
    }
  ],
  "merge_metadata": { ... }
}
```

---

### 5. Get Extraction by Submission ID

**GET** `/api/v1/extractions/by-submission/{submission_id}`

Looks up the extraction_id from a submission_id. Use this after completing a recording to get the extraction_id for merge operations.

#### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | `string` | The submission UUID from recording chunk upload |

#### Response (Success)
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "submission_id": "550e8400-e29b-41d4-a716-446655440050",
  "session_id": "550e8400-e29b-41d4-a716-446655440001",
  "consultation_type_code": "OPHTHAL_FULL",
  "doctor_id": "doctor-uuid",
  "patient_id": "patient-uuid",
  "created_at": "2025-12-02T10:30:00Z",
  "found": true,
  "message": null
}
```

#### Response (Processing In Progress)
```json
{
  "extraction_id": null,
  "submission_id": "550e8400-e29b-41d4-a716-446655440050",
  "session_id": "550e8400-e29b-41d4-a716-446655440001",
  "found": false,
  "message": "Processing in progress: EXTRACTING (75%). Extraction not yet available."
}
```

#### Response (Not Found)
```json
{
  "extraction_id": null,
  "submission_id": "550e8400-e29b-41d4-a716-446655440050",
  "found": false,
  "message": "No extraction found for this submission_id"
}
```

---

### 6. Get Extraction by Session ID

**GET** `/api/v1/extractions/by-session/{session_id}`

Looks up the extraction_id from a session_id (correlation_id from recording start).

#### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | `string` | The session UUID (correlation_id) from recording start |

#### Response
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "submission_id": "550e8400-e29b-41d4-a716-446655440050",
  "session_id": "550e8400-e29b-41d4-a716-446655440001",
  "consultation_type_code": "OPHTHAL_FULL",
  "doctor_id": "doctor-uuid",
  "patient_id": "patient-uuid",
  "created_at": "2025-12-02T10:30:00Z",
  "found": true,
  "message": null
}
```

---

## TypeScript Types

```typescript
// ============================================
// Request Types
// ============================================

interface UploadedJsonData {
  data: Record<string, unknown>;
  source_name?: string;  // Display name (e.g., "External Lab Report")
  source_type?: string;  // e.g., "OPHTHAL_OCR", "EXTERNAL", "LAB_REPORT"
  consultation_type_code?: string;  // Optional: for field mapping
}

interface MergePreviewRequest {
  source_extraction_ids?: string[];       // Use this OR source_submission_ids
  source_submission_ids?: string[];       // Alternative: submission IDs from recording flow
  target_consultation_type_code: string;  // Target consultation type code
  doctor_id: string;                      // Doctor UUID performing the merge
  uploaded_json?: UploadedJsonData;
}

interface MergeExecuteRequest {
  source_extraction_ids?: string[];       // Use this OR source_submission_ids
  source_submission_ids?: string[];       // Alternative: submission IDs from recording flow
  target_consultation_type_code: string;  // Target consultation type code
  doctor_id: string;                      // Doctor UUID performing the merge
  merge_notes?: string;                   // Optional merge notes
  uploaded_json?: UploadedJsonData;
}

// ============================================
// Response Types
// ============================================

interface MergeMetadata {
  source_count: number;                    // Number of source extractions merged
  target_type_code: string;                // Target consultation type code
  merge_timestamp: string;                 // ISO timestamp of merge operation
  doctor_confirmed: boolean;               // true for execute, false for preview
  merge_notes: string | null;              // Optional merge notes
  conflict_count: number;                  // Number of conflicting fields detected
  conflicts_resolved: string[];            // List of field names with resolved conflicts
  cross_type_scenario: string;             // Merge scenario (SAME_TYPE, OP_to_DISCHARGE, etc.)
  consultation_types_merged: string[];     // List of consultation type codes merged
}

interface MergePreviewResponse {
  success: boolean;
  extraction_id: null;                     // Always null for preview
  submission_id: null;                     // Always null for preview
  merged_data: Record<string, unknown>;
  merge_metadata: MergeMetadata;
  preview: true;                           // Always true for preview
}

interface MergeExecuteResponse {
  success: boolean;
  extraction_id: string;                   // UUID of the new merged extraction
  submission_id: string;                   // Submission UUID for tracking/lookup
  merged_data: Record<string, unknown>;
  merge_metadata: MergeMetadata;
  preview: false;                          // Always false for execute
}

interface ExtractionSummary {
  extraction_id: string;
  consultation_type: string;
  created_at: string;
  doctor_name?: string;
  patient_name?: string;
  summary?: string;
}

interface ExtractionDetail extends ExtractionSummary {
  extraction_data: Record<string, unknown>;
}

interface PatientExtractionsResponse {
  extractions: ExtractionSummary[];
  total_count: number;
  has_more: boolean;
}

// ============================================
// Lookup Response Types
// ============================================

interface ExtractionLookupResponse {
  extraction_id: string | null;
  submission_id: string | null;
  session_id: string | null;
  consultation_type_code: string | null;
  doctor_id: string | null;
  patient_id: string | null;
  created_at: string | null;
  found: boolean;
  message: string | null;
}
```

---

## Usage Flow

### Standard Merge Flow (Using extraction_ids)

```
1. User selects extractions to merge from timeline
           ↓
2. Call POST /api/v1/extractions/merge/preview
   (Validation happens automatically)
           ↓
3. Display preview to user for confirmation
           ↓
4. User confirms → Call POST /api/v1/extractions/merge
           ↓
5. New merged extraction created in database
```

### Merge Flow from Recording (Using submission_ids)

```
1. Recording completes → receive submission_id(s)
           ↓
2. Call POST /api/v1/extractions/merge/preview
   with source_submission_ids (auto-resolved to extraction_ids)
           ↓
3. Display preview to user for confirmation
           ↓
4. User confirms → Call POST /api/v1/extractions/merge
           ↓
5. New merged extraction created in database
```

### JSON Upload Flow

```
1. User uploads external JSON file (e.g., OCR export)
           ↓
2. (Optional) Detect source type (OPHTHAL_OCR, etc.)
           ↓
3. Select 1+ existing extractions from database
   OR use submission_ids from recent recordings
           ↓
4. Call POST /api/v1/extractions/merge/preview
   with uploaded_json included (validation + transformation auto-applied)
           ↓
5. Preview → Confirm → Execute
```

---

## React Native Integration Examples

### API Client Setup

```typescript
// services/mergeApi.ts

const API_BASE_URL = 'https://your-backend.com';

class MergeApiClient {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        // Add auth headers if needed
        // 'Authorization': `Bearer ${token}`,
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'API request failed');
    }

    return response.json();
  }

  // ============================================
  // Merge Operations
  // ============================================

  async previewMerge(
    request: MergePreviewRequest
  ): Promise<MergePreviewResponse> {
    return this.request('/api/v1/extractions/merge/preview', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async executeMerge(
    request: MergeExecuteRequest
  ): Promise<MergeExecuteResponse> {
    return this.request('/api/v1/extractions/merge', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  // ============================================
  // Extraction Lookup
  // ============================================

  async getExtraction(extractionId: string): Promise<ExtractionDetail> {
    return this.request(`/api/v1/extractions/${extractionId}`);
  }

  async getPatientTimeline(
    patientId: string,
    consultationTypeCode?: string
  ): Promise<PatientExtractionsResponse> {
    const params = new URLSearchParams();
    if (consultationTypeCode) params.append('consultation_type_code', consultationTypeCode);

    return this.request(
      `/api/v1/extractions/patient/${patientId}/timeline?${params}`
    );
  }

  async getMergeLineage(extractionId: string): Promise<MergeLineageResponse> {
    return this.request(`/api/v1/extractions/${extractionId}/merge-info`);
  }

  // ============================================
  // Lookup Methods (submission_id → extraction_id)
  // ============================================

  async getExtractionBySubmissionId(
    submissionId: string
  ): Promise<ExtractionLookupResponse> {
    return this.request(`/api/v1/extractions/by-submission/${submissionId}`);
  }

  async getExtractionBySessionId(
    sessionId: string
  ): Promise<ExtractionLookupResponse> {
    return this.request(`/api/v1/extractions/by-session/${sessionId}`);
  }

  /**
   * Polls for extraction_id until available (useful after recording completes)
   * @param submissionId - The submission UUID from recording
   * @param maxAttempts - Maximum polling attempts (default: 30)
   * @param intervalMs - Polling interval in milliseconds (default: 2000)
   */
  async waitForExtraction(
    submissionId: string,
    maxAttempts = 30,
    intervalMs = 2000
  ): Promise<ExtractionLookupResponse> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const result = await this.getExtractionBySubmissionId(submissionId);

      if (result.found && result.extraction_id) {
        return result;
      }

      // If not found and no processing message, it's a permanent failure
      if (!result.message?.includes('Processing in progress')) {
        throw new Error(result.message || 'Extraction not found');
      }

      // Wait before next attempt
      await new Promise(resolve => setTimeout(resolve, intervalMs));
    }

    throw new Error(`Extraction not ready after ${maxAttempts} attempts`);
  }
}

export const mergeApi = new MergeApiClient();
```

### React Native Hook

```typescript
// hooks/useMerge.ts

import { useState, useCallback } from 'react';
import { mergeApi } from '../services/mergeApi';

interface UseMergeState {
  isPreviewing: boolean;
  isExecuting: boolean;
  previewResult: MergePreviewResponse | null;
  error: string | null;
}

export function useMerge() {
  const [state, setState] = useState<UseMergeState>({
    isPreviewing: false,
    isExecuting: false,
    previewResult: null,
    error: null,
  });

  /**
   * Preview merge operation
   * @param request - Can use either source_extraction_ids OR source_submission_ids
   */
  const preview = useCallback(
    async (request: MergePreviewRequest) => {
      setState((prev) => ({ ...prev, isPreviewing: true, error: null }));
      try {
        const result = await mergeApi.previewMerge(request);
        setState((prev) => ({
          ...prev,
          isPreviewing: false,
          previewResult: result,
        }));
        return result;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Preview failed';
        setState((prev) => ({
          ...prev,
          isPreviewing: false,
          error: errorMsg,
        }));
        throw err;
      }
    },
    []
  );

  /**
   * Execute merge operation
   * @param request - Can use either source_extraction_ids OR source_submission_ids
   */
  const execute = useCallback(
    async (request: MergeExecuteRequest) => {
      setState((prev) => ({ ...prev, isExecuting: true, error: null }));
      try {
        const result = await mergeApi.executeMerge(request);
        setState((prev) => ({ ...prev, isExecuting: false }));
        return result;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Merge failed';
        setState((prev) => ({
          ...prev,
          isExecuting: false,
          error: errorMsg,
        }));
        throw err;
      }
    },
    []
  );

  const reset = useCallback(() => {
    setState({
      isPreviewing: false,
      isExecuting: false,
      previewResult: null,
      error: null,
    });
  }, []);

  return {
    ...state,
    preview,
    execute,
    reset,
  };
}
```

### Example Screen Component

```tsx
// screens/MergeScreen.tsx

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import DocumentPicker from 'react-native-document-picker';
import { useMerge } from '../hooks/useMerge';
import { mergeApi } from '../services/mergeApi';

interface MergeScreenProps {
  patientId: string;
  doctorId: string;  // Required for merge operations
  onMergeComplete: (extractionId: string) => void;
}

export function MergeScreen({ patientId, doctorId, onMergeComplete }: MergeScreenProps) {
  const [extractions, setExtractions] = useState<ExtractionSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [uploadedJson, setUploadedJson] = useState<UploadedJsonData | null>(null);
  const [targetType, setTargetType] = useState('OPHTHAL_FULL');

  const {
    isPreviewing,
    isExecuting,
    previewResult,
    error,
    preview,
    execute,
    reset,
  } = useMerge();

  // Load patient extractions on mount
  useEffect(() => {
    loadExtractions();
  }, [patientId]);

  const loadExtractions = async () => {
    try {
      const result = await mergeApi.getPatientTimeline(patientId);
      setExtractions(result.extractions);
    } catch (err) {
      Alert.alert('Error', 'Failed to load extractions');
    }
  };

  const toggleSelection = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id]
    );
  };

  const handleUploadJson = async () => {
    try {
      const result = await DocumentPicker.pick({
        type: [DocumentPicker.types.json],
      });

      const fileContent = await fetch(result[0].uri).then((r) => r.text());
      const jsonData = JSON.parse(fileContent);

      // Auto-detect source type based on structure
      let sourceType = undefined;
      if (jsonData.ocrMetadata || jsonData.referenceGuide) {
        sourceType = 'OPHTHAL_OCR';
      }

      setUploadedJson({
        data: jsonData,
        source_type: sourceType,
      });

      Alert.alert('Success', `JSON uploaded${sourceType ? ` (detected: ${sourceType})` : ''}`);
    } catch (err) {
      if (!DocumentPicker.isCancel(err)) {
        Alert.alert('Error', 'Failed to parse JSON file');
      }
    }
  };

  const handlePreview = async () => {
    if (selectedIds.length === 0 && !uploadedJson) {
      Alert.alert('Error', 'Select at least one extraction or upload JSON');
      return;
    }

    try {
      // Validation happens automatically during preview
      await preview({
        source_extraction_ids: selectedIds,
        target_consultation_type_code: targetType,
        doctor_id: doctorId,
        uploaded_json: uploadedJson || undefined,
      });
    } catch (err) {
      Alert.alert('Error', 'Preview request failed');
    }
  };

  const handleExecute = async () => {
    Alert.alert(
      'Confirm Merge',
      'This will create a new merged extraction. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Merge',
          onPress: async () => {
            try {
              const result = await execute({
                source_extraction_ids: selectedIds,
                target_consultation_type_code: targetType,
                doctor_id: doctorId,
                uploaded_json: uploadedJson || undefined,
              });

              Alert.alert('Success', 'Extractions merged successfully');
              onMergeComplete(result.extraction_id);
            } catch (err) {
              Alert.alert('Error', 'Merge failed');
            }
          },
        },
      ]
    );
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Merge Extractions</Text>

      {/* Extraction List */}
      <Text style={styles.sectionTitle}>Select Extractions</Text>
      {extractions.map((ext) => (
        <TouchableOpacity
          key={ext.extraction_id}
          style={[
            styles.extractionItem,
            selectedIds.includes(ext.extraction_id) && styles.selected,
          ]}
          onPress={() => toggleSelection(ext.extraction_id)}
        >
          <Text style={styles.extractionType}>{ext.consultation_type}</Text>
          <Text style={styles.extractionDate}>{ext.created_at}</Text>
          <Text style={styles.extractionSummary}>{ext.summary}</Text>
        </TouchableOpacity>
      ))}

      {/* Upload JSON */}
      <TouchableOpacity style={styles.uploadButton} onPress={handleUploadJson}>
        <Text style={styles.uploadButtonText}>
          {uploadedJson ? '✓ JSON Uploaded' : 'Upload External JSON'}
        </Text>
      </TouchableOpacity>

      {uploadedJson && (
        <View style={styles.uploadInfo}>
          <Text>Source Type: {uploadedJson.source_type || 'Auto-detect'}</Text>
          <TouchableOpacity onPress={() => setUploadedJson(null)}>
            <Text style={styles.removeText}>Remove</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Action Buttons */}
      <View style={styles.actions}>
        <TouchableOpacity
          style={styles.actionButton}
          onPress={handlePreview}
          disabled={isPreviewing}
        >
          {isPreviewing ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.actionButtonText}>Preview</Text>
          )}
        </TouchableOpacity>

        {previewResult?.success && (
          <TouchableOpacity
            style={[styles.actionButton, styles.executeButton]}
            onPress={handleExecute}
            disabled={isExecuting}
          >
            {isExecuting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.actionButtonText}>Execute Merge</Text>
            )}
          </TouchableOpacity>
        )}
      </View>

      {/* Preview Display */}
      {previewResult && (
        <View style={styles.preview}>
          <Text style={styles.sectionTitle}>Preview</Text>
          <Text style={styles.previewMeta}>
            Sources: {previewResult.merge_metadata.source_count}
            {previewResult.merge_metadata.transformation_applied && ' (transformed)'}
          </Text>
          <ScrollView style={styles.previewData}>
            <Text>{JSON.stringify(previewResult.merged_data, null, 2)}</Text>
          </ScrollView>
        </View>
      )}

      {/* Error Display */}
      {error && (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 16 },
  sectionTitle: { fontSize: 18, fontWeight: '600', marginTop: 16, marginBottom: 8 },
  extractionItem: {
    padding: 12,
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    marginBottom: 8,
  },
  selected: { borderColor: '#007AFF', backgroundColor: '#E8F4FD' },
  extractionType: { fontWeight: '600' },
  extractionDate: { color: '#666', fontSize: 12 },
  extractionSummary: { marginTop: 4 },
  uploadButton: {
    padding: 16,
    backgroundColor: '#f0f0f0',
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 16,
  },
  uploadButtonText: { fontWeight: '600' },
  uploadInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 8,
    backgroundColor: '#e8f5e9',
    borderRadius: 4,
    marginTop: 8,
  },
  removeText: { color: '#f44336' },
  actions: { flexDirection: 'row', gap: 8, marginTop: 24 },
  actionButton: {
    flex: 1,
    padding: 16,
    backgroundColor: '#007AFF',
    borderRadius: 8,
    alignItems: 'center',
  },
  executeButton: { backgroundColor: '#4CAF50' },
  actionButtonText: { color: '#fff', fontWeight: '600' },
  preview: { marginTop: 24 },
  previewMeta: { color: '#666', marginBottom: 8 },
  previewData: {
    maxHeight: 300,
    padding: 8,
    backgroundColor: '#f5f5f5',
    borderRadius: 4,
  },
  errorBox: {
    padding: 12,
    backgroundColor: '#ffebee',
    borderRadius: 8,
    marginTop: 16,
  },
  errorText: { color: '#c62828' },
});
```

### Example: Merge After Recording Completes

```tsx
// Example showing how to merge using submission_ids from recording flow

import { mergeApi } from '../services/mergeApi';

async function mergeRecentRecordings(
  submissionIds: string[],
  doctorId: string,
  targetType: string = 'OPHTHAL_FULL'
) {
  try {
    // Option 1: Let the API resolve submission_ids automatically
    const previewResult = await mergeApi.previewMerge({
      source_submission_ids: submissionIds,  // Use submission IDs directly
      target_consultation_type_code: targetType,
      doctor_id: doctorId,
    });

    if (previewResult.success) {
      // Execute the merge
      const result = await mergeApi.executeMerge({
        source_submission_ids: submissionIds,
        target_consultation_type_code: targetType,
        doctor_id: doctorId,
      });

      return result.extraction_id;
    }
  } catch (error) {
    console.error('Merge failed:', error);
    throw error;
  }
}

// Option 2: Manually wait for extraction_ids if needed
async function mergeWithWait(
  submissionIds: string[],
  doctorId: string,
  targetType: string = 'OPHTHAL_FULL'
) {
  // Wait for all recordings to complete processing
  const extractionIds = await Promise.all(
    submissionIds.map(async (submissionId) => {
      const lookup = await mergeApi.waitForExtraction(submissionId);
      return lookup.extraction_id!;
    })
  );

  // Now merge using extraction_ids
  const result = await mergeApi.executeMerge({
    source_extraction_ids: extractionIds,
    target_consultation_type_code: targetType,
    doctor_id: doctorId,
  });

  return result.merged_extraction_id;
}
```

---

## Schema Transformation

### OPHTHAL_OCR → OPHTHAL_FULL

When uploading external OCR data (e.g., from reference guides), the system automatically transforms it to the OPHTHAL_FULL schema format.

**Supported transformations:**
- `OPHTHAL_OCR` → `OPHTHAL_FULL` (ophthalmology family)

**Transformation features:**
- **Sparse mode**: Only populated fields are included (empty values omitted)
- **Category-based merge**: Transformed data merges within its category family
- **Backward compatibility**: Original data structure preserved in `additionalData`

**Detection criteria for OPHTHAL_OCR:**
```typescript
// Auto-detected if JSON contains:
- ocrMetadata
- referenceGuide
- visualAcuity with OD/OS/OU fields
- iop (intraocular pressure) data
```

---

## Error Handling

### Common Error Codes

| Error | Description | Solution |
|-------|-------------|----------|
| `At least 2 extractions required` | Need minimum 2 sources for merge | Add more extractions or upload JSON |
| `Incompatible consultation types` | Selected extractions have conflicting types | Select extractions of compatible types |
| `Schema transformation not available` | Uploaded JSON type cannot be transformed | Use a supported source type |
| `Extraction not found` | Invalid extraction ID | Verify extraction exists |

### Error Response Format
```json
{
  "detail": "Error message here"
}
```

---

## Best Practices

1. **Always validate before preview** - Ensures sources are compatible
2. **Use preview before execute** - Allows user to review merged data
3. **Handle transformation warnings** - Some data may be lost during transformation
4. **Implement retry logic** - Network requests may fail temporarily
5. **Cache patient extractions** - Reduce API calls when user is selecting sources
6. **Show loading states** - All operations can take 1-5 seconds

---

## Changelog

- **v3.4.0** (2025-12-03): Fixed merge response structure and documentation
  - Fixed `MergeMetadata` response to include all required fields (`doctor_confirmed`, `conflict_count`, `conflicts_resolved`, `cross_type_scenario`, `consultation_types_merged`)
  - Execute merge now returns `submission_id` for tracking merged extractions
  - Fixed TypeScript types in documentation to match actual API response
  - Renamed response field from `merged_extraction_id` to `extraction_id` for consistency
- **v3.3.0** (2025-12-02): Added submission_id support in merge API
  - New `source_submission_ids` parameter in merge/preview endpoints (auto-resolved to extraction_ids)
  - New lookup endpoints: `/api/v1/extractions/by-submission/{id}` and `/api/v1/extractions/by-session/{id}`
  - Added `waitForExtraction()` polling helper in API client
  - Removed non-existent `/validate` endpoint from docs (validation happens automatically in preview)
  - Updated field names: `target_consultation_type` → `target_consultation_type_code`
- **v3.2.0** (2025-12-02): Added schema transformation, sparse mode, category-based merge
- **v3.1.0**: Added uploaded JSON support
- **v3.0.0**: Initial merge API release

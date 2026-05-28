# Realtime Extraction Subscription Guide

This guide explains how EHR clients can subscribe to extraction results via Supabase Realtime WebSocket instead of polling the status API.

## Overview

When a hospital has `enable_realtime_subscription=true`, extraction results are automatically published to the `realtime_extraction_responses` table. EHR clients can subscribe to this table using Supabase Realtime to receive instant notifications when extractions complete.

**Benefits:**
- No polling required - instant push notification via WebSocket
- Lower latency than polling the status API
- Supports multiple parallel extractions with independent subscriptions

---

## Prerequisites

1. Hospital must have `enable_realtime_subscription` enabled (contact admin)
2. Supabase anon key (provided by admin)
3. `@supabase/supabase-js` package installed

```bash
npm install @supabase/supabase-js
```

---

## Implementation

### 1. Supabase Client Setup

```typescript
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = 'https://sicvgpofrpzchnjuaqxa.supabase.co';
const supabaseAnonKey = 'YOUR_ANON_KEY';  // Provided by admin

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: false,  // EHR clients don't need Supabase auth
  },
  realtime: {
    params: {
      eventsPerSecond: 10,
    },
    timeout: 30000,
  },
});

export function isRealtimeAvailable(): boolean {
  return supabase !== null;
}
```

---

### 2. State Management (React Example)

```typescript
import { useRef, useState, useEffect } from 'react';
import type { RealtimeChannel } from '@supabase/supabase-js';

// Track active subscriptions (keyed by submissionId)
const realtimeChannelsRef = useRef<Map<string, RealtimeChannel>>(new Map());

// Store received result
const [extractionResult, setExtractionResult] = useState<{
  submissionId: string;
  response: Record<string, unknown>;
  receivedAt: Date;
} | null>(null);
```

---

### 3. Subscribe to Extraction Results

Call this function immediately after receiving `submission_id` from the chunk upload API:

```typescript
const startExtractionSubscription = (submissionId: string) => {
  if (!supabase) {
    console.warn('[Realtime] Supabase client not configured');
    return;
  }

  // Prevent duplicate subscriptions
  if (realtimeChannelsRef.current.has(submissionId)) {
    console.log(`[Realtime] Already subscribed to: ${submissionId}`);
    return;
  }

  console.log(`[Realtime] Starting subscription for: ${submissionId}`);

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
        console.log('[Realtime] Received extraction result:', payload);
        const row = payload.new as Record<string, unknown>;

        // Handle the result
        setExtractionResult({
          submissionId,
          response: row,
          receivedAt: new Date()
        });

        // Cleanup subscription after receiving (one-time event)
        setTimeout(() => {
          channel.unsubscribe();
          realtimeChannelsRef.current.delete(submissionId);
          console.log(`[Realtime] Cleaned up subscription for: ${submissionId}`);
        }, 1000);
      }
    )
    .subscribe(async (status: string) => {
      console.log(`[Realtime] Subscription status: ${status}`);

      if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
        console.warn(`[Realtime] Subscription failed: ${status}`);
        realtimeChannelsRef.current.delete(submissionId);
        return;
      }

      if (status === 'SUBSCRIBED') {
        // Handle race condition: check if result already exists
        // (extraction may complete before subscription is ready)
        try {
          const { data, error } = await supabase
            .from('realtime_extraction_responses')
            .select('*')
            .eq('submission_id', submissionId)
            .maybeSingle();

          if (error) {
            console.error(`[Realtime] Query error: ${error.message}`);
          } else if (data) {
            console.log('[Realtime] Found existing result:', data);
            setExtractionResult({
              submissionId,
              response: data as Record<string, unknown>,
              receivedAt: new Date()
            });
            // Cleanup since we already have the result
            setTimeout(() => {
              channel.unsubscribe();
              realtimeChannelsRef.current.delete(submissionId);
            }, 1000);
          }
        } catch (err) {
          console.error('[Realtime] Exception:', err);
        }
      }
    });

  // Store channel reference for cleanup
  realtimeChannelsRef.current.set(submissionId, channel);
};
```

---

### 4. Cleanup on Component Unmount

```typescript
const cleanupAllSubscriptions = () => {
  realtimeChannelsRef.current.forEach((channel, submissionId) => {
    console.log(`[Realtime] Cleaning up: ${submissionId}`);
    channel.unsubscribe();
  });
  realtimeChannelsRef.current.clear();
};

// React useEffect cleanup
useEffect(() => {
  return () => {
    cleanupAllSubscriptions();
  };
}, []);
```

---

## Usage Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. POST /api/v1/option1/recording/start                        │
│     → Returns: correlation_id                                   │
├─────────────────────────────────────────────────────────────────┤
│  2. POST /api/v1/option1/recording/chunk (upload audio chunks)  │
│     → Last chunk returns: submission_id                         │
├─────────────────────────────────────────────────────────────────┤
│  3. startExtractionSubscription(submissionId)                   │
│     → WebSocket connection established                          │
├─────────────────────────────────────────────────────────────────┤
│  4. [Backend processes audio, transcribes, extracts]            │
│     → Inserts result into realtime_extraction_responses         │
├─────────────────────────────────────────────────────────────────┤
│  5. WebSocket receives INSERT event                             │
│     → payload.new contains full extraction result               │
├─────────────────────────────────────────────────────────────────┤
│  6. Subscription auto-cleans up after receiving result          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Response Payload Structure

When the extraction completes, you receive a row with this structure:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "submission_id": "a1a916a8-44fb-417a-ad86-db893f7266db",
  "hospital_id": "4fc2b7d4-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "hospital_code": "AOSTA001",
  "doctor_id": "57d63d7d-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "extraction_id": "eef04d06-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "response": {
    "status": "COMPLETED",
    "progress": 100,
    "message": "Processing completed successfully",
    "extraction_id": "eef04d06-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "insights": {
      "chief_complaints": [...],
      "history_of_present_illness": "...",
      "diagnosis": [...],
      "medications": [...],
      "investigations": [...],
      ...
    }
  },
  "created_at": "2026-01-22T17:59:40.715567+00:00"
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `submission_id` | Unique ID for this extraction (from chunk upload) |
| `hospital_code` | Your hospital identifier |
| `extraction_id` | UUID to fetch full extraction details if needed |
| `response.status` | `COMPLETED` or `FAILED` |
| `response.insights` | Extracted medical data (same as status API) |
| `created_at` | Timestamp when extraction completed |

---

## Multiple Parallel Extractions

The implementation supports multiple concurrent extractions. Each `submission_id` gets its own independent subscription:

```typescript
// Start 3 parallel recordings/extractions
startExtractionSubscription('submission-1');  // Channel 1
startExtractionSubscription('submission-2');  // Channel 2
startExtractionSubscription('submission-3');  // Channel 3

// Map stores: { 'submission-1' → channel1, 'submission-2' → channel2, ... }

// When submission-2 completes:
// - Only channel2 receives the event
// - Only channel2 is cleaned up
// - channel1 and channel3 continue listening
```

---

## Error Handling

### Subscription Errors

```typescript
.subscribe((status: string) => {
  if (status === 'CHANNEL_ERROR') {
    // WebSocket connection failed - retry or fall back to polling
    console.error('Channel error - falling back to polling');
    startPolling(submissionId);
  }
  if (status === 'TIMED_OUT') {
    // Connection timed out - retry
    console.warn('Subscription timed out - retrying');
    setTimeout(() => startExtractionSubscription(submissionId), 2000);
  }
});
```

### Fallback to Polling

If Realtime is unavailable, fall back to the status API:

```typescript
const checkStatus = async (submissionId: string) => {
  const response = await fetch(
    `${API_URL}/api/v1/ehr/status/${submissionId}`,
    { headers: { 'X-API-Key': apiKey } }
  );
  const data = await response.json();

  if (data.status === 'COMPLETED' || data.status === 'FAILED') {
    return data;
  }

  // Poll again after 3 seconds
  await new Promise(r => setTimeout(r, 3000));
  return checkStatus(submissionId);
};
```

---

## Vanilla JavaScript Example

For non-React implementations:

```javascript
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  'https://sicvgpofrpzchnjuaqxa.supabase.co',
  'YOUR_ANON_KEY'
);

// Store active channels
const channels = new Map();

function subscribeToExtraction(submissionId, onResult) {
  if (channels.has(submissionId)) return;

  const channel = supabase
    .channel(`extraction:${submissionId}`)
    .on('postgres_changes', {
      event: 'INSERT',
      schema: 'public',
      table: 'realtime_extraction_responses',
      filter: `submission_id=eq.${submissionId}`
    }, (payload) => {
      onResult(payload.new);

      // Cleanup
      channel.unsubscribe();
      channels.delete(submissionId);
    })
    .subscribe(async (status) => {
      if (status === 'SUBSCRIBED') {
        // Check for existing result (race condition handling)
        const { data } = await supabase
          .from('realtime_extraction_responses')
          .select('*')
          .eq('submission_id', submissionId)
          .maybeSingle();

        if (data) {
          onResult(data);
          channel.unsubscribe();
          channels.delete(submissionId);
        }
      }
    });

  channels.set(submissionId, channel);
}

// Usage
subscribeToExtraction('abc-123-uuid', (result) => {
  console.log('Extraction complete!', result);
  console.log('Insights:', result.response.insights);
});
```

---

## Security Notes

- **Anon Key**: Use the Supabase anon key (not service role key) for client-side subscriptions
- **Row Level Security**: The table has RLS enabled; you can only read rows (not insert/update/delete)
- **Submission ID**: Acts as a security filter - only receive events for your specific submission
- **24-Hour Cleanup**: Records are automatically deleted after 24 hours

---

## Support

For issues or questions:
- Check browser console for `[Realtime]` logs
- Verify hospital has `enable_realtime_subscription` enabled
- Ensure correct Supabase URL and anon key
- Contact admin if subscription consistently fails

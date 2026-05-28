# Webhook Integration Guide

## Overview

The webhook integration allows the backend to automatically send extracted medical insights to an external endpoint after processing. This enables real-time integration with EHR systems, data warehouses, or other third-party services.

## Features

✅ **Non-blocking execution** - User gets insights immediately, webhook sent in parallel
✅ **Automatic retry logic** - 3 attempts with exponential backoff (1s, 2s, 4s delays)
✅ **Comprehensive error logging** - Webhook failures logged but don't block user experience
✅ **Smart deduplication** - Prevents duplicate webhooks in progressive extraction scenarios
✅ **Secure backend-only** - Webhook URL never exposed to browser
✅ **Configurable** - Easy setup via environment variables

## Configuration

### Environment Variables

Add these to your `backend/.env` file:

```bash
# Webhook Configuration
WEBHOOK_URL=https://your-webhook-endpoint.com/api/insights
WEBHOOK_ENABLED=true
WEBHOOK_TIMEOUT=10
```

**Variables:**
- `WEBHOOK_URL` (required) - Your webhook endpoint URL
- `WEBHOOK_ENABLED` (optional) - Enable/disable webhook functionality (default: `true`)
- `WEBHOOK_TIMEOUT` (optional) - Request timeout in seconds (default: `10`)

### Example Configuration

```bash
# Production webhook
WEBHOOK_URL=https://api.yourehrsystem.com/webhooks/insights
WEBHOOK_ENABLED=true
WEBHOOK_TIMEOUT=15

# Staging/testing webhook
WEBHOOK_URL=https://webhook.site/your-unique-id
WEBHOOK_ENABLED=true
WEBHOOK_TIMEOUT=10

# Disable webhook (for local development)
WEBHOOK_ENABLED=false
```

## Webhook Payload Structure

### Complete Payload

```json
{
  "insights": {
    "diagnosis": {
      "data": "Primary diagnosis information"
    },
    "chief_complaints": {
      "data": "Patient complaints"
    },
    "prescription": {
      "data": "Prescribed medications"
    }
    // ... other extracted segments
  },
  "session_info": {
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "submission_id": "660e8400-e29b-41d4-a716-446655440000",
    "doctor_id": "770e8400-e29b-41d4-a716-446655440000",
    "patient_id": "PAT12345",
    "template_name": "Psychiatry Standard - Full",
    "extraction_mode": "full",
    "processing_mode": "default",
    "consultation_type_code": "OP"
  },
  "metadata": {
    "timestamp": "2025-01-07T10:30:00.000Z",
    "source": "recording",
    "version": "3.1.0"
  }
}
```

### Payload Fields

#### `insights` (object)
- Extracted medical data segments
- Structure varies based on consultation type and selected segments
- Contains the actual clinical information extracted from the transcript

#### `session_info` (object)
- `correlation_id` (string, nullable) - Recording session correlation ID (only for recording source)
- `submission_id` (string, nullable) - Processing job submission ID (only for recording source)
- `doctor_id` (string, nullable) - Doctor UUID
- `patient_id` (string, nullable) - Patient identifier
- `template_name` (string, nullable) - Activated template name used for extraction
- `extraction_mode` (string, nullable) - Extraction mode (core/additional/full)
- `processing_mode` (string, nullable) - Processing mode code (ultra/fast/default/thorough)
- `consultation_type_code` (string, nullable) - Consultation type (OP/DISCHARGE/etc)

#### `metadata` (object)
- `timestamp` (string) - ISO 8601 timestamp of webhook generation
- `source` (string) - Source of extraction:
  - `"recording"` - From recording pipeline (live recording or file upload with full mode)
  - `"direct_extraction"` - From direct extraction API (progressive loading)
- `version` (string) - API version

## How It Works

### Architecture

The webhook integration follows **Option 2** strategy to prevent duplicate webhook calls:

```
┌─────────────────────────────────────────────────────────┐
│                   VHR Screen (Frontend)                  │
└─────────────────────────────────────────────────────────┘
                            │
                            │ User records/uploads audio
                            ▼
           ┌────────────────────────────────┐
           │   Extraction Mode Decision     │
           └────────────────────────────────┘
                    │           │
        ┌───────────┘           └───────────┐
        │                                   │
        ▼                                   ▼
  ┌──────────┐                      ┌─────────────┐
  │   FULL   │                      │ CORE/ADD'L  │
  └──────────┘                      └─────────────┘
        │                                   │
        │ Recording Pipeline                │ Progressive Extraction
        ▼                                   ▼
  ┌──────────────────┐              ┌──────────────────┐
  │ recording_       │              │ Direct API       │
  │ processor.py     │              │ (summary.py)     │
  │                  │              │                  │
  │ 🔔 WEBHOOK #1    │              │ 🔔 WEBHOOK #1    │
  │ (full mode only) │              │ (always sent)    │
  └──────────────────┘              └──────────────────┘
                                             │
                              (For additional mode)
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │ Direct API       │
                                    │ (summary.py)     │
                                    │                  │
                                    │ 🔔 WEBHOOK #2    │
                                    │ (always sent)    │
                                    └──────────────────┘
```

### Webhook Sending Rules

#### 1. Recording Pipeline (`recording_processor.py`)
- **Only sends webhook when `extraction_mode == 'full'`**
- Triggered after audio stitching → transcription → full extraction completes
- Contains complete session context (correlation_id, submission_id)
- Source: `"recording"`

**When triggered:**
- User records audio with extraction_mode='full'
- User uploads file with extraction_mode='full'

**Example flow:**
```
User starts recording with extraction_mode='full'
    ↓
Recording completes → Upload chunks → Stitch audio
    ↓
Transcribe audio to text
    ↓
Extract insights (mode='full') ✅ ALL segments extracted
    ↓
🔔 WEBHOOK SENT (source='recording')
    ↓
Return insights to frontend via SSE
```

#### 2. Direct Extraction API (`summary.py`)
- **Always sends webhook for all extraction modes (core/additional/full)**
- Triggered by frontend progressive extraction calls
- Limited session context (no correlation_id/submission_id)
- Source: `"direct_extraction"`

**When triggered:**
- Progressive extraction: CORE segments requested
- Progressive extraction: ADDITIONAL segments requested
- Direct API usage without recording

**Example flow (progressive extraction):**
```
User starts recording with extraction_mode='core'
    ↓
Recording completes → Transcribe → Extract CORE ⚠️ Partial extraction
    ↓
Return transcript + CORE insights to frontend via SSE
    ↓
Frontend: handleProgressiveExtraction() detects core mode
    ↓
Frontend: Calls direct API with mode='additional'
    ↓
Extract ADDITIONAL segments
    ↓
🔔 WEBHOOK SENT (source='direct_extraction')
    ↓
Return ADDITIONAL insights to frontend
```

### Deduplication Logic

The system **prevents duplicate webhooks** in the following scenario:

```
❌ WITHOUT DEDUPLICATION:
extraction_mode='full' → Recording pipeline sends webhook
                      → Frontend doesn't call direct API
                      → ✅ 1 webhook (correct)

extraction_mode='core' → Recording pipeline SKIPS webhook (mode != 'full')
                       → Frontend calls direct API (mode='additional')
                       → Direct API sends webhook
                       → ✅ 1 webhook (correct)

✅ WITH OPTION 2:
extraction_mode='full' → Recording pipeline sends webhook (mode == 'full')
                       → Frontend doesn't call direct API
                       → ✅ 1 webhook sent

extraction_mode='core' → Recording pipeline SKIPS webhook (mode != 'full')
                       → Frontend calls direct API (mode='core') → webhook sent
                       → Frontend calls direct API (mode='additional') → webhook sent
                       → ✅ 2 webhooks sent (CORE + ADDITIONAL segments separately)
```

## Retry Logic

The webhook service implements automatic retry with exponential backoff:

```python
Attempt 1: Send webhook
    ↓ (fails)
Wait 1 second
    ↓
Attempt 2: Send webhook
    ↓ (fails)
Wait 2 seconds
    ↓
Attempt 3: Send webhook
    ↓ (fails)
Wait 4 seconds
    ↓
All attempts failed → Log error → Continue execution
```

**Key points:**
- Maximum 3 retry attempts per webhook
- Exponential backoff: 1s → 2s → 4s
- Total max time: ~10s (3 timeouts + 7s waiting)
- Failures are logged but don't block user experience

## Error Handling

### Webhook Disabled
```python
WEBHOOK_ENABLED=false
# OR
WEBHOOK_URL not set
```
**Result:** Webhook silently skipped, logged at DEBUG level

### Webhook Timeout
```python
WEBHOOK_TIMEOUT=10  # seconds
```
**Result:** Request times out after 10s, automatic retry triggered

### HTTP Errors (4xx/5xx)
**Result:** Error logged with status code, automatic retry triggered

### All Retries Failed
**Result:**
- Error logged with full details (attempt count, error messages)
- User receives insights normally (webhook failure doesn't affect UX)
- System continues processing

## Testing Your Webhook

### 1. Using webhook.site (Free Testing)

1. Go to https://webhook.site
2. Copy your unique URL (e.g., `https://webhook.site/your-unique-id`)
3. Add to `.env`:
   ```bash
   WEBHOOK_URL=https://webhook.site/your-unique-id
   WEBHOOK_ENABLED=true
   ```
4. Record audio or upload file in VHR screen
5. Check webhook.site dashboard for received payload

### 2. Using RequestBin (Alternative)

1. Go to https://requestbin.com
2. Create a new bin and copy the URL
3. Configure in `.env`
4. Test extraction and view captured requests

### 3. Local Testing with ngrok

```bash
# Terminal 1: Start local webhook server
python webhook_test_server.py

# Terminal 2: Expose with ngrok
ngrok http 5000

# Terminal 3: Configure .env with ngrok URL
WEBHOOK_URL=https://abc123.ngrok.io/webhook
```

### 4. Example Test Server

```python
# webhook_test_server.py
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.json
    print("=" * 80)
    print("WEBHOOK RECEIVED")
    print("=" * 80)
    print(f"Source: {payload['metadata']['source']}")
    print(f"Timestamp: {payload['metadata']['timestamp']}")
    print(f"Extraction Mode: {payload['session_info']['extraction_mode']}")
    print(f"Doctor ID: {payload['session_info']['doctor_id']}")
    print(f"Insights Keys: {list(payload['insights'].keys())}")
    print("=" * 80)
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(port=5000, debug=True)
```

## Integration Examples

### Example 1: EHR System Integration

```python
# Your EHR system webhook endpoint
@app.route('/api/insights', methods=['POST'])
def receive_insights():
    payload = request.json

    # Extract key information
    insights = payload['insights']
    session_info = payload['session_info']

    # Create EHR record
    ehr_record = {
        'doctor_id': session_info['doctor_id'],
        'patient_id': session_info['patient_id'],
        'consultation_date': payload['metadata']['timestamp'],
        'diagnosis': insights.get('diagnosis', {}).get('data'),
        'prescription': insights.get('prescription', {}).get('data'),
        'notes': insights.get('clinical_assessment', {}).get('data'),
    }

    # Save to your EHR database
    save_to_ehr_system(ehr_record)

    return jsonify({'status': 'success'}), 200
```

### Example 2: Data Warehouse Integration

```python
# Data warehouse webhook endpoint
@app.route('/webhooks/insights', methods=['POST'])
def receive_insights():
    payload = request.json

    # Route to appropriate handler based on source
    if payload['metadata']['source'] == 'recording':
        handle_complete_consultation(payload)
    else:
        handle_progressive_extraction(payload)

    return jsonify({'status': 'success'}), 200

def handle_complete_consultation(payload):
    """Handle full extraction from recording pipeline."""
    # Save complete consultation record
    save_to_data_warehouse(payload)

def handle_progressive_extraction(payload):
    """Handle partial extraction from direct API."""
    mode = payload['session_info']['extraction_mode']

    if mode == 'core':
        # Save core segments, mark as partial
        save_core_segments(payload)
    elif mode == 'additional':
        # Update existing record with additional segments
        update_with_additional_segments(payload)
```

### Example 3: Notification System

```python
# Notification webhook endpoint
@app.route('/webhooks/insights', methods=['POST'])
def receive_insights():
    payload = request.json

    # Send notification to doctor
    doctor_id = payload['session_info']['doctor_id']
    patient_id = payload['session_info']['patient_id']

    send_notification(
        recipient=doctor_id,
        title="Consultation Processed",
        message=f"Patient {patient_id} consultation has been processed and is ready for review.",
        link=f"/consultations/{payload['session_info']['correlation_id']}"
    )

    return jsonify({'status': 'success'}), 200
```

## Security Considerations

### 1. Webhook URL Security
- Store webhook URL in environment variables (never in code)
- Use HTTPS endpoints only in production
- Consider using signed webhooks for verification

### 2. Authentication
Add authentication to your webhook endpoint:

```python
from functools import wraps
from flask import request, jsonify

def verify_webhook_signature(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        signature = request.headers.get('X-Webhook-Signature')
        if not signature or not verify_signature(signature):
            return jsonify({'error': 'Invalid signature'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/webhook', methods=['POST'])
@verify_webhook_signature
def webhook():
    # Process webhook
    pass
```

### 3. Rate Limiting
Implement rate limiting on your webhook endpoint:

```python
from flask_limiter import Limiter

limiter = Limiter(app, key_func=lambda: request.remote_addr)

@app.route('/webhook', methods=['POST'])
@limiter.limit("100 per minute")
def webhook():
    # Process webhook
    pass
```

### 4. HIPAA Compliance
- Ensure webhook endpoint uses HTTPS/TLS 1.2+
- Implement audit logging of all webhook deliveries
- Store webhook URL securely (encrypted at rest)
- Consider end-to-end encryption for sensitive data

## Monitoring & Logging

### Backend Logs

The webhook service logs all activity:

```python
# Success
[INFO] Webhook sent successfully on attempt 1/3 (source=recording, session_id=550e8400...)

# Retry
[ERROR] Webhook attempt 1/3 failed: Connection timeout (source=recording, session_id=550e8400...)
[DEBUG] Waiting 1s before retry 2

# Final failure
[ERROR] Webhook failed after 3 attempts (source=recording, session_id=550e8400...)
```

### Monitoring Checklist

- [ ] Monitor webhook success/failure rates
- [ ] Alert on consecutive webhook failures
- [ ] Track webhook latency (p50, p95, p99)
- [ ] Monitor retry attempt distribution
- [ ] Log all webhook payloads for audit trail

## Troubleshooting

### Webhook Not Being Sent

**Check 1:** Verify `WEBHOOK_ENABLED=true`
```bash
# In backend/.env
WEBHOOK_ENABLED=true
```

**Check 2:** Verify `WEBHOOK_URL` is set
```bash
# In backend/.env
WEBHOOK_URL=https://your-webhook-endpoint.com/api/insights
```

**Check 3:** Check backend logs
```bash
# Look for webhook-related logs
grep WEBHOOK backend/logs/app.log
```

### Webhook Timing Out

**Solution 1:** Increase timeout
```bash
# In backend/.env
WEBHOOK_TIMEOUT=20  # Increase from 10 to 20 seconds
```

**Solution 2:** Optimize webhook endpoint
- Implement async processing
- Return 200 OK immediately, process in background
- Cache database connections

### Receiving Duplicate Webhooks

**Scenario:** Check extraction mode
- `extraction_mode='full'` → Only 1 webhook (from recording pipeline)
- `extraction_mode='core'` → 2 webhooks (core from direct API, additional from direct API)

This is **expected behavior** for progressive extraction.

**Solution (if undesired):**
Deduplicate on your webhook endpoint using `correlation_id` or `submission_id`:

```python
webhook_cache = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.json
    session_id = payload['session_info']['correlation_id']

    # Deduplicate using cache
    if session_id in webhook_cache:
        return jsonify({'status': 'duplicate'}), 200

    webhook_cache[session_id] = True
    # Process webhook...
```

### Webhook Endpoint Returns Error

**Check HTTP status codes:**
- `200-299`: Success (no retry)
- `400-499`: Client error (logged, will retry)
- `500-599`: Server error (logged, will retry)

**Check your endpoint logs** for error details

## Files Modified

- **Created:**
  - `backend/services/webhook_service.py` - Webhook service with retry logic
  - `backend/models/webhook_models.py` - Pydantic models for webhook payloads
  - `WEBHOOK_INTEGRATION.md` - This documentation file

- **Modified:**
  - `backend/services/recording_processor.py` - Added webhook call for full extraction mode
  - `backend/routers/summary.py` - Added webhook call for all direct extraction API calls
  - `backend/.env.example` - Added webhook configuration variables

## Summary

The webhook integration provides a robust, production-ready solution for real-time data integration:

✅ **Smart deduplication** prevents duplicate webhooks in progressive extraction
✅ **Non-blocking execution** ensures fast user experience
✅ **Automatic retries** handle transient network failures
✅ **Comprehensive logging** enables monitoring and debugging
✅ **Easy configuration** via environment variables
✅ **Secure backend-only** implementation

The system is now ready to send extracted medical insights to your external endpoints automatically!

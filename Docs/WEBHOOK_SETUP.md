# Webhook Setup Quick Start

## 1. Add Webhook Configuration

Edit `backend/.env` and add:

```bash
# Webhook Configuration (PLACEHOLDER - Replace with your webhook URL)
WEBHOOK_URL=https://your-webhook-endpoint.com/api/insights
WEBHOOK_ENABLED=true
WEBHOOK_TIMEOUT=10
```

**Important:** Replace `https://your-webhook-endpoint.com/api/insights` with your actual webhook endpoint URL.

## 2. Restart Backend Server

```bash
cd backend
uvicorn main:app --reload --port 8000
```

## 3. Test the Integration

### Option A: Use the Test Server (Recommended for Testing)

```bash
# Terminal 1: Start test webhook server
cd backend
python webhook_test_server.py

# Terminal 2: Configure .env to use test server
# Edit backend/.env:
WEBHOOK_URL=http://localhost:5000/webhook
WEBHOOK_ENABLED=true

# Terminal 3: Restart backend server
cd backend
uvicorn main:app --reload --port 8000

# Terminal 4: Start frontend
npm run dev
```

Then:
1. Open VHR screen in browser (http://localhost:3000)
2. Record audio or upload file
3. Watch Terminal 1 for webhook payloads

### Option B: Use webhook.site (Public Testing)

1. Go to https://webhook.site
2. Copy your unique URL
3. Edit `backend/.env`:
   ```bash
   WEBHOOK_URL=https://webhook.site/your-unique-id
   WEBHOOK_ENABLED=true
   ```
4. Restart backend server
5. Record audio in VHR screen
6. Check webhook.site dashboard for payload

## 4. How Webhooks Are Sent

### Full Extraction Mode
```
User records with extraction_mode='full'
    ↓
Recording Pipeline (recording_processor.py)
    ↓
Audio → Transcript → Extract ALL segments
    ↓
🔔 WEBHOOK SENT (source='recording')
    ↓
Return insights to frontend
```

### Progressive Extraction (Core/Additional)
```
User records with extraction_mode='core'
    ↓
Recording Pipeline (recording_processor.py)
    ↓
Audio → Transcript → Extract CORE segments
    ↓
⚠️ NO WEBHOOK (mode != 'full')
    ↓
Return transcript + CORE insights to frontend
    ↓
Frontend calls Direct API with mode='additional'
    ↓
Direct Extraction API (summary.py)
    ↓
Extract ADDITIONAL segments
    ↓
🔔 WEBHOOK SENT (source='direct_extraction')
    ↓
Return ADDITIONAL insights to frontend
```

## 5. Expected Webhook Payload

```json
{
  "insights": {
    "diagnosis": {"data": "..."},
    "chief_complaints": {"data": "..."},
    "prescription": {"data": "..."}
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

## 6. Webhook Endpoint Requirements

Your webhook endpoint should:

1. **Accept POST requests**
2. **Process JSON payload**
3. **Return 200-299 status code** for success
4. **Respond quickly** (< 10 seconds, configurable via WEBHOOK_TIMEOUT)
5. **Handle retries** (webhook will retry 3 times with exponential backoff)

### Example Webhook Endpoint (Python Flask)

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/insights', methods=['POST'])
def receive_insights():
    payload = request.json

    # Extract data
    insights = payload['insights']
    session_info = payload['session_info']
    metadata = payload['metadata']

    # Process insights (save to database, send notifications, etc.)
    print(f"Received insights from {metadata['source']}")
    print(f"Doctor: {session_info['doctor_id']}")
    print(f"Patient: {session_info['patient_id']}")
    print(f"Segments: {list(insights.keys())}")

    # Return success
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(port=8080)
```

## 7. Troubleshooting

### Webhook Not Sent

**Check:** Is webhook enabled?
```bash
# In backend/.env
WEBHOOK_ENABLED=true
```

**Check:** Is webhook URL configured?
```bash
# In backend/.env
WEBHOOK_URL=https://your-webhook-endpoint.com/api/insights
```

**Check:** Backend logs
```bash
# Look for webhook logs
grep WEBHOOK backend/logs/*.log
```

### Webhook Timing Out

**Solution:** Increase timeout
```bash
# In backend/.env
WEBHOOK_TIMEOUT=20  # Increase from 10 to 20 seconds
```

### Webhook Endpoint Returns Error

**Check:** Your webhook endpoint logs
**Check:** HTTP status code returned (must be 200-299 for success)

## 8. Production Deployment

### Security Checklist

- [ ] Use HTTPS endpoint (not HTTP)
- [ ] Store webhook URL in environment variables (not in code)
- [ ] Implement authentication on webhook endpoint
- [ ] Enable audit logging for all webhook deliveries
- [ ] Set up monitoring and alerting for webhook failures
- [ ] Consider rate limiting on webhook endpoint

### Example Production Configuration

```bash
# Production webhook
WEBHOOK_URL=https://api.yourehrsystem.com/webhooks/insights
WEBHOOK_ENABLED=true
WEBHOOK_TIMEOUT=15

# Optional: Add authentication headers (requires code modification)
# WEBHOOK_AUTH_TOKEN=your-secret-token
```

## 9. Next Steps

1. ✅ Configure webhook URL in `backend/.env`
2. ✅ Restart backend server
3. ✅ Test with webhook test server or webhook.site
4. ✅ Verify webhook payload structure
5. ✅ Implement your webhook endpoint
6. ✅ Deploy to production

## Documentation

- **Complete Guide:** See `WEBHOOK_INTEGRATION.md` for full documentation
- **Architecture:** See `.claude/CLAUDE.md` for system architecture
- **API Docs:** http://localhost:8000/docs (when backend is running)

## Support

For issues or questions:
1. Check `WEBHOOK_INTEGRATION.md` troubleshooting section
2. Review backend logs for webhook errors
3. Test with webhook.site to verify payload structure

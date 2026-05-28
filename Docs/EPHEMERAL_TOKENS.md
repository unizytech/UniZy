# Ephemeral Tokens Implementation

## 🔒 Security Enhancement

The Live tab now uses **ephemeral tokens** instead of exposing the API key in the browser. This provides secure client-side access to Gemini Live API without compromising your API key.

---

## How It Works

### Architecture Flow

```
1. User clicks "Start Recording" in Live tab
   ↓
2. RecordTab.tsx → Backend: POST /api/ephemeral-token
   ↓
3. Backend generates short-lived token using server-side GEMINI_API_KEY
   ↓
4. Backend → Frontend: Returns ephemeral token
   ↓
5. Frontend connects to Gemini Live API using ephemeral token
   ↓
6. Live transcription session begins (secure)
```

### Key Benefits

✅ **API key never exposed** - Only ephemeral tokens visible in browser
✅ **Short-lived tokens** - Automatic expiration (1 min session window, 30 min transmission window)
✅ **v1alpha API** - Uses latest Gemini Live API features
✅ **Backend-controlled** - Server manages all token generation

---

## Implementation Details

### Backend (Python FastAPI)

**File**: `backend/routers/ephemeral_token.py`

```python
from google import genai
from config import settings

# Initialize client with v1alpha API
client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options={'api_version': 'v1alpha'}
)

# Generate ephemeral token
token = client.auth_tokens.create()

# Return token.name to frontend
return {
    "token": token.name,
    "expires_in": 300,
    "new_session_expire_time": token.new_session_expire_time,
    "expire_time": token.expire_time
}
```

**Endpoint**: `POST /api/ephemeral-token`

**Response**:
```json
{
  "token": "auth_tokens/...",
  "expires_in": 300,
  "new_session_expire_time": "2025-11-02T10:05:00Z",
  "expire_time": "2025-11-02T10:35:00Z"
}
```

---

### Frontend (React/TypeScript)

**File**: `app/components/RecordTab.tsx`

```typescript
// Fetch ephemeral token from backend
const tokenResponse = await fetch(API_ENDPOINTS.ephemeralToken, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
});

const tokenData = await tokenResponse.json();
const ephemeralToken = tokenData.token;

// Use token to connect to Gemini Live API
sessionManagerRef.current = await startLiveTranscriptionSession(
    handleTranscriptionUpdate,
    onError,
    onOpen,
    ephemeralToken  // Pass ephemeral token
);
```

---

**File**: `app/services/geminiClient.ts`

```typescript
// Use ephemeral token with v1alpha API
const client = ephemeralToken
    ? new GoogleGenAI({
        apiKey: ephemeralToken,
        httpOptions: { apiVersion: 'v1alpha' }
      })
    : ai;  // Fallback (not recommended for production)

// Connect to Gemini Live API
const sessionPromise = client.live.connect({
    model: 'gemini-2.5-flash-native-audio-preview-09-2025',
    callbacks: { /* ... */ }
});
```

---

## Configuration

### Backend (.env)

```bash
# Server-side API key (REQUIRED)
GEMINI_API_KEY=your_gemini_api_key_here

# Backend URL
NEXT_PUBLIC_BACKEND_API_URL=http://localhost:8000
```

### Frontend (.env.local)

```bash
# Client-side API key (DEPRECATED - not needed for Live tab)
# The Live tab now uses ephemeral tokens for security
# NEXT_PUBLIC_GEMINI_API_KEY=your_gemini_api_key_here

# Backend URL
NEXT_PUBLIC_BACKEND_API_URL=http://localhost:8000
```

---

## Token Expiration

Custom configuration for long recordings:

- **Session Initiation Window** (`newSessionExpireTime`): **12 minutes**
  - Time window to start a new session after token generation
  - Configured for recordings up to 10+ minutes
  - If session not started within 12 minutes, token becomes invalid

- **Message Transmission Window** (`expireTime`): **15 minutes**
  - Once session is started, you can transmit messages for 15 minutes
  - Provides buffer for post-recording processing and insights extraction

**Example Timeline**:
```
T+0s   : Token generated
T+30s  : User starts session (within 12 min window) ✅
T+5m   : Recording... (within 15 min window) ✅
T+10m  : Still recording (within 15 min window) ✅
T+12m  : Recording finished, processing insights ✅
T+16m  : Token expired, session auto-closes ❌
```

**Note**: These times are customized from the default (1 min / 30 min) to better accommodate typical medical recording sessions.

---

## Security Best Practices

### ✅ DO

- Use ephemeral tokens for all client-side Live API access
- Keep `GEMINI_API_KEY` in backend `.env` file only
- Never commit `.env` files to version control
- Monitor token generation rate

### ❌ DON'T

- Expose `GEMINI_API_KEY` in frontend code
- Use `NEXT_PUBLIC_GEMINI_API_KEY` for Live API (deprecated)
- Share ephemeral tokens across users
- Store ephemeral tokens in localStorage

---

## Testing

### 1. Test Backend Endpoint

```bash
# Start backend server
cd backend
uvicorn main:app --reload --port 8000
```

```bash
# Test ephemeral token generation
curl -X POST http://localhost:8000/api/ephemeral-token \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "token": "auth_tokens/abc123...",
  "expires_in": 300,
  "new_session_expire_time": "2025-11-02T10:05:00Z",
  "expire_time": "2025-11-02T10:35:00Z"
}
```

### 2. Test Frontend Integration

```bash
# Start frontend dev server
npm run dev
```

1. Navigate to http://localhost:3000
2. Go to **Live tab**
3. Click "Start Recording"
4. Check browser console:
   - ✅ "Ephemeral token obtained, expires in 300 seconds"
   - ✅ "Connecting to Gemini Live session..."
   - ✅ "Listening... Speak now!"

---

## Troubleshooting

### Error: "Failed to obtain ephemeral token"

**Cause**: Backend couldn't generate token from Gemini API

**Solutions**:
- Check `GEMINI_API_KEY` is set in `backend/.env`
- Verify API key is valid
- Check internet connection
- Check Gemini API quota/billing

### Error: "No API key or ephemeral token available"

**Cause**: Frontend received invalid/empty token

**Solutions**:
- Check backend is running on correct port (8000)
- Check `NEXT_PUBLIC_BACKEND_API_URL` in `.env.local`
- Verify ephemeral token endpoint returns valid token
- Check browser network tab for API errors

### Session expires too quickly

**Cause**: Not starting session within 1-minute window

**Solutions**:
- Request token just before connecting to Live API
- Don't cache tokens for later use
- Implement automatic token refresh if needed

---

## API Documentation

See official Gemini documentation:
- [Ephemeral Tokens Guide](https://ai.google.dev/gemini-api/docs/ephemeral-tokens)
- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live-api)

---

## Future Enhancements

Potential improvements:

- [ ] Automatic token refresh when near expiration
- [ ] Token caching with expiration tracking
- [ ] Custom token TTL configuration
- [ ] Token usage metrics and monitoring
- [ ] Multi-user token management

---

## Files Modified

### Backend
- ✅ `backend/routers/ephemeral_token.py` - New ephemeral token endpoint
- ✅ `backend/main.py` - Added ephemeral token router

### Frontend
- ✅ `app/components/RecordTab.tsx` - Fetch and use ephemeral tokens
- ✅ `app/services/geminiClient.ts` - Support ephemeral tokens with v1alpha
- ✅ `lib/config.ts` - Added ephemeralToken endpoint

### Configuration
- ✅ `.env.example` - Deprecated client-side API key
- ✅ `EPHEMERAL_TOKENS.md` - This documentation

---

## Summary

The Live tab now uses **ephemeral tokens** for secure, client-side access to Gemini Live API:

1. Backend generates short-lived tokens using server-side API key
2. Frontend receives tokens and connects to Gemini Live API
3. API key remains secure on backend, never exposed to browser
4. Tokens auto-expire (1 min session window, 30 min transmission window)

This provides the same real-time transcription experience with **enhanced security**. 🔒

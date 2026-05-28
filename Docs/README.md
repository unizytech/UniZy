# Gemini Audio Transcriber - Medical Consultation Assistant

AI-powered medical consultation transcription & insights extraction for psychiatry using Google Gemini AI.

## 🎯 Features

### 3 Core Tabs:

1. **🏠 Home Tab** - Live recording + file upload (dual mode)
   - **Live recording** with chunked audio streaming (10-second chunks)
   - Real-time progress via Server-Sent Events (SSE)
   - **File upload** for batch processing
   - Multiple transcription models (Gemini 2.5 Flash/Pro)
   - 6 prompt templates: SMALL, BASE, BASE_PRO, CONCISE, CONCISE_LITE, DETAILED

2. **🎙️ Live Tab** - Real-time transcription with secure ephemeral tokens
   - **🔒 Secure** - Uses ephemeral tokens (no API key exposed in browser)
   - Live audio transcription with instant translation
   - Backend-generated short-lived tokens (12 min session, 15 min transmission)
   - Medical insights extraction after recording stops
   - Session controls: start, pause, resume, stop

3. **📊 Compare Tab** - Transcript accuracy testing
   - Compare generated transcripts against ground truth
   - Calculate Word Error Rate (WER) and Levenshtein distance
   - Benchmark Gemini 2.5 Flash transcription quality
   - Detailed accuracy metrics

## 🏗️ Architecture

**Hybrid Full-Stack Application**
- **Frontend**: Next.js 16.0 with React 19.2 and Tailwind CSS v4
- **Backend**: Python FastAPI 0.115.5 (async/await for optimal performance)
- **AI**: Google Gemini API (@google/genai 1.26.0)
- **Real-time**: WebSocket for live transcription and conversation
- **Mobile-Ready**: REST API for iOS, Android, React Native (see [MOBILE_API.md](MOBILE_API.md))

### Hybrid Security Model:
- **Real-time features** (Live tab): **🔒 Ephemeral tokens** (no API key exposed in browser)
  - Backend generates short-lived tokens via `/api/ephemeral-token`
  - Tokens expire after 12 minutes (session) / 15 minutes (transmission)
- **Batch features** (Home, Compare tabs): Python FastAPI backend (API key secure)

### Two-Server Architecture:
- **Frontend** (Next.js): http://localhost:3000 - UI and real-time features
- **Backend** (Python FastAPI): http://localhost:8000 - Medical transcription & STT testing APIs

## 🚀 Run Locally

**Prerequisites:** Node.js 18+ and Python 3.11+

### 1. Setup Python Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Setup Next.js Frontend

```bash
# From project root
npm install

# Create .env.local file
cp .env.example .env.local
```

Edit `.env.local`:
```bash
# Python FastAPI backend URL
NEXT_PUBLIC_BACKEND_API_URL=http://localhost:8000

# Client-side API key (DEPRECATED - now using ephemeral tokens)
# The Live tab now uses ephemeral tokens from backend (secure)
# Leave this blank unless you have a specific fallback use case
# NEXT_PUBLIC_GEMINI_API_KEY=your_gemini_api_key
```

### 3. Start Both Servers

**Terminal 1 (Backend):**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Terminal 2 (Frontend):**
```bash
npm run dev
```

### 4. Access the Application
- **Frontend**: http://localhost:3000
- **Backend API Docs**: http://localhost:8000/docs (Swagger UI)

## 📱 Mobile App Integration

See [MOBILE_API.md](MOBILE_API.md) for complete REST API documentation for mobile apps:
- React Native examples
- iOS Swift examples
- Android Kotlin examples

**Backend API Endpoints:**
- `POST /api/insights` - Transcript → Multi-prompt extraction
- `POST /api/ephemeral-token` - Generate secure tokens for Live API
- `POST /api/v1/option1/recording/*` - Live recording (start, chunk, stream, cancel)
- `POST /api/compare-transcribe` - Transcript accuracy testing

## 🏥 Medical Insights Schema

Psychiatry-focused extraction with 26 fields including:
- Chief Complaint, Diagnosis (DSM-5/ICD-10), Treatment Plan
- Prescription Data, Mental Status Examination
- History, Associated Symptoms, Subtext Analysis
- Patient Info (name, phone, email)
- Treatment Protocol with behavioral nudging

## 🛠️ Tech Stack

- **Framework**: Next.js 16.0 (App Router, Turbopack)
- **Language**: TypeScript 5.8
- **UI**: Tailwind CSS v4, React 19.2
- **AI**: Google Gemini API (gemini-2.5-pro, gemini-2.5-flash)
- **Audio**: WebSocket real-time, Base64 file upload

## 📂 Project Structure

```
app/                      # Next.js Frontend
├── components/           # React components (3 active tabs)
│   ├── Option1Tab.tsx    # Home tab: Live recording + file upload
│   ├── RecordTab.tsx     # Live tab: Real-time transcription
│   └── CompareTranscriptTab.tsx  # Compare tab: Accuracy testing
├── services/
│   └── geminiClient.ts   # Client-side WebSocket service
├── utils/
│   └── audioUtils.ts     # Audio encoding utilities
├── page.tsx              # Main app with tab switcher
├── layout.tsx            # Root layout
└── globals.css           # Tailwind v4 styles

lib/                      # Shared utilities
├── config.ts             # API configuration (backend URL)
└── types.ts              # TypeScript types

backend/                  # Python FastAPI Backend
├── main.py               # FastAPI app entry point
├── requirements.txt      # Python dependencies
├── routers/              # API route handlers
│   ├── insights.py       # POST /api/insights
│   ├── recording_session.py  # Live recording APIs
│   └── compare_transcripts.py  # POST /api/compare-transcribe
├── services/             # Business logic
│   ├── gemini_service.py # Gemini AI client (async)
│   ├── prompts.py        # Extraction prompt templates
│   ├── recording_processor.py  # Recording processor with SSE
│   ├── audio_stitcher.py  # Audio chunk stitching
│   ├── supabase_service.py  # Database operations
│   └── insight_extractor.py  # Medical insights extraction
├── models/               # Pydantic models
│   ├── request_models.py # Request validation
│   ├── response_models.py # Response models
│   └── enums.py          # Workflow and model enums
└── utils/
    └── audio_utils.py    # Audio validation and processing
```

## 🔒 Security Notes

1. **🔒 Ephemeral Tokens (Live Tab)**: The Live tab uses **secure ephemeral tokens** generated by the backend. No API key is exposed in the browser.
   - Backend generates short-lived tokens (12 min session, 15 min transmission)
   - Tokens auto-expire for security
   - See `EPHEMERAL_TOKENS.md` for implementation details

2. **Backend API security**: Home and Compare tabs use server-side `GEMINI_API_KEY` which is never exposed to the browser.

3. **Production recommendations**:
   - Add authentication (OAuth 2.0 / JWT)
   - Implement rate limiting
   - Enable HTTPS only
   - Add request logging
   - HIPAA compliance audit logging
   - Configure Supabase Row Level Security (RLS)

## 📦 Build & Deploy

**Build for production:**
```bash
npm run build
npm start
```

**Deploy to Vercel (recommended):**
```bash
vercel --prod
```

Set environment variables in Vercel dashboard:
- `GEMINI_API_KEY` (server-side only)
- `SUPABASE_URL` (for live recording)
- `SUPABASE_SERVICE_KEY` (for database operations)
- `NEXT_PUBLIC_BACKEND_API_URL` (FastAPI backend URL)

## 🧪 Testing

Access the app at http://localhost:3000 and test all 3 tabs:
- **Home**: Test live recording (10s chunks) or upload audio files
- **Live**: Allow microphone access for real-time transcription with ephemeral tokens
- **Compare**: Paste ground truth and test transcript for accuracy metrics (WER, Levenshtein)

## 📄 License

MIT

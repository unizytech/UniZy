- when replicating any screen in front end, refer how other screens handle authentication and authorization and accordingly replicate. Don't try new logic
- when new backend logic and endpoint is being added, refer to ensure there is already no such functionality in other python files and only then add the new code. If they exists, then re-use rather than create new each time

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **COMPACTION REMINDER**: After context compaction, re-read this file to refresh critical project details (especially Supabase project ref and database rules).

## Supabase Project Reference
- When on main git branch, then the supabase project id is as below
- **Project ID**: `yvpyqnkxxgyzaapozafg`
- **Project URL**: https://yvpyqnkxxgyzaapozafg.supabase.co

- When on dev git branch, then the supabase project id is as below
- **Project ID**: `oepojxrximnmqwvnpoiu`
- **Project URL**: https://oepojxrximnmqwvnpoiu.supabase.co

Always use the right project ID when running Supabase MCP commands.

### Supabase Topology (important)
- There is **one** Supabase project in this account: **"Unizy Voice" = main** (`yvpyqnkxxgyzaapozafg`).
- The **dev** ref (`oepojxrximnmqwvnpoiu`) is a **preview branch** of main, NOT a standalone project — so it does not appear in `list_projects`. Address it by its branch ref where a `project_id` is required.
- Migration *history* differs by design: main carries the full migration chain; the dev branch is built from a **squashed schema-only baseline**, so its migration list shows mostly just `baseline` even though the actual schema matches. **Do not judge sync by migration counts — compare the actual schema.**

### Accessing BOTH databases via MCP
Two MCP servers give access to both DBs. Pick by which DB you need:

| Need | MCP server (tool prefix) | How it targets the DB |
|---|---|---|
| **dev** branch | `mcp__supabase__*` | Pinned to dev via `?project_ref=oepojxrximnmqwvnpoiu` — no `project_id` arg |
| **main** (or any project/branch) | `mcp__plugin_supabase_supabase__*` (account-level OAuth) | Pass `project_id` explicitly (`yvpyqnkxxgyzaapozafg` for main, or a branch ref) |

- A third account-wide server **`supabase-unizy`** is defined in `.mcp.json` (stdio `npx @supabase/mcp-server-supabase` with a personal access token, no `project_ref` → reaches any project/branch in the account). Its tools (`mcp__supabase-unizy__*`) only load **after a Claude Code restart** — if they aren't available, use the two servers above, which cover both DBs.
- **Security**: `.mcp.json` holds a live `sbp_…` personal access token. It is gitignored (do NOT commit it). Rotate the token in the Supabase dashboard if it ever leaks.

### Checking main↔dev schema sync
Run an identical schema-fingerprint query against both DBs and diff the results (not migration counts):
```sql
select table_name, count(*) as cols,
       md5(string_agg(column_name||':'||data_type, ',' order by ordinal_position)) as sig
from information_schema.columns where table_schema='public'
group by table_name order by table_name;
```
Run on dev via `mcp__supabase__execute_sql`, on main via `mcp__plugin_supabase_supabase__execute_sql` with `project_id='yvpyqnkxxgyzaapozafg'`. Identical rows ⇒ table/column schema in sync. (This covers tables/columns/types; for a deeper check also compare enums, functions, RLS policies, and indexes.)

## Project Rules

- Always use the standard timestamp format for Supabase migration files: `YYYYMMDDHHMMSS_description.sql`
- Don't create documentation files unless explicitly requested
- **Git Branch Safety**: Before running `git add`, `git commit`, or `git push`, check if on `dev` branch. If not on `dev`, warn the user and ask for confirmation before proceeding.
- **API Auth Permissions**: When creating new API endpoints, always ask the user what auth level is required:
  - **Admin only**: Use `Depends(require_admin)`
  - **Admin + Web**: Use `Depends(get_current_client)` with client_type check
  - **Admin + Web + School**: Use `Depends(get_current_client)` with School admin/counselor validation
  - Available client types: `admin`, `web_app`, `mobile_app`, `school`

### Feature Flags

- **CRITICAL**: `hospitals.feature_flags` is a JSONB column used **only** to return UI configuration to the frontend during auth validation. It controls which UI elements (tabs, buttons, toggles) are visible to users.
- **Do NOT use `feature_flags` to gate backend logic.** Backend features should be controlled by their own configuration (e.g., `doctors.translation_language` controls whether translation runs, not `feature_flags.translation`).
- The frontend reads feature flags from the `/auth/validate` response to show/hide UI features.

### Pipeline Latency Protection

- **CRITICAL**: The transcription and extraction pipeline is latency-sensitive. Before adding ANY new feature that hooks into the pipeline (recording, transcription, extraction, post-processing), you MUST:
  1. **Warn the user** that the change could impact pipeline latency
  2. **Get explicit permission** before proceeding
  3. **Implement as fire-and-forget**: Use `asyncio.create_task()` with try/except wrapper
  4. **Never block the main flow**: New features must not add awaited calls in the critical path
- **Pattern to follow** (see `extraction_service.py` for examples):
  ```python
  # CORRECT: Fire-and-forget, zero latency impact
  try:
      asyncio.create_task(my_new_feature(extraction_id))
  except Exception as e:
      logger.warning(f"Failed to schedule feature: {e}")

  # WRONG: Blocks the pipeline
  await my_new_feature(extraction_id)  # DO NOT DO THIS
  ```

### LLM Provider Name Sanitization

- **CRITICAL**: Never expose LLM provider names (Gemini, Google, Anthropic, Claude, OpenAI, GPT) in log messages, error messages, or any text stored in the database or returned to the frontend.
- **Logger messages**: Use generic tags like `[EXTRACTION]`, `[LLM]`, `[TRANSCRIPTION]` — never `[GeminiService]`, `[LLMFactory]`, `[ClaudeClient]`.
- **Error messages stored in DB** (`llm_usage_log.error_message`, `processing_jobs.error_message`, etc.): Always use `"AI service"` instead of provider names. E.g., `"AI service timed out"` not `"Gemini API timed out"`.
- **Error type names**: Sanitize exception class names before logging. Use `"Timeout"` / `"Connection issue"` instead of raw `TimeoutError`, `RemoteProtocolError`, etc.
- **Utility**: Use `sanitize_error_message()` from `backend/services/error_utils.py` for any error message that may reach the user or be stored in the database. It strips provider names via regex.
- **User-facing exceptions**: All `raise Exception(...)` in LLM service code must use sanitized messages (e.g., `"AI service timed out after 150 seconds - please retry"`).

### Supabase Database Rules

- **Migrations**: Always use `supabase db push` (via CLI) to apply migrations to the database. Do NOT use Supabase MCP `apply_migration` tool.
- **SQL Queries**: SELECT queries can run automatically. Always ask user before running INSERT, UPDATE, or DELETE queries via `execute_sql`.

## Development Commands

**Frontend (Next.js):**
```bash
npm run dev      # Start dev server on port 3000 (Turbopack)
npm run build    # Production build
npm run lint     # ESLint check
```

**Backend (Python FastAPI):**
```bash
./start-backend.sh                                    # Quick start (recommended)
cd backend && source venv/bin/activate && python main.py  # Manual start
```

**Run Both:**
```bash
# Terminal 1: ./start-backend.sh
# Terminal 2: npm run dev
```

**Backend Tests:**
```bash
cd backend && source venv/bin/activate && pytest tests/
pytest tests/test_specific_file.py -v  # Single test file
```

## Architecture Overview

### Hybrid Architecture

- **Frontend**: Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4
- **Backend**: Python FastAPI 0.115.5 + Supabase (PostgreSQL)
- **Real-time**: Supabase Realtime (PostgreSQL change notifications)

### Key Directories

```
app/                    # Next.js frontend
├── components/         # React components (12 tabs/screens)
├── services/           # API clients (geminiClient, recordingService, etc.)
├── hooks/              # React hooks (useProcessingProgress)
└── page.tsx            # Main app with tab navigation

backend/                # Python FastAPI backend
├── routers/            # API route handlers (14 routers)
├── services/           # Business logic (gemini_service, supabase_service, etc.)
├── models/             # Pydantic models
└── supabase/migrations/ # Database migrations

lib/                    # Shared frontend utilities
├── config.ts           # Backend URL config
├── types.ts            # TypeScript types (AppMode enum, API types)
├── summaryApi.ts       # Summary extraction API client
└── patientHistoryApi.ts # Patient history API client
```

### Main Screens (12 Tabs)

**User Test Category:**
1. **VHR** - Virtual Health Record: Recording + file upload with progressive extraction
2. **Live** - Real-time transcription with WebSocket (ephemeral tokens)
3. **Patient** - Patient history: prescriptions, diagnosis, investigations, case summary
4. **Doctor Config** - Per-doctor template visibility and activation
5. **Medicines** - Doctor/hospital medicine list management (CSV upload)
6. **Investigations** - Doctor/hospital investigation list management
7. **Retry** - View and retry failed audio processing sessions

**Admin Category:**
8. **Config** - Template creation with drag-and-drop segment management
9. **Prompts** - Dynamic system prompt management with components
10. **API Keys** - API key management for hospital EHR integrations
11. **Usage** - Extraction history with LLM usage tracking
12. **Compare** - Transcript accuracy testing (WER metrics)

### Core API Endpoints (Backend: http://localhost:8000)

**Recording & Extraction:**
- `POST /api/v1/option1/recording/start` - Start recording session
- `POST /api/v1/option1/recording/chunk` - Upload audio chunk
- `POST /api/v1/summary/extract` - Extract medical summary (unified endpoint)

**Management:**
- `/api/v1/doctors/*` - Doctor CRUD + template activation
- `/api/v1/summary/templates/*` - Template management
- `/api/v1/summary/segments/*` - Segment configuration
- `/api/v1/extractions/*` - Extraction history + edit tracking
- `/api/v1/extractions/merge` - AI-powered extraction merge

**Patient History:**
- `GET /api/v1/patients/{id}/history` - Full patient history
- `GET /api/v1/patients/{id}/case-summary` - AI-generated case summary

**Utilities:**
- `POST /api/ephemeral-token` - Secure tokens for client-side Gemini API
- `GET /docs` - OpenAPI documentation

### Database Schema (Key Tables)

**Core Entities:**
- `doctors` - Doctor profiles
- `consultation_types` - OP, DISCHARGE, NEONATAL, OPHTHALMOLOGY, etc.
- `templates` - Extraction templates (owned by doctors or shared)
- `segment_definitions` - Medical segment prompts and schemas

**Junction Tables:**
- `consultation_type_segments` - Links consultation types to segments
- `template_segments` - Links templates to segments with config overrides
- `doctor_templates` - Template access/activation per doctor

**Recording & Extraction:**
- `recording_sessions` - Audio recording sessions
- `processing_jobs` - Background job tracking with progress_json
- `extractions` - Extraction results with edit history

### Environment Variables

**Frontend (.env.local):**
- `NEXT_PUBLIC_BACKEND_API_URL` - Backend URL (default: http://localhost:8000)
- `NEXT_PUBLIC_SUPABASE_URL` - Supabase project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` - Supabase anon key (for Realtime)

**Backend (backend/.env):**
- `GEMINI_API_KEY` - Google Gemini API key
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_KEY` - Supabase service role key
- `WEBHOOK_URL`, `WEBHOOK_ENABLED`, `WEBHOOK_TOKEN` - Webhook config

### Key Patterns

1. **Real-time Progress**: Frontend subscribes to `processing_jobs` via Supabase Realtime
2. **Template Inheritance**: Global -> Consultation Type -> Template -> Doctor overrides
3. **Edit Tracking**: Original AI extraction preserved, edits stored separately
4. **Ephemeral Tokens**: Secure client-side Gemini API access (12-min session window)

### Important Notes

- **Tailwind v4**: Uses `@import "tailwindcss"` syntax (not `@tailwind` directives)
- **No src/ directory**: Uses Next.js App Router (`app/` directory)
- **Async Backend**: All FastAPI endpoints use async/await
- **segment_code is NOT unique**: Segments linked via junction tables by `id` (UUID)
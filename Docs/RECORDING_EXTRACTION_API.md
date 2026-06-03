# Recording & Extraction API — Integration Guide

This document describes the end-to-end API flow for a **server-backed confidential client**
that records audio, uploads it in chunks, and receives extracted insights for the
`CAREER_DISCUSSION` (Career Counselling) template.

Authentication uses **OAuth 2.0 client-credentials** with short-lived **access tokens**
and rotating **refresh tokens**.

---

## Base URLs

| Environment | Backend base URL |
|---|---|
| Local | `http://localhost:8000` |
| dev / main | (your deployed backend host) |

All paths below are relative to the backend base URL.

## Authentication header

Every pipeline call (steps 2–4) must send the access token from step 1:

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

The client is a `web_app`, token-mode client with **global (all-schools)** access.
You receive a `client_id` + `client_secret` once at provisioning time. Store the
`client_secret` securely — it is never retrievable again.

---

## Flow overview

```
1. POST /api/v1/auth/token            ── client_id + client_secret ──▶ access_token + refresh_token
2. POST /api/v1/option1/recording/start ── template_code=CAREER_DISCUSSION ──▶ correlation_id
3. POST /api/v1/option1/recording/chunk ── audio chunks (is_last=true on final) ──▶ submission_id
   └─ backend transcribes + extracts in the background
4. Webhook  ──▶ your endpoint receives the insights payload  (or poll /status, or Supabase Realtime)
5. POST /api/v1/auth/client-refresh   ── refresh_token ──▶ new access_token + new refresh_token
```

---

## 1. Get an access token

Exchange `client_id` + `client_secret` for an access token and a refresh token.

**Request** — `POST /api/v1/auth/token`

```json
{
  "client_id": "a9b4bc66-5281-4ff8-8c49-a8ef9b6216ff",
  "client_secret": "secret_********************************",
  "grant_type": "client_credentials"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `client_id` | string (UUID) | yes | Issued at provisioning |
| `client_secret` | string | yes | Issued once at provisioning |
| `grant_type` | string | yes | Must be `"client_credentials"` |

**Response** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "KfhK5i3rz0pOCYMNIk9ZpTUQoHJuxQhN96NV5uVRjX13brKtUuZk7wIgx9L7aync",
  "token_type": "Bearer",
  "expires_in": 3600,
  "expires_at": "2026-06-01T17:12:11.882112Z"
}
```

| Field | Type | Notes |
|---|---|---|
| `access_token` | string (JWT) | Send as `Authorization: Bearer …`. Lifetime = client's `token_expiry_minutes` (default 60 min). |
| `refresh_token` | string | Single-use, 30-day lifetime. Use with `/auth/client-refresh` (step 5). |
| `token_type` | string | Always `"Bearer"`. |
| `expires_in` | integer | Access-token lifetime in seconds. |
| `expires_at` | string (ISO 8601) | Absolute access-token expiry. |

**Errors**

| Status | Meaning |
|---|---|
| `400` | `grant_type` is not `"client_credentials"` |
| `401` | Invalid `client_id` / `client_secret`, or client not configured for token auth |

---

## 2. Start a recording session

Creates a session and returns a `correlation_id` used for all subsequent chunk uploads.
Pass the `CAREER_DISCUSSION` template code.

**Request** — `POST /api/v1/option1/recording/start`

```json
{
  "counsellor_id": "770e8400-e29b-41d4-a716-446655440000",
  "student_id": "STU12345",
  "template_code": "CAREER_DISCUSSION",
  "template_name": "Career Counselling discussion",
  "processing_mode": "default",
  "extraction_mode": "full",
  "chunk_duration_seconds": 10
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `counsellor_id` | string (UUID **or external id**) | yes | — | Counsellor performing the session. Accepts the internal UUID **or** your own external id (the integer mapped to `counsellors.external_id`). Malformed → `400`; unknown → `404`. |
| `student_id` | string | yes | — | Free-form student identifier (your own id, MRN, etc.). The backend find-or-creates the student from it — **any string is accepted** (no UUID required). |
| `template_code` | string \| null | no | resolves to counsellor/school default → `OP_CORE` | Use `"CAREER_DISCUSSION"`, or `"TRANSCRIPT_ONLY"` for transcript-only |
| `template_name` | string \| null | no | — | Display name only (human readability) |
| `processing_mode` | string | no | `"default"` | `"fast"` \| `"default"` \| `"thorough"` |
| `extraction_mode` | string | no | `"full"` | `"core"` \| `"additional"` \| `"full"` |
| `chunk_duration_seconds` | integer (0–60) | no | `10` | `0` = single file upload |
| `assistant_id` | string (UUID **or external id**) \| null | no | — | If an assistant initiated the session. Accepts the internal UUID **or** your external id (the integer mapped to `assistants.external_id`). |
| `recording_metadata` | object \| null | no | — | Custom metadata; flows through to `/status` |
| `correlation_id` | string (UUID) \| null | no | generated | Optional. If supplied it **must be a UUID**; otherwise leave it `null` and the backend generates one. Do not pass a non-UUID id here. |
| `is_continuation` | boolean | no | `false` | `true` continues a prior session for the same student/visit |

> **Identifiers — UUID vs your own ids.** `counsellor_id` and `assistant_id` accept **either** the
> backend's internal UUID **or** your own external id: provision your id into
> `counsellors.external_id` / `assistants.external_id` (a unique integer) and then pass it directly,
> e.g. `"counsellor_id": "21"`. `student_id` is already a free-form external identifier — pass any
> string, no mapping needed. The backend-generated ids you receive back (`correlation_id`,
> `session_id`, `submission_id`, `extraction_id`) are **opaque UUID strings** — store and echo them
> as strings, not integers.

**Response** `200 OK`

```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "880e8400-e29b-41d4-a716-446655440000",
  "message": "Recording session started"
}
```

| Field | Type | Notes |
|---|---|---|
| `correlation_id` | string (UUID) | **Use this for every chunk upload in step 3.** |
| `session_id` | string (UUID) | Database session row ID |
| `message` | string | Status message |

---

## 3. Upload audio chunks

Upload audio sequentially. Set `is_last: true` on the final chunk — the response then
returns the `submission_id` that identifies the background processing job.

**Request** — `POST /api/v1/option1/recording/chunk`

```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "chunk_index": 0,
  "audio_data": "<base64-encoded audio>",
  "mime_type": "audio/webm",
  "duration_seconds": 10.0,
  "is_last": false
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `correlation_id` | string (UUID) | yes | — | From step 2 |
| `chunk_index` | integer (≥ 0) | yes | — | Sequential, 0-based |
| `audio_data` | string | yes | — | Base64-encoded audio bytes |
| `mime_type` | string | no | `"audio/webm"` | Audio MIME type |
| `duration_seconds` | number \| null | no | — | Chunk duration |
| `is_last` | boolean | no | `false` | `true` on the final chunk |

**Response** `200 OK` (JSON keys are camelCase)

```json
{
  "message": "Chunk received",
  "chunkIndex": 0,
  "totalChunks": 1,
  "submissionId": null
}
```

On the **final** chunk (`is_last: true`):

```json
{
  "message": "Final chunk received, processing started",
  "chunkIndex": 4,
  "totalChunks": 5,
  "submissionId": "660e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Type | Notes |
|---|---|---|
| `message` | string | Status message |
| `chunkIndex` | integer | Echo of the uploaded chunk index |
| `totalChunks` | integer | Total chunks received so far |
| `submissionId` | string (UUID) \| null | **Present only when `is_last: true`.** Identifies the processing job. |

After the final chunk, the backend transcribes and extracts insights **in the background**.
Retrieve results via one of:

- **Webhook** (push) — the backend POSTs the insights to your configured `WEBHOOK_URL` (step 4).
- **Polling** — `GET /api/v1/option1/recording/status/{submission_id}` returns
  `{ submission_id, status, progress, message, extraction_id, transcript, insights, metrics }`.
- **Supabase Realtime** — subscribe to the `processing_jobs` table for live progress.

---

## 4. Webhook payload (CAREER_DISCUSSION)

When extraction completes, the backend sends an **outgoing** `POST` to each URL configured in
`WEBHOOK_URL`. There is **no inbound webhook endpoint** — your service must expose a receiver.

**Delivery details**

| Aspect | Value |
|---|---|
| Method | `POST` (JSON) |
| Auth header | `Authorization: Bearer <WEBHOOK_TOKEN>` (if configured) |
| Timeout | 10 seconds |
| Retries | 3 attempts, exponential backoff (1s, 2s, 4s) |

**Payload structure** (`WebhookPayload`)

```jsonc
{
  "insights": { /* segment_code → extracted fields (see below) */ },
  "session_info": {
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "submission_id": "660e8400-e29b-41d4-a716-446655440000",
    "session_id": "880e8400-e29b-41d4-a716-446655440000",
    "counsellor_id": "770e8400-e29b-41d4-a716-446655440000",
    "student_id": "STU12345",
    "template_code": "CAREER_DISCUSSION",
    "template_name": "Career Counselling discussion",
    "extraction_mode": "full",
    "processing_mode": "default",
    "consultation_type_code": null
  },
  "metadata": {
    "timestamp": "2026-06-01T10:30:00.000Z",
    "source": "recording",
    "version": "3.1.0"
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `insights` | object | Extracted data, keyed by segment code (see below) |
| `session_info.correlation_id` | string | From step 2 |
| `session_info.submission_id` | string | From step 3 (final chunk) |
| `session_info.session_id` | string | Recording session UUID |
| `session_info.counsellor_id` | string | Counsellor UUID |
| `session_info.student_id` | string | Student identifier |
| `session_info.template_code` | string | `"CAREER_DISCUSSION"` |
| `session_info.template_name` | string | `"Career Counselling discussion"` |
| `session_info.extraction_mode` | string | `core` \| `additional` \| `full` |
| `session_info.processing_mode` | string | Processing mode used |
| `session_info.consultation_type_code` | string \| null | Consultation type, if any |
| `metadata.timestamp` | string (ISO 8601) | When the webhook was generated |
| `metadata.source` | string | `recording` \| `reprocess` \| `merge` \| `transcript_only_extraction` |
| `metadata.version` | string | Payload version (`3.1.0`) |

### `insights` keys for `CAREER_DISCUSSION`

The `insights` object contains one entry per template segment. For the
`CAREER_DISCUSSION` template the segments are (in display order):

The `insights` object is keyed by **camelCase output keys** (not the internal `UPPER_SNAKE`
segment codes) and conforms to the careerzilla reference contract
(`references/updated_meeting_response_structure.json`) — the `parsedValue` shape of each segment.

> **Every key is always present.** A server-side formatter completes the extraction to the
> reference schema before it is stored and delivered, filling any absent field with an empty,
> type-appropriate default (`""`, `[]`, `{}`, or `null`) and recursing into nested objects and
> array items. So you always receive the full skeleton — empty where the session had no content.
> Note the **American spelling** in output keys: `counselorRemarks`, `"Counselor Name"`,
> `"Parent(s) Present"`.

| Output key (camelCase) | Reference label | Value type |
|---|---|---|
| `participants` | Participants | object |
| `keyFacts` | Key Facts | string[] |
| `studentContext` | Student Context | object |
| `workExperience` | Work Experience | object |
| `academics` | Academics | object |
| `supercurricularActivities` | Supercurricular Activities | object |
| `futureGoals` | Future Goals | object |
| `tasks` | Tasks | object[] |
| `nextSteps` | Next Steps | object |
| `assessmentMeters` | Assessment Meters | object |
| `directionalChanges` | Directional Changes | object |
| `counselorRemarks` | Additional Remarks (Counselors Only) | string |

> The nested fields inside each object segment match the reference's `parsedValue` shapes
> (shown in full below). Treat **values** (not keys) defensively — keys are guaranteed.

**Illustrative payload** — the `insights` object below shows the **full conformant shape**
(every key present; values are representative). This structure matches
`references/updated_meeting_response_structure.json` field-for-field.

```jsonc
{
  "insights": {
    "participants": {
      "Counselor Name": "Ms. Rao",
      "Student Name": "Priya S.",
      "Parent(s) Present": "No"
    },
    "keyFacts": [
      "Interested in mechanical engineering",
      "Targeting UK universities"
    ],
    "studentContext": {
      "Parents and Family Background": { "Parent Professions": [], "Family Background": "" },
      "Student Strengths vs. Weaknesses": { "Strengths": [], "Weaknesses/Areas for Improvement": [] },
      "Likes / Dislikes": { "Likes": [], "Dislikes": [] },
      "Technical Skills / Tools / Technologies": { "Programming Languages": "", "Software/Tools": "", "Platforms": "", "Level of Proficiency": "" },
      "Existing Mentors": { "Current Mentors": "", "Type of Mentorship": "" },
      "General Concerns About Student": { "Academic Concerns": "", "Personal/Social Concerns": "", "Career-related Concerns": "" }
    },
    "workExperience": {
      "Current Work Experience": { "Internship Details": "", "Work Experience": "", "Skills Gained": "" },
      "Planned Work Experience": { "Internship Plans": "", "Industry Preferences": "", "Timeline": "" }
    },
    "academics": {
      "Academic Performance": { "Subjects & Grades": {}, "Strong Subjects": [], "Challenging Subjects": [], "Overall Performance": "" },
      "Currently Pursuing Courses": { "Current Grade Level": "", "Core Subjects": "", "Elective Courses": "", "Advanced Courses": "" },
      "Student Academic Interests": { "Primary Interests": [], "Areas of Curiosity": "", "Learning Style": "" },
      "Planned Courses": { "Next Semester/Year": "", "Course Selection Strategy": "", "Prerequisites": "" }
    },
    "supercurricularActivities": {
      "Reading & Learning": { "Books Completed": [], "Books To Start": [], "Guides To Start": [], "Online Courses": [], "Online Learning": [] },
      "Standardised & Competitive Tests": { "Standardised Tests Completed": [], "Competitive Exams Completed": [], "Competitions": [] },
      "Leadership & Extracurriculars": { "Student Council / Leadership Completed": [], "Extracurriculars": [], "Sports": [], "Hobbies": [] },
      "Projects & Service": { "Passion Projects": [], "Research": "", "Internship / Job Shadowing": "", "Community Service / Volunteering": [] },
      "Planned Activities": { "Summer Programs To Start": "", "Activities": [], "Planned Extracurricular Activities": [] }
    },
    "futureGoals": {
      "Career & Academic Interests": { "Course Interests": [], "Career Aspirations": "", "Industry Interests": "", "Alternative Career Options": "" },
      "University & Country Preferences": { "Target Countries": [], "College Aspirations": [], "Priority Order": "", "Program Preferences": "" },
      "Topics of Interest to Study": { "Major Field of Study": "", "Specific Subjects": [], "Interdisciplinary Interests": "" }
    },
    "tasks": [
      {
        "task_name": "Draft personal statement",
        "bucket_id": 1,
        "task_details": "Write a first draft focusing on engineering motivation",
        "start_date": "",
        "end_date": "",
        "duration_in_minutes": 60,
        "task_type": "Once",
        "requires_approval": false,
        "task_category_id": "Academic & Intellectual Pursuits",
        "task_file_resource": ""
      }
    ],
    "nextSteps": {
      "Next Steps for Counselor": { "Action Items": "", "Research Tasks": "", "Preparation for Next Meeting": "" },
      "Next Steps for Student": { "Books": [], "Guides": [], "Competitions": [], "Community Service": [], "Council": [], "Passion Project": [], "Research Tasks": [], "Decisions": [] },
      "Next Steps for Parent": { "Action Items": "", "Information Gathering": "", "Support Required": "" },
      "Next Meeting Details": { "Date": "", "Format": "", "Agenda": "" }
    },
    "assessmentMeters": {
      "Student Anxiety Levels": { "Pre-Session Anxiety": "", "Post-Session Anxiety": "", "Anxiety Triggers": "" },
      "Parent Anxiety Level": { "Parent Anxiety": "", "Parent Concerns": "" },
      "Counselor Assessment Meters": { "Urgency Level": "", "Student Proficiency in English": "", "Career Choice Clarity": "", "Academic Choice Clarity": "" },
      "Financial Considerations": { "Financial Constraints": "", "Financial Support Level": "", "Scholarship Needs": "" }
    },
    "directionalChanges": {
      "Changes in Student Direction": { "Previous Goals": "", "Current Goals": "", "Reason for Change": "", "Impact of Change": "" }
    },
    "counselorRemarks": "Confident student; needs support narrowing university list."
  },
  "session_info": {
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "submission_id": "660e8400-e29b-41d4-a716-446655440000",
    "session_id": "880e8400-e29b-41d4-a716-446655440000",
    "counsellor_id": "770e8400-e29b-41d4-a716-446655440000",
    "student_id": "STU12345",
    "template_code": "CAREER_DISCUSSION",
    "template_name": "Career Counselling discussion",
    "extraction_mode": "full",
    "processing_mode": "default",
    "consultation_type_code": null
  },
  "metadata": {
    "timestamp": "2026-06-01T10:30:00.000Z",
    "source": "recording",
    "version": "3.1.0"
  }
}
```

Your webhook receiver should respond with `2xx` quickly; non-2xx triggers the retry policy.

---

## 5. Refresh the access token

When the access token nears expiry, exchange the refresh token for a new pair.
Refresh tokens are **single-use** — each refresh returns a new refresh token and
revokes the old one (rotation).

**Request** — `POST /api/v1/auth/client-refresh`

```json
{
  "client_id": "a9b4bc66-5281-4ff8-8c49-a8ef9b6216ff",
  "refresh_token": "KfhK5i3rz0pOCYMNIk9ZpTUQoHJuxQhN96NV5uVRjX13brKtUuZk7wIgx9L7aync",
  "grant_type": "refresh_token"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `client_id` | string (UUID) | yes | Same client |
| `refresh_token` | string | yes | From step 1 (or a previous refresh) |
| `grant_type` | string | yes | Must be `"refresh_token"` |

**Response** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "AnUdKApfjooeWXRMosVLo7FxUOhnksYfjvtcxBzkC3eEFu457UboLOViclMXGpI2",
  "token_type": "Bearer",
  "expires_in": 3600,
  "expires_at": "2026-06-01T17:12:26.420848Z"
}
```

Fields are identical to step 1. **Replace both stored tokens** with the new values;
the previous refresh token is now invalid (`401 "Invalid or expired refresh token"` if reused).

**Errors**

| Status | Meaning |
|---|---|
| `400` | `grant_type` is not `"refresh_token"` |
| `401` | Refresh token invalid, expired, already used, or client inactive |

---

## 6. Poll processing status

Polling alternative to the webhook / Realtime. Use the `submission_id` returned by the
final chunk (step 3) or by a reprocess (step 7). Poll until `status` is terminal.

**Request** — `GET /api/v1/option1/recording/status/{submission_id}`

| Param | In | Type | Notes |
|---|---|---|---|
| `submission_id` | path | string (UUID) | From step 3 (final chunk) or step 7 |

No request body. Send the `Authorization: Bearer` header.

**Response** `200 OK`

```json
{
  "submission_id": "660e8400-e29b-41d4-a716-446655440000",
  "status": "COMPLETED",
  "progress": 100,
  "message": "Extraction complete",
  "extraction_id": "990e8400-e29b-41d4-a716-446655440000",
  "transcript": "Counsellor: Let's talk about your university options...",
  "insights": { "participants": { "...": "..." }, "futureGoals": { "...": "..." }, "counselorRemarks": "..." },
  "metrics": { "transcription_ms": 4200, "extraction_ms": 8100 }
}
```

| Field | Type | Notes |
|---|---|---|
| `submission_id` | string (UUID) | Echo of the polled submission |
| `status` | string | Job status (e.g. `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`) |
| `progress` | integer | Progress percentage (0–100) |
| `message` | string | Human-readable status message |
| `extraction_id` | string (UUID) \| null | Present once `COMPLETED` |
| `transcript` | string \| null | Present once `COMPLETED` |
| `insights` | object \| null | Extracted data (same shape as the webhook `insights`); present once `COMPLETED` |
| `metrics` | object \| null | Processing-time metrics |

> Poll at a modest interval (e.g. every 2–3 s) until `status` is `COMPLETED` or `FAILED`.
> For lower latency / no polling, prefer the webhook (step 4) or a Supabase Realtime
> subscription on the `processing_jobs` table.

---

## 7. Reprocess / retry a session

Re-run extraction for an existing recording session — e.g. to retry a failed job or
re-extract against a different template. Operates on the **session UUID** (`session_id`
from step 2), and returns a **new** `submission_id` to track via step 6 / the webhook.

**Request** — `POST /api/v1/recordings/{session_id}/reprocess`

| Param | In | Type | Notes |
|---|---|---|---|
| `session_id` | path | string (UUID) | The recording session to reprocess (from step 2) |

```json
{
  "mode": "new_extraction",
  "template_code": "CAREER_DISCUSSION",
  "processing_mode": "default",
  "extraction_mode": "full"
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `mode` | string | yes | — | `"new_extraction"` (re-transcribe + extract) or `"reprocess_transcript"` (extract only, reuse existing transcript) |
| `template_code` | string | yes | — | Template to extract with, e.g. `"CAREER_DISCUSSION"` |
| `processing_mode` | string | no | `"default"` | `"fast"` \| `"default"` \| `"thorough"` |
| `extraction_mode` | string | no | `"full"` | `"core"` \| `"additional"` \| `"full"` |

**Response** `200 OK`

```json
{
  "submission_id": "aa0e8400-e29b-41d4-a716-446655440000",
  "mode_used": "new_extraction",
  "fallback_used": false,
  "message": "Reprocessing started"
}
```

| Field | Type | Notes |
|---|---|---|
| `submission_id` | string (UUID) | **New** job ID — track via step 6 or the webhook (step 4) |
| `mode_used` | string | Mode actually applied |
| `fallback_used` | boolean | `true` if the requested mode fell back (e.g. `reprocess_transcript` requested but no transcript existed, so it re-transcribed) |
| `message` | string | Status message |

On completion, the same webhook payload as step 4 is delivered, with
`metadata.source: "reprocess"`.

---

## 8. Fetch insights after the fact

Two read endpoints to retrieve results later — by `extraction_id` (from the webhook/`/status`) or by
your student id. The `insights` returned is the **same conformant structure** as the webhook/status.

### 8a. By extraction id

**Request** — `GET /api/v1/option1/recording/extraction/{extraction_id}`

| Param | In | Type | Notes |
|---|---|---|---|
| `extraction_id` | path | string (UUID) | The `extraction_id` from `/status` (step 6) or the webhook (step 4) |

No request body. Send the `Authorization: Bearer` header.

**Response** `200 OK`

```jsonc
{
  "extraction_id": "990e8400-e29b-41d4-a716-446655440000",
  "session_id": "880e8400-e29b-41d4-a716-446655440000",
  "student_id": "STU12345",
  "counsellor_id": "770e8400-e29b-41d4-a716-446655440000",
  "transcript": "Counsellor: Let's talk about your university options…",
  "insights": { "participants": { /* … */ }, "counselorRemarks": "…" },
  "created_at": "2026-06-02T15:33:24.628132Z"
}
```

| Field | Type | Notes |
|---|---|---|
| `extraction_id` | string (UUID) | Echo of the requested id |
| `session_id` | string (UUID) \| null | The recording session it came from |
| `student_id` | string \| null | **Your** external student identifier |
| `counsellor_id` | string (UUID) \| null | Internal counsellor UUID |
| `transcript` | string \| null | Full transcript |
| `insights` | object \| null | Same conformant shape as the webhook/status `insights` (section 4) |
| `created_at` | string (ISO 8601) | When the extraction was created |

**Errors:** `400` malformed UUID; `404` extraction not found.

### 8b. By student

**Request** — `GET /api/v1/option1/recording/student/{student_id}/extractions`

| Param | In | Type | Default | Notes |
|---|---|---|---|---|
| `student_id` | path | string | — | **Your** external student identifier (the same value you pass to `/recording/start`) |
| `limit` | query | integer (1–100) | `20` | Max number of extractions to return (newest first) |

No request body. Send the `Authorization: Bearer` header.

**Response** `200 OK`

```jsonc
{
  "student_id": "STU12345",
  "count": 4,
  "extractions": [
    {
      "extraction_id": "990e8400-e29b-41d4-a716-446655440000",
      "session_id": "880e8400-e29b-41d4-a716-446655440000",
      "created_at": "2026-06-02T15:33:24.628132Z",
      "insights": { "participants": { /* … */ }, "counselorRemarks": "…" }
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `student_id` | string | Echo of your external id |
| `count` | integer | Number of extractions returned |
| `extractions[]` | array | Newest first; each item has `extraction_id`, `session_id`, `created_at`, and the full `insights` |

**Errors:** `404` if no student exists for that external id.

---

## Token lifecycle summary

- **Access token** — JWT, ~60 min, sent on every API call. Stateless (signature-verified).
- **Refresh token** — opaque, 30 days, single-use, rotated on every refresh.
- On `401` from a pipeline call, run step 5 to get a fresh access token and retry.
- Keep `client_secret` and refresh tokens **server-side only** (confidential client).

# HIPAA Compliance Plan

**Created:** 2026-02-26
**Status:** In Progress
**Owner:** Engineering Team

---

## Overview

This document outlines the HIPAA compliance roadmap for the AI Live Recorder platform, which processes medical consultation audio, transcripts, and clinical extractions. HIPAA (Health Insurance Portability and Accountability Act) requires safeguards for Protected Health Information (PHI) across technical, administrative, and physical domains.

---

## Phase 1: PHI Removal from AI Outputs (COMPLETED)

**Status: Done (2026-02-26)**

All prompts — both code-level and database-stored — have been updated to explicitly exclude PHI from AI-generated outputs.

### Changes Made

#### Code-Level Prompts (`backend/services/prompts.py`)

| Prompt | Change |
|--------|--------|
| `MEDICAL_EXTRACTION_PROMPT_BASE` | Removed `patient_info` block (name, phone, email). Added HIPAA rule #8. Removed "Name" from "Patient Details" segment. |
| `MEDICAL_EXTRACTION_PROMPT_CONCISE` | Removed `patient_info` block. Removed "Patient Info (name)" from segment list. Added HIPAA rule. |
| `MEDICAL_EXTRACTION_PROMPT_SMALL_SYSTEM` | Added HIPAA COMPLIANCE section. |
| `MEDICAL_EXTRACTION_PROMPT_SMALL_USER` | Already clean — no PHI fields. |

#### Hardcoded Fallback Prompt (`backend/services/system_prompt_service.py`)

| Prompt | Change |
|--------|--------|
| `BASE_SYSTEM_PROMPT_OP` | Updated rule 7 to explicitly list all HIPAA identifiers (names, DOB, phone, address, email, SSN, MRN/UHID, IP numbers, registration numbers, etc.) |

#### Database System Prompt Components (both dev + production)

| Component Code | Configs Using It | Change |
|----------------|------------------|--------|
| `RULES_GKNM` | Cardio base, OBGYN base | Added rule 14: HIPAA PHI exclusion (was completely missing) |
| `TRANSCRIPTION_BASE_PROMPT` | Transcription Only | Added PHI Protection section — redact names to `[PATIENT]`, phone/address to `[REDACTED]` |
| `COMBINED_EMOTION_BASE_PROMPT` | (emotion analysis) | Added HIPAA PHI Protection section |
| `TEXT_EMOTION_BASE_PROMPT` | Text Emotion Analysis | Added HIPAA Compliance to Important Notes |
| `AUDIO_EMOTION_BASE_PROMPT_COMBINED` | Audio Emotion (Combined) | Added HIPAA Compliance with transcription redaction rules |
| `AUDIO_EMOTION_BASE_PROMPT_STANDALONE` | Audio Emotion (Standalone) | Added HIPAA Compliance |
| `VALIDATION_FOR_OP` | Ultra concise OP | Added PHI validation check to checklist |
| `VALIDATION_FOR_OP_DISCH` | Concise base, Cardio base, OBGYN base, Op system | Added PHI validation check to checklist |

#### Database Segment Definitions (both dev + production)

| Segment Code | Change |
|--------------|--------|
| `PATIENT_INFORMATION` | Removed `name`, `address`, `contact_number`, `registration_number`, `ip_number` from JSON schema. Updated prompt to explicitly prohibit PHI extraction. |
| `SUMMARY` | Added "NEVER include patient names" instruction with updated examples using "the patient" |
| `VISIT_SUMMARY` | Added "NEVER include patient names" instruction with updated examples |
| `CLINICAL_NOTES` | Prepended PHI exclusion rule to both variants |

#### Cache Invalidation

- Cleared all `assembled_system_prompt` on `system_prompt_configurations` table
- Cleared all assembled template prompts (`assembled_full_prompt`, `assembled_audio_prompt`, `assembled_text_emotion_prompt`, `assembled_combined_emotion_prompt`) on `templates` table
- Next extraction will automatically rebuild prompts with PHI-free rules

### HIPAA Safe Harbor De-Identification (18 Identifiers)

The following identifiers are now explicitly excluded from all AI outputs:

1. Names
2. Dates (except year) — birth date, admission date, discharge date
3. Phone numbers
4. Geographic data (addresses)
5. Fax numbers
6. Email addresses
7. Social Security numbers
8. Medical record numbers (MRN/UHID)
9. Health plan beneficiary numbers
10. Account numbers
11. Certificate/license numbers
12. Vehicle identifiers
13. Device identifiers/serial numbers
14. URLs
15. IP addresses
16. Biometric identifiers
17. Full-face photographs
18. Any other unique identifying number

---

## Phase 2: Business Associate Agreements (BAAs)

**Priority: P0 — CRITICAL**
**Status: Not Started**
**Effort: High (Google), Low (Supabase)**

Without BAAs, transmitting PHI to third-party processors is a HIPAA violation regardless of prompt-level de-identification.

### 2.1 Google Cloud — Migrate to Vertex AI

**Current state:** The platform uses the consumer `google-genai` SDK to send patient audio and transcripts to Google Gemini API. The consumer API is NOT covered under Google's HIPAA BAA.

**Required action:**
- Migrate from `google-genai` consumer SDK to **Vertex AI** (Google Cloud's HIPAA-eligible AI platform)
- Sign a Google Cloud BAA (available for Vertex AI under Google Cloud's HIPAA-covered services)
- Update `backend/services/gemini_service.py` and `backend/services/gemini_client_factory.py` to use Vertex AI endpoints
- Update API key management to use Google Cloud service accounts instead of consumer API keys

**Impact:** This is the single most important HIPAA compliance item. Audio files containing patient conversations are PHI, and sending them to a non-BAA-covered service is a direct violation.

### 2.2 Supabase BAA

**Current state:** Supabase offers BAAs on Pro and Enterprise plans.

**Required action:**
- Verify current Supabase plan supports BAA
- Contact Supabase support to sign a BAA if not already done
- Document the signed BAA

### 2.3 Webhook Recipients

**Current state:** The platform can send extraction data to external webhooks.

**Required action:**
- Identify all webhook endpoints receiving extraction data
- Ensure each recipient has a signed BAA
- Sanitize webhook payloads to send only metadata if BAA is not in place (see Phase 7)

---

## Phase 3: Audit Logging

**Priority: P1**
**Status: Not Started**
**Effort: Medium**

HIPAA requires logging who accessed what PHI and when.

### 3.1 Create Audit Log Infrastructure

Create an `audit_logs` table:

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    client_type TEXT,           -- 'admin', 'web_app', 'mobile_app', 'ehr'
    action TEXT,                -- 'view_extraction', 'edit_extraction', 'view_patient_history', etc.
    resource_type TEXT,         -- 'extraction', 'patient', 'recording_session'
    resource_id UUID,
    ip_address INET,
    user_agent TEXT,
    metadata JSONB,             -- additional context (e.g., fields accessed)
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at);
```

### 3.2 Add Audit Middleware to FastAPI

- Create middleware that logs every request to PHI-accessing endpoints
- Key events to log:
  - Extraction creation (POST /extract)
  - Extraction view (GET /extractions/{id})
  - Patient history access (GET /patients/{id}/history)
  - Case summary generation (GET /patients/{id}/case-summary)
  - Extraction edit (PUT /extractions/{id})
  - Data export / webhook delivery
  - Recording session access

### 3.3 Audit Log Retention

- Retain audit logs for minimum 6 years (HIPAA requirement)
- Implement log archival to cold storage after 1 year

---

## Phase 4: Application Log Hygiene

**Priority: P1**
**Status: Not Started**
**Effort: Medium**

Backend logs must not contain PHI.

### 4.1 Audit Log Statements

Review all `logger.info/debug/warning/error` calls in these critical files:

| File | Risk |
|------|------|
| `extraction_service.py` | May log extraction content |
| `gemini_service.py` | May log prompts containing transcripts |
| `recording_processor.py` | May log audio processing details |
| `merge_service.py` | May log merged extraction data |
| `template_assembly_service.py` | Lower risk — prompt assembly |
| `background_tasks.py` | May log webhook payloads |

### 4.2 Sanitization Rules

- Log only IDs and metadata: extraction_id, session_id, segment_count, processing_time
- NEVER log: transcript text, extraction content, patient demographics, audio data
- Replace any debug logging of full responses with truncated/hashed versions

### 4.3 Log Storage Security

- Configure log rotation (max 100MB per file, 30-day retention)
- Ensure log files are on encrypted volumes
- Restrict log file access to ops personnel only

---

## Phase 5: Audio File Handling & Secure Deletion

**Priority: P2**
**Status: Not Started**
**Effort: Low**

### 5.1 Audit Current Audio Lifecycle

Review `recording_processor.py` to verify:

- Audio buffers are zeroed/cleared after processing
- Temporary files use `tempfile.NamedTemporaryFile(delete=True)` or explicit secure deletion
- No audio is persisted beyond what's necessary

### 5.2 Implement Secure Deletion

- Add explicit cleanup in `finally` blocks for audio processing
- Log temp file lifecycle: created -> processed -> deleted
- Set maximum audio retention: delete after extraction completes or after 24 hours max

### 5.3 Supabase Storage

- If audio is stored in Supabase Storage, ensure bucket-level encryption is enabled
- Implement automatic expiration policies on audio storage buckets

---

## Phase 6: Data Retention & Deletion Policy

**Priority: P2**
**Status: Not Started**
**Effort: Medium**

### 6.1 Define Retention Periods

| Data Type | Retention Period | Justification |
|-----------|-----------------|---------------|
| Medical extractions | 7 years | Medical record retention laws |
| Audio recordings | 30 days | Needed only for reprocessing |
| Transcripts | 7 years | Part of clinical record |
| Application logs | 1 year | Operational needs |
| Audit logs | 6 years | HIPAA requirement |
| Processing jobs | 90 days | Debugging/monitoring |

### 6.2 Implement Automated Deletion

- Create scheduled background tasks (cron jobs) that purge expired data
- Run daily at off-peak hours
- Log all deletions to audit log

### 6.3 Right to Delete (Patient Data Erasure)

- Implement API endpoint for patient data erasure requests
- Must delete: extractions, recordings, transcripts, patient history references
- Must retain: audit logs of the deletion itself
- Document the erasure process

---

## Phase 7: Webhook Payload Security

**Priority: P2**
**Status: Not Started**
**Effort: Low**

### 7.1 Audit Current Webhook Payloads

Review `background_tasks.py` to determine what data is sent in webhooks.

### 7.2 Sanitize Payloads

- Send only metadata: extraction_id, status, consultation_type, timestamp
- Do NOT send: full extraction data, transcript, patient demographics
- Recipients should use the API (with authentication) to fetch full data

### 7.3 Webhook Security

- Require HTTPS for all webhook endpoints
- Implement HMAC payload signing for webhook integrity verification
- Log all webhook deliveries to audit log

---

## Phase 8: Row-Level Security (Access Controls)

**Priority: P3**
**Status: Not Started**
**Effort: High**

### 8.1 Doctor-Scoped Access

- Doctor A can only see extractions from their own consultations
- Implement RLS policies on `medical_extractions`, `recording_sessions`

### 8.2 Hospital-Scoped Access

- Hospital staff can only access data from their hospital
- EHR integrations scoped to their hospital's patients

### 8.3 Admin Access

- Full access with mandatory audit logging
- Implement admin action review/approval for bulk operations

### 8.4 Implementation Approach

```sql
-- Example RLS policy for medical_extractions
ALTER TABLE medical_extractions ENABLE ROW LEVEL SECURITY;

CREATE POLICY doctor_access ON medical_extractions
    FOR SELECT
    USING (doctor_id = auth.uid() OR is_admin(auth.uid()));
```

---

## Phase 9: Encryption (Defense-in-Depth)

**Priority: P3**
**Status: Not Started**
**Effort: Medium**

### 9.1 Transport Security

- Enforce HTTPS-only in production (redirect HTTP -> HTTPS)
- Add HSTS headers (Strict-Transport-Security)
- Ensure backend FastAPI is behind HTTPS reverse proxy

### 9.2 Application-Level Encryption

- Consider encrypting sensitive columns with AES-256:
  - `medical_extractions.extraction_data`
  - `recording_sessions` audio references
- Use envelope encryption with a KMS (Key Management Service)

### 9.3 Key Management

- Store encryption keys in a dedicated KMS (AWS KMS, Google Cloud KMS)
- Rotate keys annually
- Never store encryption keys alongside encrypted data

---

## Phase 10: Breach Notification Process

**Priority: P3**
**Status: Not Started**
**Effort: Low (documentation)**

### 10.1 Incident Response Plan

Document a formal plan covering:

1. **Detection**: How breaches are discovered (monitoring, alerts, user reports)
2. **Containment**: Immediate steps to stop ongoing breach
3. **Investigation**: Root cause analysis, scope assessment
4. **Notification**: Who to notify and when

### 10.2 Notification Requirements

- **HHS (Department of Health and Human Services)**: Within 60 days of discovery
- **Affected individuals**: "Without unreasonable delay" and no later than 60 days
- **Media**: If breach affects 500+ individuals in a single jurisdiction

### 10.3 Roles & Responsibilities

- Designate a **Privacy Officer** responsible for HIPAA compliance
- Designate a **Security Officer** responsible for technical safeguards
- Document escalation chain for breach incidents

---

## Phase 11: Security Hardening

**Priority: P3**
**Status: Ongoing**
**Effort: Continuous**

### 11.1 API Security

- API rate limiting to prevent data scraping
- Input validation on all endpoints (prevent injection attacks)
- Error message sanitization (already done — commit `dc67481`)
- CORS restricted to specific production domains

### 11.2 Dependency Management

- Regular dependency audits: `pip audit`, `npm audit`
- Automated vulnerability scanning in CI/CD
- Pin dependency versions to prevent supply chain attacks

### 11.3 Key Rotation

- Rotate Supabase API keys periodically
- Rotate Gemini/Vertex AI API keys
- Rotate webhook tokens

### 11.4 Penetration Testing

- Annual penetration test by a qualified security firm
- Address all critical/high findings within 30 days

---

## Priority Summary

| Priority | Phase | Area | Effort | Status |
|----------|-------|------|--------|--------|
| **DONE** | 1 | PHI Removal from AI Outputs | Done | Completed |
| **P0** | 2.1 | BAA with Google (migrate to Vertex AI) | High | Not Started |
| **P0** | 2.2 | BAA with Supabase | Low | Not Started |
| **P1** | 3 | Audit Logging | Medium | Not Started |
| **P1** | 4 | Application Log Hygiene (no PHI in logs) | Medium | Not Started |
| **P2** | 5 | Audio File Secure Deletion | Low | Not Started |
| **P2** | 6 | Data Retention & Deletion Policy | Medium | Not Started |
| **P2** | 7 | Webhook Payload Security | Low | Not Started |
| **P3** | 8 | Row-Level Security (Access Controls) | High | Not Started |
| **P3** | 9 | Encryption (Application-Level) | Medium | Not Started |
| **P3** | 10 | Breach Notification Process | Low | Not Started |
| **P3** | 11 | Security Hardening | Ongoing | Partially Done |

---

## References

- [HIPAA Security Rule](https://www.hhs.gov/hipaa/for-professionals/security/index.html)
- [HIPAA Safe Harbor De-Identification](https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/de-identification/index.html)
- [Google Cloud HIPAA Compliance](https://cloud.google.com/security/compliance/hipaa)
- [Supabase HIPAA Compliance](https://supabase.com/docs/guides/platform/hipaa)

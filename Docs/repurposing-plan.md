# Repurposing Plan — Healthcare → Schools Counselling Platform

> **Status:** Phase 0 (planning). No schema/code changes until each phase is approved.
> **Spelling:** British throughout — *counsellor* / *counselling* (double-l), *behaviour*, *organise*, etc.
> **Rollout rule:** every change lands on the **dev** preview branch first → validate → then main. Every schema change is a timestamped migration (`YYYYMMDDHHMMSS_*.sql` via `supabase db push`) so it flows dev→main.

---

## 1. Domain mapping

| Healthcare (base table — **unchanged**) | Schools alias / vocabulary |
|---|---|
| `hospitals` | **schools** (alias view) |
| `doctors` | **counsellors** (alias view) |
| `nurses` | **assistants** (alias view) |
| `patients` | **students** (alias view) |
| `medical_extractions` | **session_extractions** (alias view) |
| `consultation_types` | *name kept* → used as counselling session types |
| `templates` | *name kept* → counselling note templates |
| `recording_sessions` | *name kept* → counsellor–student session recordings |
| `patient_interventions`, `intervention_*` | student interventions / referrals / support plans |
| `triage_*` | student **risk triage** (safeguarding / self-harm severity) |
| `clinical_severity_assessments`, `care_quality_risk`, `patient_dropoff_risk` | student wellbeing & risk (incl. dropout risk) |
| `clinical_guidelines/conditions/chunks` (RAG) | counselling frameworks / resources RAG |
| `phi_audit_log` | safeguarding / student-data audit |

**UI tab renames:** `VHR` → **VSR** (Virtual Student Record); `Patient` → **Student**; `Doctor Config` → **Counsellor Config**.

## 2. Module disposition

- **Keep (core infra) → recontextualise content later:** recording, extraction, reprocess (Retry), merge, continue session, emotion analysis, interventions, triage, insights/dashboards, embeddings + NL Q&A.
- **Rename via alias views:** the entities in §1.
- **Retire now (Phase 2):**
  - **Billing & fees** — `bills`, `bill_line_items`, `room_rate_master`, `procedure_fee_master`, `hospital_intervention_pricing`, fee columns + billing router/UI.
  - **EHR/EMR** — `hospital_ehr`, `ehr_types`, `template_ehr`, EHR token auth, RASTER push, `ehr_payload_json` + EHR router/UI.
- **Keep & repurpose later (do NOT retire):**
  - **Medicine / investigation lookups** (`*_medicine_lists`, `*_investigation_lists`, match logs) → reused as counselling **resource-library lookups**.
  - **Radiology standard-output generation** (`radiology_*`, `RS_*` templates) → reused for **counselling report** generation.
- **Defer:** legacy healthcare templates (`OP_SHORT`, `PSG_*`, …), legacy consultation types, and test tenants are **not** retired now — handled in Phase 5/6 once the new context works.

> **Decision updates (2026-05-30):** (1) `UsageSummaryScreen` **kept** for now. (2) **RASTER + neonatal (`NEO_*`) specialty packs now retire WITH EHR in Phase 2** (`aosta_service.py`, `raster_api_service.py`, `neo_*`) — moved out of keep-repurpose. (3) `patient_dropoff_risk` fields **renamed to student-engagement vocab** in Phase 4.

## 3. Phased execution (each phase: dev first → validate → main)

| Phase | What | Risk |
|---|---|---|
| **1 — Naming / compat layer** | Migration: alias **views** (`schools`, `counsellors`, `assistants`, `students`, `session_extractions`) with `security_invoker=true`. UI: relabel terminology only (Counsellor/Student/School/Session; VHR→VSR; Patient→Student). No base-table or route changes. | 🟢 Very low (additive) |
| **2 — Retire Billing + EHR** | 2a: hide tabs + gate routers via `feature_flags` (data stays). 2b (later): drop tables/columns. **⚠️ Inventory confirms EHR is embedded in the keep-core extraction pipeline** — `extraction_service.py` writes `ehr_payload_json` (~L1802-1815) and calls `schedule_ehr_sync` (~L2087-2098, + an edit-path hook). EHR teardown is **pipeline-sensitive**: stub those hooks first under the latency rule, then remove routes/services/columns. Billing also couples to `intervention_orchestrator.py` via `revenue_interventions_service.py`. See `repurposing-inventory.md` §3, §6. | 🟡→🟠 Medium (pipeline-touch) |
| **3 — Taxonomy scaffolding** | Reuse `consultation_types` / `templates` / `segment_definitions` / `system_prompt_*` structure; seed a minimal counselling session-type set + starter note template + placeholder prompts. Content filled later. | 🟢🟡 Low–med |
| **4 — Recontextualise kept workflows** | Rewrite extraction/transcription prompts, triage rubric (student risk), interventions catalogue, insights, emotion segments, Q&A knowledge base for counselling. | 🟡 Pipeline-sensitive |
| **5 — Legacy data cleanup** | Retire old healthcare templates, old consultation types, test tenants (blast-radius + dev-first protocol). | 🔴 Destructive (gated) |
| **6 — Physical rename (optional, final)** | Rename base tables/columns to counselling terms, collapse views — only once stable. | 🔴 High churn |

## 4. Technical guardrails

- **Every schema change = timestamped migration**; no ad-hoc DDL on main.
- **Alias views:** `security_invoker=true`; a simple `select *` view over one table is auto-updatable, but it freezes its column list at creation — recreate the view when the base table gains columns.
- **Pipeline latency rule:** any change touching the recording/transcription/extraction path must be fire-and-forget + warned + approved.
- **`feature_flags` JSONB** = UI gating only; the lever to hide Billing/EHR tabs in Phase 2 without deleting code.
- **Provider-name sanitisation** rule applies to all new prompt/LLM code.

## 5. Phase-1 alias views (draft DDL)

```sql
create or replace view schools             with (security_invoker = true) as select * from hospitals;
create or replace view counsellors         with (security_invoker = true) as select * from doctors;
create or replace view assistants          with (security_invoker = true) as select * from nurses;
create or replace view students            with (security_invoker = true) as select * from patients;
create or replace view session_extractions with (security_invoker = true) as select * from medical_extractions;
```

## 6. Resolved decisions

1. **`assistants` = simplified access** — do not carry over the full `nurses` access model (template access + counsellor links). Strip to a minimal access model in Phase 1/3.
2. **Phase-3 session-type starter set** (default): **Intake, Follow-up, Crisis/Risk, Academic, Careers, Behavioural, Group**.
3. **`Doctor Config` tab → `Counsellor Config`** (added to the Phase-1 UI relabel set).

---

*A companion `repurposing-inventory.md` (auto-generated file-by-file mapping) accompanies this plan.*

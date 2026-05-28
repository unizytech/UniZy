# Multi-Layered Clinical Triage Suggestion Engine - Implementation Plan

> **Status**: Phase 0.5 In Progress
> **Objective**: Build a multi-layered contextual triage system that provides reliable, India-specific clinical recommendations

## Executive Summary

Transform the existing MVP triage engine into a multi-layered system that considers:
- Patient context (allergies, emotions, finances, compliance, prior interventions)
- Doctor's personal triage history and patterns
- Hospital/peer intelligence from same-specialty doctors (cross-hospital, same specialty)
- India-specific differential trees
- RAG from 71 Indian medical society guidelines
- Gemini AI synthesis with contextual adjustments

## Design Decisions (User Confirmed)

| Question | Decision |
|----------|----------|
| Feedback timing | Optional (not required immediately) |
| Layer override | Yes - doctors can disable specific layers |
| Hospital scope | Cross-hospital, but same specialty only |
| Admin visibility | Hospital admins CAN see individual doctor patterns |
| Outcome tracking | Deferred (difficult to track patient outcomes) |

---

## Existing Infrastructure (Leverage, Don't Recreate)

The following **already exists** in the database:

| What | Segment Code | Use For |
|------|--------------|---------|
| Drug allergies | `ALLERGIES`, `CAUTION` | Patient safety vetos |
| Anxiety (pre-consultation) | `ANXIETY_PRE_CONSULTATION` | Baseline emotional state |
| Anxiety (post-consultation) | `ANXIETY_POST_CONSULTATION` | Communication effectiveness |
| Other emotions | `OTHER_EMOTIONS_DETECTED` | Fear, anger, depression detection |
| Financial concerns | `FINANCIAL_CONCERNS` | Cost-sensitive recommendations |
| Compliance likelihood | `TREATMENT_COMPLIANCE_LIKELIHOOD` | Regimen simplification |
| Patient history | `HISTORY`, `HISTORY_OF_PRESENT_ILLNESS` | Chronic conditions, past medical |
| Prior interventions | `patient_interventions` table | Avoid ineffective interventions |
| Intervention definitions | `intervention_definitions` table | Categories: mental_health, financial, compliance, emotional |
| Doctor specialty | `doctors.specialization` | Peer filtering |
| Hospital affiliation | `doctors.hospital_id` | Same-hospital queries |
| Hospital location | `hospitals.city`, `hospitals.state` | Regional context |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     MULTI-LAYERED TRIAGE ENGINE                                  │
│                                                                                  │
│  INPUT: Extraction + Patient ID + Doctor ID + Hospital ID                        │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 0: PATIENT CONTEXT (Priority: HIGHEST - Safety)                       ││
│  │ • Drug allergies → VETO contraindicated suggestions                         ││
│  │ • Emotional state (anxiety/depression) → Communication adjustments          ││
│  │ • Financial concerns → Cost-sensitive recommendations                       ││
│  │ • Compliance history → Simplified regimens                                  ││
│  │ • Prior intervention outcomes → Avoid what didn't work                      ││
│  │ • Current medications → Drug interaction checks                             ││
│  │ • Chronic conditions → Dose adjustments, contraindications                  ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                              ↓                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 1: DOCTOR'S PERSONAL HISTORY                                          ││
│  │ • Past triage decisions for similar presentations                           ││
│  │ • AI suggestion acceptance/rejection patterns                               ││
│  │ • Practice style (aggressive/moderate/conservative)                         ││
│  │ • Preferred first-line investigations                                       ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                              ↓                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 2: HOSPITAL/PEER INTELLIGENCE                                         ││
│  │ • Same-specialty doctors at same hospital                                   ││
│  │ • Emergent hospital protocols from collective decisions                     ││
│  │ • Outlier detection (flag unusual patterns)                                 ││
│  │ • Regional/seasonal adjustments                                             ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                              ↓                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 3: DIFFERENTIAL TREES (Existing - India-Specific)                     ││
│  │ • Hardcoded evidence-based differentials                                    ││
│  │ • Endemic diseases (Dengue, Malaria, TB, Typhoid, Scrub Typhus)            ││
│  │ • 8 specialties covered                                                     ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                              ↓                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 4: RAG FROM CLINICAL GUIDELINES                                       ││
│  │ • 71 Indian medical society guidelines (ICMR, IAP, NNF, FOGSI, etc.)        ││
│  │ • Vector search with pgvector                                               ││
│  │ • Source citations for each recommendation                                  ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                              ↓                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 5: GEMINI AI SYNTHESIS                                                ││
│  │ • Combines all layer outputs                                                ││
│  │ • Applies contextual filters (seasonal, regional, cost)                     ││
│  │ • Handles edge cases not covered by other layers                            ││
│  │ • Final prioritization and deduplication                                    ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  OUTPUT: Prioritized suggestions with source attribution                         │
│  • critical_actions[] (red flags, immediate safety)                             │
│  • important_considerations[] (missing investigations, history gaps)            │
│  • nice_to_have[] (additional workup)                                           │
│  • psychosocial_recommendations[] (emotion/financial/compliance based)          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 0.5: MVP Enhancement (Current Sprint) ✅ IN PROGRESS
**Goal**: Enhance existing MVP with patient context awareness and feedback collection using EXISTING tables

This phase builds on the completed Phase 1 MVP by:
1. Pulling patient context from existing extraction segments
2. Adding triage suggestion logging (minimal new schema)
3. Adding optional feedback UI for doctors

#### 0.5.1 Database Schema (Minimal)
**Migration**: `20251215_add_triage_feedback.sql`

**Only 2 new tables needed** (patient context comes from existing segments):

```sql
-- Log all triage suggestions for analytics and learning
CREATE TABLE triage_suggestion_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id),
    doctor_id UUID REFERENCES doctors(id),
    suggestion_category TEXT NOT NULL,
    suggestion_type TEXT NOT NULL,
    suggestion_text TEXT NOT NULL,
    source_layer TEXT NOT NULL,
    confidence_score NUMERIC(3,2),
    priority_rank INTEGER,
    patient_context_applied JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Track doctor feedback on suggestions (optional)
CREATE TABLE triage_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suggestion_id UUID NOT NULL REFERENCES triage_suggestion_log(id),
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('accepted', 'rejected', 'modified')),
    rejection_reason TEXT,
    modified_text TEXT,
    feedback_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 0.5.2 Files to Modify/Create

| File | Action | Description |
|------|--------|-------------|
| `backend/services/triage/structured_insights.py` | Modify | Add `with_patient_history()` method |
| `backend/services/triage/triage_engine.py` | Modify | Add `generate_suggestions_v2()`, patient context filtering |
| `backend/routers/triage.py` | Modify | Add `/feedback` endpoint |
| `app/components/TriageSuggestionsModal.tsx` | Modify | Add optional feedback buttons |
| `supabase/migrations/20251215_add_triage_feedback.sql` | Create | 2 new tables + RPC function |

---

### Phase 1: Doctor History Layer
**Goal**: Learn from individual doctor's patterns
**Prerequisite**: Phase 0.5 (needs `triage_suggestion_log` and `triage_feedback` tables)

---

### Phase 2: Peer Intelligence Layer (Cross-Hospital, Same Specialty)
**Goal**: Leverage collective intelligence from same-specialty doctors across ALL hospitals
**Scope**: Cross-hospital (not limited to same hospital), filtered by specialty

---

### Phase 3: RAG Guidelines Layer
**Goal**: Evidence-based recommendations from 71 Indian medical society guidelines
**Source**: See `Docs/rag_sources_analysis.md` for complete guideline registry

---

### Phase 4: Multi-Layer Orchestrator + Synthesis
**Goal**: Integrate all layers with intelligent conflict resolution

---

### Phase 5: Evals, Guardrails & Production
**Goal**: Production-grade safety and monitoring

---

## Conflict Resolution Rules

| Rule | Description |
|------|-------------|
| **Patient Safety First** | Patient context contraindications ALWAYS override other layers |
| **Evidence Over Opinion** | Differential trees + RAG (evidence) > Doctor/Peer patterns when in conflict |
| **Doctor Preference for Ties** | Doctor history layer breaks ties when confidence is equal |
| **Confidence Aggregation** | Multi-layer agreement boosts confidence |
| **Layer Disable Respected** | If doctor disables a layer via preferences, skip it entirely |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Red flag recall | >95% |
| Suggestion acceptance rate | >70% |
| Critical coverage (must-not-miss) | 100% |
| P95 latency | <15s |
| Contraindication enforcement | 100% |

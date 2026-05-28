# Extraction Merge Feature - Implementation Plan

**Start Date**: 2025-11-19
**Status**: In Progress
**Current Phase**: Phase 1 - Database Schema

---

## Overview

Implementing AI-powered contextual merge feature to combine multiple medical extractions into a single consolidated output.

### Design Decisions
- **Output Type**: User selects target consultation type
- **Merge Strategy**: AI-powered contextual merge via Gemini
- **Conflict Resolution**: Latest extraction wins, AI validates and refines
- **Use Cases**: Follow-up consolidation, specialist integration, discharge enhancement, continuity of care

---

## Implementation Phases

### ✅ Phase 1: Database Schema (COMPLETED)
- [x] **Task 1.1**: Create migration 012 file ✅ 2025-11-19
  - File: `backend/supabase/migrations/012_extraction_merge.sql`
  - Created extraction_relationships table
  - Added merge tracking columns to medical_extractions
  - Added helper functions (get_merge_lineage, get_patient_extraction_timeline, validate_merge_sources)
  - Added indexes for performance
- [ ] **Task 1.2**: Run migration on development database
- [ ] **Task 1.3**: Verify migration with test queries

**Notes**: Migration includes comprehensive audit trail and validation functions.

---

### ⏳ Phase 2: Backend Service - Merge Orchestration (IN PROGRESS)
- [ ] **Task 2.1**: Create `backend/services/merge_service.py`
  - [ ] `validate_merge_request()` - Validate source extractions
  - [ ] `prepare_merge_context()` - Sort and prepare merge data
  - [ ] `generate_merge_prompt()` - Create AI merge prompt
  - [ ] `perform_ai_merge()` - Call Gemini for contextual merge
  - [ ] `save_merged_extraction()` - Save to database
  - [ ] Define merge prompt templates (SYSTEM, USER)
  - [ ] Add field-specific merge strategies
  - [ ] Add conflict resolution logic

- [ ] **Task 2.2**: Update `backend/services/segment_registry.py`
  - [ ] Add `generate_merge_artifacts()` function
  - [ ] Support target type schema generation
  - [ ] Always use 'full' mode for merge targets

- [ ] **Task 2.3**: Create `backend/models/merge_models.py`
  - [ ] `MergeRequest` - Request model
  - [ ] `MergePreviewResponse` - Preview response model
  - [ ] `MergeResponse` - Final merge response model
  - [ ] `MergeLineageResponse` - Lineage response model

**Status**: Not started
**Estimated Time**: 8-10 hours

---

### ⏸️ Phase 3: API Endpoints (PENDING)
- [ ] **Task 3.1**: Create `backend/routers/merge.py`
  - [ ] `POST /api/v1/extractions/merge` - Main merge endpoint
  - [ ] `POST /api/v1/extractions/merge/preview` - Preview before saving
  - [ ] `GET /api/v1/extractions/patient/{patient_id}/timeline` - Patient extraction timeline
  - [ ] `GET /api/v1/extractions/{extraction_id}/merge-info` - Merge lineage info

- [ ] **Task 3.2**: Update `backend/main.py`
  - [ ] Import merge router
  - [ ] Add merge router to app
  - [ ] Bump API version to 3.3.0
  - [ ] Update API documentation

- [ ] **Task 3.3**: Update `backend/services/supabase_service.py`
  - [ ] Add `get_patient_extractions()` function
  - [ ] Add `get_extraction_with_segments()` function
  - [ ] Add `save_extraction_relationships()` function
  - [ ] Add `get_merge_lineage()` function

**Status**: Not started
**Estimated Time**: 4-6 hours

---

### ⏸️ Phase 4: Frontend UI (PENDING)
- [ ] **Task 4.1**: Create `app/components/ExtractionMergeScreen.tsx`
  - [ ] Patient selector with search
  - [ ] Extraction timeline with checkboxes
  - [ ] Target consultation type selector
  - [ ] Preview button and preview panel
  - [ ] Confirm merge button
  - [ ] Merge lineage display
  - [ ] Loading states and error handling

- [ ] **Task 4.2**: Update `app/components/VHRScreen.tsx`
  - [ ] Add "Merge Extractions" button in header
  - [ ] Add merge badge for merged extractions
  - [ ] Add navigation to merge screen

- [ ] **Task 4.3**: Create `app/services/mergeService.ts`
  - [ ] API client functions for merge endpoints
  - [ ] Type definitions for merge requests/responses

- [ ] **Task 4.4**: Update `lib/types.ts`
  - [ ] Add merge-related TypeScript types
  - [ ] Add MergeRequest, MergeResponse interfaces

**Status**: Not started
**Estimated Time**: 8-10 hours

---

### ⏸️ Phase 5: Testing (PENDING)
- [ ] **Task 5.1**: Unit tests - `backend/tests/test_merge_service.py`
  - [ ] Test validate_merge_request()
  - [ ] Test prepare_merge_context()
  - [ ] Test generate_merge_prompt()
  - [ ] Test save_merged_extraction()

- [ ] **Task 5.2**: Integration tests
  - [ ] Test merge 2 OPs → OP
  - [ ] Test merge OP + DISCHARGE → DISCHARGE
  - [ ] Test merge OPTOMETRY + OPHTHALMOLOGY → OPHTHALMOLOGY
  - [ ] Test merge 3+ extractions
  - [ ] Test conflict resolution scenarios

- [ ] **Task 5.3**: Edge case tests
  - [ ] Merge extractions from different patients (should fail)
  - [ ] Merge single extraction (should fail)
  - [ ] Target type not supported (should fail)
  - [ ] AI merge timeout/failure

**Status**: Not started
**Estimated Time**: 6-8 hours

---

### ⏸️ Phase 6: Documentation (PENDING)
- [ ] **Task 6.1**: API documentation
  - [ ] Add merge endpoints to `/docs`
  - [ ] Add request/response examples
  - [ ] Add error codes and messages

- [ ] **Task 6.2**: User guide
  - [ ] Create `MERGE_FEATURE_USER_GUIDE.md`
  - [ ] Add screenshots of merge UI
  - [ ] Add common use case examples

- [ ] **Task 6.3**: Update project documentation
  - [ ] Update `.claude/CLAUDE.md` with merge feature
  - [ ] Update README.md
  - [ ] Update API version references

**Status**: Not started
**Estimated Time**: 2-3 hours

---

### ⏸️ Phase 7: Deployment (PENDING)
- [ ] **Task 7.1**: Run migration on staging database
- [ ] **Task 7.2**: Deploy backend to staging
- [ ] **Task 7.3**: Deploy frontend to staging
- [ ] **Task 7.4**: Beta test with sample data
- [ ] **Task 7.5**: Collect feedback and iterate
- [ ] **Task 7.6**: Deploy to production

**Status**: Not started
**Estimated Time**: 2-3 hours

---

## Progress Summary

| Phase | Status | Tasks Completed | Total Tasks | Progress |
|-------|--------|-----------------|-------------|----------|
| Phase 1: Database | ✅ In Progress | 1 | 3 | 33% |
| Phase 2: Backend Service | ⏸️ Pending | 0 | 11 | 0% |
| Phase 3: API Endpoints | ⏸️ Pending | 0 | 11 | 0% |
| Phase 4: Frontend UI | ⏸️ Pending | 0 | 12 | 0% |
| Phase 5: Testing | ⏸️ Pending | 0 | 12 | 0% |
| Phase 6: Documentation | ⏸️ Pending | 0 | 4 | 0% |
| Phase 7: Deployment | ⏸️ Pending | 0 | 6 | 0% |
| **OVERALL** | **In Progress** | **1** | **59** | **2%** |

---

## Key Implementation Details

### Merge Prompt Strategy

**System Prompt Principles:**
1. Chronological context awareness
2. Latest-wins for current state fields
3. Append mode for historical fields
4. Narrative synthesis for text fields
5. Conflict validation and resolution
6. Medication status tracking
7. Preserve clinical specificity

**Field-Specific Strategies:**
- **Medications**: Append all, mark discontinued vs new
- **Diagnosis**: Use latest, note changes in clinical_assessment
- **HPI/Hospital Course**: Chronological narrative synthesis
- **Vital Signs**: Use latest, note trends if significant
- **Investigations**: Append chronologically with timestamps

### Cross-Type Merge Examples

1. **OP + DISCHARGE → DISCHARGE**
   - Use admission/hospital details from DISCHARGE
   - Incorporate OP chief complaints as admission complaints
   - Merge medications from both
   - Use discharge follow-up, append OP follow-up if relevant

2. **OPTOMETRY + OPHTHALMOLOGY → OPHTHALMOLOGY**
   - Use optometry refraction measurements
   - Incorporate ophthalmology clinical findings
   - Merge both prescriptions (glasses + eye drops)

3. **Multiple OPs → OP**
   - Latest diagnosis is primary
   - Merge chief complaints (show progression)
   - Combine all prescriptions (mark discontinued)
   - Merge follow-up into single coherent plan

---

## Technical Decisions Log

### Decision 1: AI-Powered vs Rule-Based
**Date**: 2025-11-19
**Decision**: AI-powered contextual merge
**Rationale**:
- Rule-based too rigid for narrative fields (HPI, hospital course)
- AI can handle context and nuance
- Gemini 2.5 Pro has strong medical domain knowledge
- Latest-wins provides fallback for simple conflicts

### Decision 2: Target Type Selection
**Date**: 2025-11-19
**Decision**: User selects target consultation type
**Rationale**:
- Maximum flexibility (doctor decides output format)
- Supports superset and subset scenarios
- Avoids schema explosion from "MERGED" types
- Matches clinical workflow (doctor knows desired output)

### Decision 3: Database Structure
**Date**: 2025-11-19
**Decision**: Separate extraction_relationships table
**Rationale**:
- Clean separation of concerns
- Easy to query merge lineage
- Supports M:N relationships (if needed in future)
- Maintains audit trail

---

## Blockers and Risks

### Current Blockers
- None

### Potential Risks
1. **AI Merge Quality**: Gemini may produce inconsistent merges
   - **Mitigation**: Extensive prompt engineering + preview before save

2. **Large Extraction Merges**: 5+ extractions may exceed token limits
   - **Mitigation**: Add warning for 5+ extractions, suggest manual review

3. **Schema Mismatches**: Target type may not support all source fields
   - **Mitigation**: AI intelligently maps fields, drops unsupported fields with note

4. **Performance**: AI merge may take 20-40 seconds
   - **Mitigation**: Use Gemini 2.5 Flash for faster merges (configurable)

---

## Next Steps

**Immediate (Today)**:
1. ✅ Complete Task 1.1: Create migration file
2. ⏳ Complete Task 1.2: Run migration on development database
3. ⏳ Complete Task 1.3: Verify migration
4. ⏳ Start Task 2.1: Create merge_service.py

**This Week**:
- Complete Phase 2: Backend Service
- Complete Phase 3: API Endpoints
- Start Phase 4: Frontend UI

**Next Week**:
- Complete Phase 4: Frontend UI
- Complete Phase 5: Testing
- Complete Phase 6: Documentation
- Deploy to staging (Phase 7)

---

## Completion Criteria

### Phase 1: Database
- [x] Migration file created
- [ ] Migration runs without errors
- [ ] All tables and columns created
- [ ] All functions and indexes created
- [ ] Verification queries pass

### Phase 2: Backend Service
- [ ] All merge_service.py functions implemented
- [ ] segment_registry.py updated
- [ ] merge_models.py created
- [ ] Unit tests pass

### Phase 3: API Endpoints
- [ ] All merge endpoints implemented
- [ ] API documentation updated
- [ ] Integration tests pass

### Phase 4: Frontend UI
- [ ] ExtractionMergeScreen component complete
- [ ] VHRScreen updated with merge button
- [ ] mergeService.ts created
- [ ] Type definitions added

### Phase 5: Testing
- [ ] Unit tests pass (100% coverage)
- [ ] Integration tests pass
- [ ] Edge case tests pass
- [ ] Manual QA complete

### Phase 6: Documentation
- [ ] API docs updated
- [ ] User guide created
- [ ] Project docs updated

### Phase 7: Deployment
- [ ] Staging deployment successful
- [ ] Beta testing complete
- [ ] Production deployment successful

---

**Last Updated**: 2025-11-19 10:45 AM
**Next Update**: After completing Task 1.2 (Run migration)

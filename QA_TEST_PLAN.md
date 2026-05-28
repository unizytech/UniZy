# QA Test Plan - Template Sharing, Cloning & Auto-Activation Architecture

**Version**: 2.0 (Updated with Auto-Activation Tests)
**Date**: 2025-11-23
**Implementation Status**: 100% Complete
**Test Environment**: Development (localhost)
**New Features**:
- Auto-activation when admin shares templates with 'use' access
- Doctor activation directly from consultation types
- Soft-delete template conflict resolution
- DoctorTemplateConfigScreen UI changes

---

## Prerequisites

### Environment Setup
- [ ] Backend running: `./start-backend.sh` (http://localhost:8000)
- [ ] Frontend running: `npm run dev` (http://localhost:3000)
- [ ] Database migration applied: `20251123000000_cleanup_schema_and_add_doctor_templates.sql`
- [ ] Test data available (doctors, consultation types, templates)

### Test Data Requirements
- [ ] At least 3 test doctors with different specializations
- [ ] At least 2 hospitals with assigned doctors
- [ ] Common templates (doctor_id = NULL)
- [ ] Doctor-owned templates (doctor_id = UUID)
- [ ] All consultation types (OP, DISCHARGE, RESPIRATORY)

---

## 🎯 Featured Test Workflows (New)

### Critical Business Workflows
The following three workflows are **critical** for testing the complete segment and consultation type management system:

| Workflow | Test Cases | Complexity | Priority |
|----------|------------|------------|----------|
| **3.6: Segment Cloning & Assignment** | 18 steps | Medium | ⭐⭐⭐ Critical |
| **3.7: Segment Creation from Scratch** | 26 steps | High | ⭐⭐⭐ Critical |
| **3.8: Consultation Type Cloning with Visibility** | 56 steps | Very High | ⭐⭐⭐ Critical |

### Workflow 3.6: Segment Cloning & Assignment
**Purpose**: Verify admins can clone existing segments and assign them to doctor templates

**Key Validations**:
- Segment properties inherited from parent
- Assignment to specific doctor templates
- Segment appears in doctor's template configuration
- Doctor can customize cloned segment settings

### Workflow 3.7: Segment Creation from Scratch
**Purpose**: Verify complete segment lifecycle from creation to extraction

**Key Validations**:
- Custom segment code uniqueness
- JSON schema validation
- Default settings (category, brevity, terminology)
- Assignment and activation workflow
- Extraction includes custom segment data

### Workflow 3.8: Consultation Type Cloning with Visibility
**Purpose**: Verify consultation type visibility rules work correctly for all access patterns

**Key Validations**:
- 7 phases covering all visibility scenarios
- Hospital-specific visibility
- Specialization-specific visibility
- Doctor-specific visibility
- Mixed visibility (OR logic)
- Global visibility (no restrictions)
- Visibility matrix with 10 test combinations

**Visibility Scenarios Tested**:
1. ✅ Hospital-restricted types (only hospital members see it)
2. ✅ Specialization-restricted types (only matching specialization)
3. ✅ Doctor-specific types (only assigned doctors)
4. ✅ Mixed visibility (Hospital OR Specialization)
5. ✅ Global visibility (all doctors)
6. ❌ Negative tests (doctors without access cannot see type)

---

## Test Suite 1: Backend API Testing

### 1.1 Share Template with Individual Doctors
**Endpoint**: `POST /api/v1/doctor-templates/share`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-001 | Share template with single doctor (access_level: 'use') | Success response, shared_count = 1 | ⬜ |
| TC-BE-002 | Share template with multiple doctors (3 UUIDs) | Success response, shared_count = 3 | ⬜ |
| TC-BE-003 | Share template with access_level: 'view' | Success response, doctor can only view | ⬜ |
| TC-BE-004 | Share same template twice with same doctor | No duplicate entry, updates existing | ⬜ |
| TC-BE-005 | Share template with non-existent doctor_id | Partial failure, failures array populated | ⬜ |
| TC-BE-006 | Share template with invalid template_id | 404 error | ⬜ |
| TC-BE-007 | Share template without authentication | 401/403 error | ⬜ |

**API Documentation**: http://localhost:8000/docs#/Doctor%20Templates/share_template_api_v1_doctor_templates_share_post

---

### 1.1.1 Auto-Activation on Share (NEW)

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-AUTO-001 | Share template with access_level='use' | doctor_templates.is_active = true automatically | ⬜ |
| TC-BE-AUTO-002 | Share template with access_level='view' | doctor_templates.is_active = false (no auto-activation) | ⬜ |
| TC-BE-AUTO-003 | Upgrade access from 'view' to 'use' (re-share) | Auto-activates template (is_active updated to true) | ⬜ |
| TC-BE-AUTO-004 | Share with 'use' when doctor has another template active | Other template deactivated, new one activated | ⬜ |
| TC-BE-AUTO-005 | Bulk share with hospital (access_level='use') | All doctors have templates auto-activated | ⬜ |
| TC-BE-AUTO-006 | Share template where templates.is_active=false | 400 error: "template has been deactivated by admin" | ⬜ |
| TC-BE-AUTO-007 | Verify auto-activation logs | Backend logs contain "Auto-activated template..." | ⬜ |

---

### 1.2 Share Template with Hospital
**Endpoint**: `POST /api/v1/doctor-templates/share-hospital`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-011 | Share template with hospital (5 doctors) | shared_count = 5 | ⬜ |
| TC-BE-012 | Share template with hospital (no active doctors) | shared_count = 0 | ⬜ |
| TC-BE-013 | Share template with non-existent hospital_id | 404 error | ⬜ |
| TC-BE-014 | Share template with access_level: 'view' | All doctors get view-only access | ⬜ |

---

### 1.3 Share Template with Specialization
**Endpoint**: `POST /api/v1/doctor-templates/share-specialization`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-021 | Share template with "Cardiology" specialization | All cardiology doctors get access | ⬜ |
| TC-BE-022 | Share template with "Psychiatry" specialization | All psychiatry doctors get access | ⬜ |
| TC-BE-023 | Share template with non-existent specialization | shared_count = 0, success = true | ⬜ |
| TC-BE-024 | Share template with empty specialization | 400 error | ⬜ |

---

### 1.4 Activate Template for Doctor
**Endpoint**: `POST /api/v1/doctor-templates/activate`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-031 | Activate shared template (access_level: 'use') | Success, is_active = true | ⬜ |
| TC-BE-032 | Activate common template (auto-clone) | New cloned template created, owned by doctor | ⬜ |
| TC-BE-033 | Activate template when another is active | Previous template deactivated, new one activated | ⬜ |
| TC-BE-034 | Activate template with access_level: 'view' | 403 error (cannot activate view-only) | ⬜ |
| TC-BE-035 | Activate template not accessible to doctor | 403 error | ⬜ |
| TC-BE-036 | Activate template with custom_name | Cloned template has custom name | ⬜ |

---

### 1.5 Deactivate Template
**Endpoint**: `POST /api/v1/doctor-templates/deactivate`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-041 | Deactivate active template | is_active = false | ⬜ |
| TC-BE-042 | Deactivate already inactive template | Success (no-op) | ⬜ |
| TC-BE-043 | Deactivate template for wrong doctor | 404 error | ⬜ |

---

### 1.5.1 Activate from Consultation Type (NEW)
**Endpoint**: `POST /api/v1/doctor-templates/activate-from-consultation-type`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-ACTTYPE-001 | Activate from visible consultation type | New template created, owned by doctor, auto-activated | ⬜ |
| TC-BE-ACTTYPE-002 | Verify template code unique (timestamp-based) | template_code includes doctor name + timestamp | ⬜ |
| TC-BE-ACTTYPE-003 | Verify segments cloned from consultation_type_segments | All segments copied to template_segments | ⬜ |
| TC-BE-ACTTYPE-004 | Verify segment properties inherited | category, brevity_level, terminology_style cloned | ⬜ |
| TC-BE-ACTTYPE-005 | Activate from consultation type doctor doesn't have visibility to | 403 error: "does not have visibility to consultation type" | ⬜ |
| TC-BE-ACTTYPE-006 | Activate from non-existent consultation type | 404 error | ⬜ |
| TC-BE-ACTTYPE-007 | Activate multiple times from same consultation type | Each creates new unique template | ⬜ |
| TC-BE-ACTTYPE-008 | Verify new template deactivates old template of same type | Only one is_active=true per consultation_type | ⬜ |
| TC-BE-ACTTYPE-009 | Activate with custom template_name | Template created with custom name | ⬜ |
| TC-BE-ACTTYPE-010 | Activate without template_name | Default name: "{type_name} - {doctor_name}" | ⬜ |

---

### 1.6 Get Accessible Templates
**Endpoint**: `GET /api/v1/doctor-templates/accessible`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-051 | Get accessible templates (include_common: true) | Returns owned + shared + common | ⬜ |
| TC-BE-052 | Get accessible templates (include_common: false) | Returns owned + shared only | ⬜ |
| TC-BE-053 | Get accessible templates (filter by consultation_type) | Returns only matching type | ⬜ |
| TC-BE-054 | Get accessible templates (doctor has no access) | Empty templates array | ⬜ |
| TC-BE-055 | Verify ownership badges in response | Common/Owned/Shared correctly identified | ⬜ |

---

### 1.6.1 Soft-Delete Template Filtering (NEW)
**Endpoint**: `GET /api/v1/summary/templates?doctor_id={id}&filter_type=doctor`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-SOFTDEL-001 | Get templates for doctor (includes soft-deleted template) | Soft-deleted templates filtered out | ⬜ |
| TC-BE-SOFTDEL-002 | Verify filter checks templates.is_active=false | Filter applied even if doctor_templates.is_active=true | ⬜ |
| TC-BE-SOFTDEL-003 | Verify warning logged for conflict | Backend logs: "Skipping soft-deleted template..." | ⬜ |
| TC-BE-SOFTDEL-004 | Activate soft-deleted template (API call) | 400 error: "template has been deactivated by admin" | ⬜ |
| TC-BE-SOFTDEL-005 | Share soft-deleted template | 400 error: "Reactivate the template first before sharing" | ⬜ |
| TC-BE-SOFTDEL-006 | Clone soft-deleted template | 400 error: Cannot clone deactivated template | ⬜ |
| TC-BE-SOFTDEL-007 | Reactivate template (set is_active=true) | Template appears in doctor's template list again | ⬜ |

---

### 1.7 Revoke Template Access
**Endpoint**: `DELETE /api/v1/doctor-templates/revoke`

| Test Case | Input | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-BE-061 | Revoke access from doctor with shared template | Access removed, template no longer accessible | ⬜ |
| TC-BE-062 | Revoke access from doctor who owns template | 400 error (cannot revoke owner) | ⬜ |
| TC-BE-063 | Revoke access that doesn't exist | 404 error | ⬜ |

---

## Test Suite 2: Frontend Component Testing

### 2.1 TemplateSelector Component
**Location**: `app/components/TemplateSelector.tsx`

| Test Case | Expected Behavior | Status |
|-----------|-------------------|--------|
| TC-FE-001 | Component loads and displays accessible templates | ⬜ |
| TC-FE-002 | Ownership badges display correctly (Common/Owned/Shared) | ⬜ |
| TC-FE-003 | Active template shows ✓ Active indicator | ⬜ |
| TC-FE-004 | Access level displays (view/use) | ⬜ |
| TC-FE-005 | Template details card shows metadata | ⬜ |
| TC-FE-006 | "Activate Template" button disabled when already active | ⬜ |
| TC-FE-007 | Clone button appears only for non-owned templates | ⬜ |
| TC-FE-008 | Loading state displays spinner | ⬜ |
| TC-FE-009 | Error state displays error message | ⬜ |
| TC-FE-010 | No templates available shows empty state | ⬜ |

---

### 2.2 ShareTemplateModal Component
**Location**: `app/components/ShareTemplateModal.tsx`

| Test Case | Expected Behavior | Status |
|-----------|-------------------|--------|
| TC-FE-021 | Modal opens when "Share" button clicked | ⬜ |
| TC-FE-022 | Modal displays template name in header | ⬜ |
| TC-FE-023 | Three tabs visible: Individual/Hospital/Specialization | ⬜ |
| TC-FE-024 | Individual tab: textarea accepts doctor UUIDs (one per line) | ⬜ |
| TC-FE-025 | Hospital tab: input field accepts hospital UUID | ⬜ |
| TC-FE-026 | Specialization tab: dropdown shows 8 specializations | ⬜ |
| TC-FE-027 | Access level radio buttons: View/Use | ⬜ |
| TC-FE-028 | "Share Template" button triggers API call | ⬜ |
| TC-FE-029 | Success message displays with shared_count | ⬜ |
| TC-FE-030 | Error message displays on API failure | ⬜ |
| TC-FE-031 | "Currently Shared With" list displays existing shares | ⬜ |
| TC-FE-032 | "Revoke" button removes access | ⬜ |

---

### 2.3 DoctorTemplateConfigScreen Component
**Location**: `app/components/DoctorTemplateConfigScreen.tsx`

| Test Case | Expected Behavior | Status |
|-----------|-------------------|--------|
| TC-FE-041 | Doctor selector dropdown loads and displays doctors | ⬜ |
| TC-FE-042 | Consultation type selector shows OP/DISCHARGE/RESPIRATORY | ⬜ |
| TC-FE-043 | TemplateSelector component renders after selections | ⬜ |
| TC-FE-044 | Clone button creates "(My Copy)" template | ⬜ |
| TC-FE-045 | Cloned template becomes active automatically | ⬜ |
| TC-FE-046 | Segment lists show CORE/ADDITIONAL/EXCLUDED categories | ⬜ |
| TC-FE-047 | Drag-and-drop works between categories | ⬜ |
| TC-FE-048 | Drag-and-drop disabled for non-owned templates | ⬜ |
| TC-FE-049 | Warning message displays for read-only templates | ⬜ |
| TC-FE-050 | Segment configuration panel opens on segment click | ⬜ |
| TC-FE-051 | Brevity controls work (concise/balanced/detailed) | ⬜ |
| TC-FE-052 | Terminology controls work (medical/simple/as_spoken) | ⬜ |
| TC-FE-053 | Changes auto-save on update | ⬜ |
| TC-FE-054 | Success/error messages display appropriately | ⬜ |

---

### 2.4 TemplateAdminScreen Component
**Location**: `app/components/TemplateAdminScreen.tsx`

| Test Case | Expected Behavior | Status |
|-----------|-------------------|--------|
| TC-FE-061 | Template list displays all templates | ⬜ |
| TC-FE-062 | Ownership badges display (Common/Owned) | ⬜ |
| TC-FE-063 | "Share" button appears next to Edit/Delete | ⬜ |
| TC-FE-064 | "Share" button opens ShareTemplateModal | ⬜ |
| TC-FE-065 | Delete button disabled for common templates | ⬜ |
| TC-FE-066 | Edit button opens TemplateForm modal | ⬜ |
| TC-FE-067 | Create template button opens form | ⬜ |
| TC-FE-068 | Segment configuration tab loads segments | ⬜ |
| TC-FE-069 | Bulk clone panel allows cloning from parent types | ⬜ |

---

## Test Suite 3: End-to-End Workflows

### 3.1 Workflow: Admin Shares Template with Individual Doctor

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| 1 | Admin opens TemplateAdminScreen | Screen loads with template list | ⬜ |
| 2 | Admin clicks "Share" button on a template | ShareTemplateModal opens | ⬜ |
| 3 | Admin enters doctor UUID in Individual tab | UUID appears in textarea | ⬜ |
| 4 | Admin selects access_level: "Use" | Radio button selected | ⬜ |
| 5 | Admin clicks "Share Template" | Success message: "Shared with 1 doctor(s)" | ⬜ |
| 6 | Doctor opens DoctorTemplateConfigScreen | Shared template appears in TemplateSelector | ⬜ |
| 7 | Doctor selects shared template | Template details show "Shared" badge | ⬜ |
| 8 | Doctor clicks "Activate Template" | Template activates, checkmark appears | ⬜ |
| 9 | Doctor verifies segments loaded | CORE and ADDITIONAL segments visible | ⬜ |
| 10 | Doctor tries to edit segments | Warning: "Clone to customize" | ⬜ |

---

### 3.2 Workflow: Admin Shares Template with Hospital

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| 1 | Admin opens ShareTemplateModal | Modal opens | ⬜ |
| 2 | Admin switches to "By Hospital" tab | Hospital tab active | ⬜ |
| 3 | Admin enters hospital UUID | UUID appears in input | ⬜ |
| 4 | Admin selects access_level: "Use" | Radio button selected | ⬜ |
| 5 | Admin clicks "Share Template" | Success: "Shared with X doctors in hospital" | ⬜ |
| 6 | All hospital doctors see template | Template accessible in TemplateSelector | ⬜ |

---

### 3.3 Workflow: Doctor Clones and Customizes Template

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| 1 | Doctor selects common template | Template details show "Common" badge | ⬜ |
| 2 | Doctor clicks "Clone Template" | Cloning starts (loading state) | ⬜ |
| 3 | Clone completes | New template created: "Template Name (My Copy)" | ⬜ |
| 4 | Cloned template auto-activates | ✓ Active indicator appears | ⬜ |
| 5 | Cloned template owned by doctor | "Owned" badge displays | ⬜ |
| 6 | Doctor drags segment from CORE to ADDITIONAL | Segment moves, API call succeeds | ⬜ |
| 7 | Doctor changes segment brevity to "Concise" | Update succeeds, success message displays | ⬜ |
| 8 | Doctor changes terminology to "Simple Terms" | Update succeeds, success message displays | ⬜ |
| 9 | Doctor saves changes | All changes persisted to database | ⬜ |

---

### 3.4 Workflow: Template Activation Rules

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| 1 | Doctor has Template A active for OP | is_active = true for Template A | ⬜ |
| 2 | Doctor activates Template B for OP | Template A deactivated, Template B activated | ⬜ |
| 3 | Verify only one active template per type | Query shows only Template B active | ⬜ |
| 4 | Doctor activates template for DISCHARGE | OP template unaffected, DISCHARGE template active | ⬜ |

---

### 3.5 Workflow: Revoke Access

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| 1 | Admin opens ShareTemplateModal | "Currently Shared With" section shows doctors | ⬜ |
| 2 | Admin clicks "Revoke" on a doctor | Confirmation or immediate revoke | ⬜ |
| 3 | Access revoked successfully | Success message displays | ⬜ |
| 4 | Doctor no longer sees template | Template removed from accessible list | ⬜ |
| 5 | Doctor had activated template | Template deactivated automatically | ⬜ |

---

### 3.6 Workflow: Segment Creation via Cloning and Doctor Assignment

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| 1 | Admin opens TemplateAdminScreen → Segments tab | Segment list displays | ⬜ |
| 2 | Admin selects a segment to clone | Segment details shown | ⬜ |
| 3 | Admin clicks "Clone Segment" button | Clone segment modal/form opens | ⬜ |
| 4 | Admin enters new segment code (e.g., "CLONED_DIAGNOSIS") | Code entered in field | ⬜ |
| 5 | Admin enters new segment name | Name entered in field | ⬜ |
| 6 | Admin modifies prompt text for new segment | Prompt text updated | ⬜ |
| 7 | Admin saves cloned segment | Success: "Segment cloned successfully" | ⬜ |
| 8 | Verify segment appears in segment list | New segment visible with cloned properties | ⬜ |
| 9 | Admin assigns segment to specific doctor's template | Assignment modal opens | ⬜ |
| 10 | Admin selects doctor from dropdown | Doctor selected | ⬜ |
| 11 | Admin selects template for assignment | Template selected | ⬜ |
| 12 | Admin sets category (CORE/ADDITIONAL/EXCLUDED) | Category selected | ⬜ |
| 13 | Admin saves segment assignment | Success: "Segment assigned to doctor template" | ⬜ |
| 14 | Doctor opens DoctorTemplateConfigScreen | Doctor sees assigned template | ⬜ |
| 15 | Doctor activates template with new segment | Template activates successfully | ⬜ |
| 16 | Verify new cloned segment appears in category | Segment visible in correct category (CORE/ADDITIONAL/EXCLUDED) | ⬜ |
| 17 | Doctor configures cloned segment settings | Brevity/terminology controls work | ⬜ |
| 18 | Doctor uses template for extraction | Cloned segment data extracted correctly | ⬜ |

**Notes**:
- Cloned segment should inherit schema and prompt from parent
- Doctor should be able to customize cloned segment in their template
- Extraction should include cloned segment data

---

### 3.7 Workflow: Segment Creation from Scratch and Doctor Assignment

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| 1 | Admin opens TemplateAdminScreen → Segments tab | Segment list displays | ⬜ |
| 2 | Admin clicks "Create New Segment" button | Create segment form opens | ⬜ |
| 3 | Admin enters segment code (e.g., "CUSTOM_VITALS") | Code entered, validation passes | ⬜ |
| 4 | Admin enters segment name (e.g., "Custom Vital Signs") | Name entered | ⬜ |
| 5 | Admin writes custom prompt text | Prompt text entered in textarea | ⬜ |
| 6 | Admin defines JSON schema for segment | Schema JSON entered and validated | ⬜ |
| 7 | Admin sets default category (CORE/ADDITIONAL) | Category selected | ⬜ |
| 8 | Admin sets default brevity level (concise/balanced/detailed) | Brevity level selected | ⬜ |
| 9 | Admin sets default terminology style | Terminology style selected | ⬜ |
| 10 | Admin sets display order (numeric value) | Display order entered | ⬜ |
| 11 | Admin marks segment as required (checkbox) | Required checkbox checked/unchecked | ⬜ |
| 12 | Admin clicks "Create Segment" | Success: "Segment created successfully" | ⬜ |
| 13 | Verify segment appears in All Segments list | New segment visible with all properties | ⬜ |
| 14 | Admin assigns new segment to doctor's template | Assignment workflow starts | ⬜ |
| 15 | Admin selects target doctor | Doctor selected from dropdown | ⬜ |
| 16 | Admin selects target consultation type | Consultation type selected (OP/DISCHARGE/RESPIRATORY) | ⬜ |
| 17 | Admin selects target template | Template selected | ⬜ |
| 18 | Admin adds segment to template (category override optional) | Segment added to template | ⬜ |
| 19 | Admin saves assignment | Success: "Segment assigned to template" | ⬜ |
| 20 | Doctor opens DoctorTemplateConfigScreen | Doctor sees template with new segment | ⬜ |
| 21 | Doctor selects template with new segment | Template loads, new segment visible | ⬜ |
| 22 | Verify segment appears in assigned category | Segment in correct category with default settings | ⬜ |
| 23 | Doctor customizes segment (change brevity to concise) | Segment settings updated | ⬜ |
| 24 | Doctor drags segment to different category | Segment moves successfully | ⬜ |
| 25 | Doctor uses template for extraction with custom segment | Extraction includes custom segment data | ⬜ |
| 26 | Verify extracted data matches schema definition | JSON output conforms to schema | ⬜ |

**Validation Points**:
- Segment code must be unique
- JSON schema must be valid JSON
- Display order determines segment position in UI
- Required segments cannot be moved to EXCLUDED category
- Custom segments behave identically to built-in segments in extraction

---

### 3.8 Workflow: Consultation Type Creation via Cloning with Visibility Testing

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Clone Consultation Type** |
| 1 | Admin opens TemplateAdminScreen → Consultation Types view | Consultation types list displays (OP, DISCHARGE, RESPIRATORY) | ⬜ |
| 2 | Admin selects "OP" consultation type to clone | OP consultation type highlighted | ⬜ |
| 3 | Admin clicks "Clone Consultation Type" button | Clone modal opens with source type details | ⬜ |
| 4 | Admin enters new type code (e.g., "CARDIOLOGY") | Type code entered | ⬜ |
| 5 | Admin enters new type name (e.g., "Cardiology Consultation") | Type name entered | ⬜ |
| 6 | Admin enters description | Description text entered | ⬜ |
| 7 | Admin selects icon for new type | Icon selected from dropdown/picker | ⬜ |
| 8 | Admin selects color code for UI display | Color selected (e.g., #FF5733) | ⬜ |
| **Phase 2: Set Visibility Rules** |
| 9 | Admin configures visibility: "Hospital-Specific" | Visibility type selected | ⬜ |
| 10 | Admin selects target hospital UUID | Hospital selected from dropdown | ⬜ |
| 11 | Admin saves consultation type | Success: "Consultation type created" | ⬜ |
| 12 | Verify new type appears in consultation types list | CARDIOLOGY visible with hospital badge | ⬜ |
| 13 | Verify new type inherits all segments from OP | All OP segments cloned to CARDIOLOGY | ⬜ |
| 14 | Verify new type inherits all templates from OP | All OP templates available for CARDIOLOGY | ⬜ |
| **Phase 3: Visibility Testing - Hospital Access** |
| 15 | Doctor A (belongs to target hospital) logs in | Doctor A authenticated | ⬜ |
| 16 | Doctor A opens DoctorTemplateConfigScreen | Screen loads | ⬜ |
| 17 | Doctor A opens consultation type dropdown | Dropdown displays consultation types | ⬜ |
| 18 | Verify CARDIOLOGY appears in Doctor A's list | ✅ CARDIOLOGY visible | ⬜ |
| 19 | Doctor A selects CARDIOLOGY | Consultation type selected | ⬜ |
| 20 | Verify templates load for CARDIOLOGY | Templates display correctly | ⬜ |
| 21 | Doctor A activates a CARDIOLOGY template | Template activates successfully | ⬜ |
| 22 | Doctor B (different hospital) logs in | Doctor B authenticated | ⬜ |
| 23 | Doctor B opens consultation type dropdown | Dropdown displays consultation types | ⬜ |
| 24 | Verify CARDIOLOGY does NOT appear for Doctor B | ❌ CARDIOLOGY hidden (hospital restriction) | ⬜ |
| **Phase 4: Visibility Testing - Specialization Access** |
| 25 | Admin creates new consultation type: "PSYCH" | Cloned from OP | ⬜ |
| 26 | Admin sets visibility: "Specialization-Specific" | Visibility type selected | ⬜ |
| 27 | Admin selects specialization: "Psychiatry" | Specialization selected | ⬜ |
| 28 | Admin saves consultation type | Success: "Consultation type created" | ⬜ |
| 29 | Doctor C (specialization: Psychiatry) logs in | Doctor C authenticated | ⬜ |
| 30 | Doctor C opens consultation type dropdown | Dropdown displays | ⬜ |
| 31 | Verify PSYCH appears for Doctor C | ✅ PSYCH visible | ⬜ |
| 32 | Doctor C can activate PSYCH templates | Templates load and activate | ⬜ |
| 33 | Doctor D (specialization: Cardiology) logs in | Doctor D authenticated | ⬜ |
| 34 | Doctor D opens consultation type dropdown | Dropdown displays | ⬜ |
| 35 | Verify PSYCH does NOT appear for Doctor D | ❌ PSYCH hidden (specialization restriction) | ⬜ |
| **Phase 5: Visibility Testing - Individual Doctor Access** |
| 36 | Admin creates consultation type: "RESEARCH" | Cloned from DISCHARGE | ⬜ |
| 37 | Admin sets visibility: "Doctor-Specific" | Visibility type selected | ⬜ |
| 38 | Admin assigns to specific doctors (Doctor E, Doctor F UUIDs) | Doctors selected via multi-select | ⬜ |
| 39 | Admin saves consultation type | Success: "Consultation type created" | ⬜ |
| 40 | Doctor E logs in and opens dropdown | Dropdown displays | ⬜ |
| 41 | Verify RESEARCH appears for Doctor E | ✅ RESEARCH visible | ⬜ |
| 42 | Doctor F logs in and opens dropdown | Dropdown displays | ⬜ |
| 43 | Verify RESEARCH appears for Doctor F | ✅ RESEARCH visible | ⬜ |
| 44 | Doctor G (not assigned) logs in | Doctor G authenticated | ⬜ |
| 45 | Doctor G opens consultation type dropdown | Dropdown displays | ⬜ |
| 46 | Verify RESEARCH does NOT appear for Doctor G | ❌ RESEARCH hidden (not assigned) | ⬜ |
| **Phase 6: Mixed Visibility Testing** |
| 47 | Admin creates consultation type: "MULTI_VIS" | Cloned from OP | ⬜ |
| 48 | Admin sets visibility: Hospital + Specialization | Multiple visibility rules | ⬜ |
| 49 | Admin saves consultation type | Success | ⬜ |
| 50 | Test Doctor matches hospital OR specialization | ✅ MULTI_VIS visible (OR logic) | ⬜ |
| 51 | Test Doctor matches neither condition | ❌ MULTI_VIS hidden | ⬜ |
| **Phase 7: Global Visibility Testing** |
| 52 | Admin creates consultation type: "GLOBAL_TYPE" | Cloned from RESPIRATORY | ⬜ |
| 53 | Admin sets visibility: "All Doctors" (no restrictions) | No visibility filters applied | ⬜ |
| 54 | Admin saves consultation type | Success | ⬜ |
| 55 | Any doctor logs in | Doctor authenticated | ⬜ |
| 56 | Verify GLOBAL_TYPE appears for all doctors | ✅ GLOBAL_TYPE visible universally | ⬜ |

**Visibility Matrix to Test**:

| Consultation Type | Visibility Rule | Doctor Profile | Should Be Visible? |
|-------------------|-----------------|----------------|-------------------|
| CARDIOLOGY | Hospital A | Doctor in Hospital A | ✅ Yes |
| CARDIOLOGY | Hospital A | Doctor in Hospital B | ❌ No |
| PSYCH | Specialization: Psychiatry | Psychiatrist | ✅ Yes |
| PSYCH | Specialization: Psychiatry | Cardiologist | ❌ No |
| RESEARCH | Doctor-Specific (E, F) | Doctor E | ✅ Yes |
| RESEARCH | Doctor-Specific (E, F) | Doctor G | ❌ No |
| MULTI_VIS | Hospital A OR Psychiatry | Hospital A doctor | ✅ Yes |
| MULTI_VIS | Hospital A OR Psychiatry | Psychiatrist in Hospital B | ✅ Yes |
| MULTI_VIS | Hospital A OR Psychiatry | Cardiologist in Hospital B | ❌ No |
| GLOBAL_TYPE | No restrictions | Any doctor | ✅ Yes |

**API Validation**:
- Verify `specialty_applicable` field correctly filters visibility
- Verify `hospital_id` field enforces hospital restrictions
- Verify `doctor_assignments` junction table for doctor-specific access
- Verify consultation type list API respects visibility rules

**Database Queries for Verification**:
```sql
-- TC-CT-001: Verify consultation type cloned with all segments
SELECT ct.type_code, COUNT(s.id) as segment_count
FROM consultation_types ct
LEFT JOIN consultation_type_segments cts ON ct.id = cts.consultation_type_id
LEFT JOIN segments s ON cts.segment_id = s.id
WHERE ct.type_code = 'CARDIOLOGY'
GROUP BY ct.type_code;
-- Expected: Same segment count as source OP type

-- TC-CT-002: Verify visibility rules stored correctly
SELECT type_code, specialty_applicable, hospital_id, is_global
FROM consultation_types
WHERE type_code IN ('CARDIOLOGY', 'PSYCH', 'RESEARCH', 'GLOBAL_TYPE');

-- TC-CT-003: Verify doctor-specific assignments
SELECT ct.type_code, COUNT(dct.doctor_id) as assigned_doctors
FROM consultation_types ct
LEFT JOIN doctor_consultation_types dct ON ct.id = dct.consultation_type_id
WHERE ct.type_code = 'RESEARCH'
GROUP BY ct.type_code;
-- Expected: 2 assigned doctors
```

---

### 3.9 Workflow: Consultation Type Creation from Scratch with Bulk Segment Assignment

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Create Empty Consultation Type** |
| 1 | Admin opens TemplateAdminScreen → Consultation Types | Consultation types list displays | ⬜ |
| 2 | Admin clicks "Create New Consultation Type" button | Create form opens | ⬜ |
| 3 | Admin enters type code (e.g., "DERMATOLOGY") | Code entered, validation passes | ⬜ |
| 4 | Admin enters type name (e.g., "Dermatology Consultation") | Name entered | ⬜ |
| 5 | Admin enters description | Description text entered | ⬜ |
| 6 | Admin selects icon for type | Icon selected from picker | ⬜ |
| 7 | Admin selects color code | Color selected (e.g., #FFA500) | ⬜ |
| 8 | Admin sets visibility: "All Doctors" | Visibility configured | ⬜ |
| 9 | Admin sets display order: 4 | Display order entered | ⬜ |
| 10 | Admin marks as active | is_active checkbox checked | ⬜ |
| 11 | Admin saves WITHOUT selecting segments | Success: "Consultation type created with 0 segments" | ⬜ |
| 12 | Verify new type appears in list | DERMATOLOGY visible with "0 segments" badge | ⬜ |
| **Phase 2: Bulk Assign Segments** |
| 13 | Admin selects DERMATOLOGY type | Type details displayed | ⬜ |
| 14 | Admin clicks "Manage Segments" button | Segment assignment interface opens | ⬜ |
| 15 | Admin views available segments list | All segment definitions displayed (50+ segments) | ⬜ |
| 16 | Admin uses "Bulk Assign from Parent" option | Parent type selector appears | ⬜ |
| 17 | Admin selects parent type: "OP" | OP selected, shows 18 segments | ⬜ |
| 18 | Admin clicks "Clone All Segments" | Confirmation dialog appears | ⬜ |
| 19 | Admin confirms bulk assignment | Progress indicator shows | ⬜ |
| 20 | Wait for bulk assignment to complete | Success: "18 segments assigned to DERMATOLOGY" | ⬜ |
| 21 | Verify segment count updated | DERMATOLOGY now shows "18 segments" | ⬜ |
| **Phase 3: Selective Segment Addition** |
| 22 | Admin clicks "Add Individual Segments" | Segment search/select interface opens | ⬜ |
| 23 | Admin searches for "SKIN" segment | Search filters segment list | ⬜ |
| 24 | Admin selects custom "SKIN_EXAMINATION" segment | Segment selected | ⬜ |
| 25 | Admin sets category for new segment: CORE | Category selected | ⬜ |
| 26 | Admin sets display order: 5 | Display order entered | ⬜ |
| 27 | Admin clicks "Add Segment" | Success: "Segment added" | ⬜ |
| 28 | Verify segment count: 19 segments | Count updated correctly | ⬜ |
| **Phase 4: Segment Removal** |
| 29 | Admin selects segment to remove (e.g., "PROTOCOL") | Segment highlighted | ⬜ |
| 30 | Admin clicks "Remove from Type" | Confirmation dialog appears | ⬜ |
| 31 | Admin confirms removal | Success: "Segment removed" | ⬜ |
| 32 | Verify segment count: 18 segments | Count decremented | ⬜ |
| **Phase 5: Verify Templates Inherit Segments** |
| 33 | Admin creates new template for DERMATOLOGY | Template creation form opens | ⬜ |
| 34 | Admin names template: "DERM_BASIC" | Template name entered | ⬜ |
| 35 | Admin saves template | Success: "Template created" | ⬜ |
| 36 | Admin opens template segment configuration | Template segments loaded | ⬜ |
| 37 | Verify template has all 18 DERMATOLOGY segments | All segments inherited correctly | ⬜ |
| 38 | Verify SKIN_EXAMINATION segment included | Custom segment present | ⬜ |
| 39 | Verify PROTOCOL segment excluded | Removed segment not present | ⬜ |

**Validation Points**:
- Empty consultation types can be created
- Bulk segment assignment from parent types works
- Individual segment addition works
- Segment removal works
- Templates inherit segment configuration from consultation type
- Segment count updates correctly after all operations

**Database Queries**:
```sql
-- Verify consultation type created with correct segment count
SELECT ct.type_code, COUNT(cts.segment_id) as segment_count
FROM consultation_types ct
LEFT JOIN consultation_type_segments cts ON ct.id = cts.consultation_type_id
WHERE ct.type_code = 'DERMATOLOGY'
GROUP BY ct.type_code;
-- Expected: 18 segments
```

---

### 3.10 Workflow: Admin Creates Template and Assigns to All Doctors (Global Template)

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Create Global Template** |
| 1 | Admin opens TemplateAdminScreen | Screen loads | ⬜ |
| 2 | Admin selects consultation type: OP | OP selected | ⬜ |
| 3 | Admin clicks "Create Template" button | Template form opens | ⬜ |
| 4 | Admin enters template code: "GLOBAL_OP_V1" | Code entered | ⬜ |
| 5 | Admin enters template name: "Standard OP Template v1" | Name entered | ⬜ |
| 6 | Admin enters description: "Global template for all doctors" | Description entered | ⬜ |
| 7 | Admin leaves doctor_id field EMPTY (NULL) | doctor_id = NULL (common template) | ⬜ |
| 8 | Admin sets is_default: true | Default checkbox checked | ⬜ |
| 9 | Admin sets use_case: "Standard outpatient consultation" | Use case entered | ⬜ |
| 10 | Admin sets estimated time: 45 seconds | Estimated time entered | ⬜ |
| 11 | Admin clicks "Save Template" | Success: "Global template created" | ⬜ |
| 12 | Verify template in list with "Common" badge | Template visible, doctor_id = NULL | ⬜ |
| **Phase 2: Configure Template Segments** |
| 13 | Admin clicks "Configure Segments" on new template | Segment configuration opens | ⬜ |
| 14 | Admin sets 8 segments to CORE category | CORE segments configured | ⬜ |
| 15 | Admin sets 10 segments to ADDITIONAL category | ADDITIONAL segments configured | ⬜ |
| 16 | Admin sets brevity levels (mix of concise/balanced) | Brevity configured per segment | ⬜ |
| 17 | Admin saves segment configuration | Success: "Template configuration saved" | ⬜ |
| **Phase 3: Auto-Share with All Doctors** |
| 18 | Admin clicks "Share with All Doctors" button | Confirmation dialog appears | ⬜ |
| 19 | Admin selects access_level: "Use" | Access level selected | ⬜ |
| 20 | Admin confirms share operation | Progress indicator shows | ⬜ |
| 21 | Wait for sharing to complete | Success: "Shared with 50 doctors" (example) | ⬜ |
| 22 | Verify sharing records created | doctor_templates junction table populated | ⬜ |
| **Phase 4: Doctor A - Sees and Selects Template** |
| 23 | Doctor A opens VHR Screen | VHR screen loads | ⬜ |
| 24 | Doctor A selects consultation type: OP | OP selected | ⬜ |
| 25 | Doctor A opens template dropdown | Template list displays | ⬜ |
| 26 | Verify "Standard OP Template v1" appears | ✅ Template visible with "Common" badge | ⬜ |
| 27 | Doctor A selects template | Template selected | ⬜ |
| 28 | Doctor A clicks "Start Recording" button | Recording starts | ⬜ |
| 29 | Verify recording uses selected template | Template_id stored in session metadata | ⬜ |
| 30 | Doctor A completes recording | Recording saved | ⬜ |
| 31 | Doctor A triggers extraction | Extraction starts with selected template | ⬜ |
| 32 | Verify extraction uses template's segment config | CORE + ADDITIONAL segments extracted | ⬜ |
| 33 | Verify extraction results match template schema | All configured segments present | ⬜ |
| **Phase 5: Doctor B - Different Hospital/Specialization** |
| 34 | Doctor B logs in (different hospital) | Doctor B authenticated | ⬜ |
| 35 | Doctor B opens VHR Screen | VHR screen loads | ⬜ |
| 36 | Doctor B selects consultation type: OP | OP selected | ⬜ |
| 37 | Verify "Standard OP Template v1" also appears | ✅ Global template visible to all | ⬜ |
| 38 | Doctor B can select and use template | Template selectable | ⬜ |
| 39 | Doctor B starts recording with template | Recording starts successfully | ⬜ |
| 40 | Verify extraction uses same template config | Same segment configuration applied | ⬜ |
| **Phase 6: Verify Template Selection in Recording Session** |
| 41 | Admin queries recording_sessions table | Database query executed | ⬜ |
| 42 | Verify template_id field populated | template_id = GLOBAL_OP_V1 | ⬜ |
| 43 | Verify extraction_results linked to template | extraction.template_id matches | ⬜ |

**Critical Validations**:
- Common templates (doctor_id = NULL) visible to all doctors
- Template selection persisted in recording session
- Template configuration applied during extraction
- Multiple doctors can use same global template
- Recording metadata tracks which template was used

**Database Queries**:
```sql
-- Verify template is common (not doctor-owned)
SELECT template_code, template_name, doctor_id, is_default
FROM templates
WHERE template_code = 'GLOBAL_OP_V1';
-- Expected: doctor_id = NULL

-- Verify all doctors have access
SELECT COUNT(DISTINCT doctor_id) as doctors_with_access
FROM doctor_templates
WHERE template_id = (SELECT id FROM templates WHERE template_code = 'GLOBAL_OP_V1');
-- Expected: All active doctors count

-- Verify recording sessions use template
SELECT rs.id, rs.template_id, t.template_name
FROM recording_sessions rs
JOIN templates t ON rs.template_id = t.id
WHERE t.template_code = 'GLOBAL_OP_V1'
LIMIT 5;
-- Expected: Multiple sessions using this template
```

---

### 3.11 Workflow: Doctors Inherit and Activate Consultation Types Before Recording

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Admin Creates Consultation Type with Visibility** |
| 1 | Admin creates consultation type: "CARDIO_ADVANCED" | Type created | ⬜ |
| 2 | Admin sets visibility: Specialization = "Cardiology" | Visibility rule configured | ⬜ |
| 3 | Admin assigns 15 segments to type | Segments assigned | ⬜ |
| 4 | Admin creates default template for type | Template created | ⬜ |
| 5 | Admin marks template as default | is_default = true | ⬜ |
| **Phase 2: Cardiologist Doctor Logs In** |
| 6 | Doctor C (Cardiologist) logs in | Authenticated | ⬜ |
| 7 | Doctor C opens VHR Screen | VHR screen loads | ⬜ |
| 8 | Doctor C opens consultation type dropdown | Dropdown displays | ⬜ |
| 9 | Verify CARDIO_ADVANCED appears | ✅ Visible (matches specialization) | ⬜ |
| 10 | Doctor C selects CARDIO_ADVANCED | Type selected | ⬜ |
| **Phase 3: Doctor Activates Default Template** |
| 11 | System auto-loads default template for type | Default template pre-selected | ⬜ |
| 12 | Doctor C clicks "Activate Template" | Activation starts | ⬜ |
| 13 | System auto-clones template for doctor | New template created, doctor_id set | ⬜ |
| 14 | Verify cloned template owned by Doctor C | Template in doctor's owned list | ⬜ |
| 15 | Verify cloned template marked active | is_active = true | ⬜ |
| 16 | Verify only one active template per type | Previous templates deactivated | ⬜ |
| **Phase 4: Doctor Starts Recording with Inherited Type** |
| 17 | Doctor C stays on VHR screen | Screen still loaded | ⬜ |
| 18 | Doctor C verifies CARDIO_ADVANCED selected | Consultation type confirmed | ⬜ |
| 19 | Doctor C verifies activated template selected | Template shown as active | ⬜ |
| 20 | Doctor C clicks "Start Recording" | Recording starts | ⬜ |
| 21 | Verify recording session created | Session in database | ⬜ |
| 22 | Verify session metadata includes consultation_type_id | consultation_type_id = CARDIO_ADVANCED | ⬜ |
| 23 | Verify session metadata includes template_id | template_id = cloned template | ⬜ |
| 24 | Doctor C records audio (1 minute) | Audio chunks uploaded | ⬜ |
| 25 | Doctor C stops recording | Recording stopped | ⬜ |
| **Phase 5: Extraction Uses Inherited Configuration** |
| 26 | System triggers extraction | Extraction process starts | ⬜ |
| 27 | Verify extraction uses CARDIO_ADVANCED segments | 15 segments loaded | ⬜ |
| 28 | Verify extraction uses doctor's template config | Custom brevity/terminology applied | ⬜ |
| 29 | Extraction completes successfully | Results saved | ⬜ |
| 30 | Verify extracted data has all 15 segments | All segments extracted | ⬜ |
| 31 | Doctor C views extraction results | Results displayed in UI | ⬜ |
| 32 | Verify segment data follows template configuration | CORE segments listed first | ⬜ |
| **Phase 6: Non-Cardiologist Cannot See Type** |
| 33 | Doctor G (General Practice) logs in | Authenticated | ⬜ |
| 34 | Doctor G opens VHR Screen | VHR screen loads | ⬜ |
| 35 | Doctor G opens consultation type dropdown | Dropdown displays | ⬜ |
| 36 | Verify CARDIO_ADVANCED NOT visible | ❌ Hidden (specialization mismatch) | ⬜ |
| 37 | Doctor G can only see allowed types | Only OP, DISCHARGE, RESPIRATORY visible | ⬜ |

**Critical Validations**:
- Inherited consultation types respect visibility rules
- Default templates auto-activate on first use
- Auto-cloning creates doctor-owned copy
- Recording sessions track consultation type and template
- Extraction uses correct segment configuration
- Non-authorized doctors cannot access restricted types

---

### 3.12 Workflow: Doctor Clones Template and Uses for Recording

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Doctor Discovers Shared Template** |
| 1 | Doctor D logs in | Authenticated | ⬜ |
| 2 | Doctor D opens DoctorTemplateConfigScreen | Screen loads | ⬜ |
| 3 | Doctor D selects consultation type: OP | OP selected | ⬜ |
| 4 | TemplateSelector loads accessible templates | List displays: owned, shared, common | ⬜ |
| 5 | Doctor D sees shared template: "Expert OP Template" | Template visible with "Shared" badge | ⬜ |
| 6 | Doctor D reviews template details | Template metadata displayed | ⬜ |
| 7 | Doctor D sees "access_level: view" | Read-only template | ⬜ |
| 8 | Doctor D sees "Clone Template" button | Button visible for non-owned templates | ⬜ |
| **Phase 2: Clone Template** |
| 9 | Doctor D clicks "Clone Template" | Cloning process starts | ⬜ |
| 10 | System creates new template | Template cloned | ⬜ |
| 11 | System sets name: "Expert OP Template (My Copy)" | Auto-named with suffix | ⬜ |
| 12 | System sets doctor_id = Doctor D | Ownership assigned | ⬜ |
| 13 | System copies all segment configurations | All segments cloned with settings | ⬜ |
| 14 | System marks cloned template as active | is_active = true | ⬜ |
| 15 | Success message: "Template cloned successfully" | Confirmation displayed | ⬜ |
| 16 | TemplateSelector refreshes list | Cloned template now in "Owned" section | ⬜ |
| **Phase 3: Customize Cloned Template** |
| 17 | Doctor D sees owned template highlighted | Template shows "Owned" badge | ⬜ |
| 18 | Doctor D opens segment configuration | Segment lists load (CORE, ADDITIONAL, EXCLUDED) | ⬜ |
| 19 | Doctor D drags segment from ADDITIONAL to CORE | Segment moves successfully | ⬜ |
| 20 | System updates segment category | API call succeeds | ⬜ |
| 21 | Doctor D changes segment brevity to "Concise" | Brevity updated | ⬜ |
| 22 | Doctor D changes terminology to "Simple Terms" | Terminology updated | ⬜ |
| 23 | Doctor D saves all changes | Success: "Template updated" | ⬜ |
| 24 | Verify customizations persisted | Database reflects changes | ⬜ |
| **Phase 4: Use Cloned Template for Recording** |
| 25 | Doctor D navigates to VHR Screen | VHR screen loads | ⬜ |
| 26 | Doctor D selects consultation type: OP | OP selected | ⬜ |
| 27 | Template dropdown auto-shows active template | "Expert OP Template (My Copy)" pre-selected | ⬜ |
| 28 | Verify template shows "✓ Active" indicator | Active status visible | ⬜ |
| 29 | Doctor D clicks "Start Recording" | Recording starts | ⬜ |
| 30 | Doctor D records consultation (2 minutes) | Audio chunks uploaded | ⬜ |
| 31 | Doctor D stops recording | Recording stopped | ⬜ |
| 32 | System stitches audio chunks | Full audio created | ⬜ |
| **Phase 5: Extraction with Customized Template** |
| 33 | System triggers extraction | Extraction starts | ⬜ |
| 34 | Verify extraction loads template_id | Cloned template ID used | ⬜ |
| 35 | Verify extraction loads custom segment config | Modified categories loaded | ⬜ |
| 36 | Verify CORE includes customized segment | Moved segment appears in CORE | ⬜ |
| 37 | Verify brevity modifier applied | "Concise" prompts used | ⬜ |
| 38 | Verify terminology modifier applied | "Simple Terms" prompts used | ⬜ |
| 39 | Extraction completes | Results saved | ⬜ |
| 40 | Doctor D views extraction results | Results displayed | ⬜ |
| 41 | Verify segments match custom configuration | Custom CORE segments listed first | ⬜ |
| 42 | Verify output uses simple terminology | Medical jargon minimized | ⬜ |
| 43 | Verify output is concise (not verbose) | Shorter responses per segment | ⬜ |
| **Phase 6: Verify Original Template Unchanged** |
| 44 | Admin views "Expert OP Template" (original) | Original template loaded | ⬜ |
| 45 | Verify original segment configuration intact | No changes to source template | ⬜ |
| 46 | Other doctors still see original template | Shared template unchanged | ⬜ |

**Critical Validations**:
- Clone creates independent copy
- Doctor owns cloned template (can edit)
- Customizations don't affect source template
- Active template used automatically in recording
- Extraction applies custom segment configuration
- Brevity and terminology modifiers work correctly

**Database Queries**:
```sql
-- Verify cloned template exists and is owned
SELECT template_code, template_name, doctor_id, is_active
FROM templates
WHERE template_name LIKE '%My Copy%' AND doctor_id = 'DOCTOR_D_UUID';

-- Verify segment configuration customizations
SELECT ts.segment_code, ts.category, ts.brevity_level, ts.terminology_style
FROM template_segments ts
JOIN templates t ON ts.template_id = t.id
WHERE t.template_name = 'Expert OP Template (My Copy)';

-- Verify recording session uses cloned template
SELECT rs.id, rs.template_id, t.template_name
FROM recording_sessions rs
JOIN templates t ON rs.template_id = t.id
WHERE rs.doctor_id = 'DOCTOR_D_UUID'
ORDER BY rs.created_at DESC
LIMIT 1;
```

---

### 3.13 Workflow: Segment Master Changes Propagate to All Templates and Types

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Setup - Templates Using Segment** |
| 1 | Admin verifies segment "DIAGNOSIS" exists | Segment exists in segment_definitions | ⬜ |
| 2 | Verify DIAGNOSIS used in 5 templates | Query returns 5 template assignments | ⬜ |
| 3 | Verify DIAGNOSIS used in 3 consultation types | Query returns 3 type assignments | ⬜ |
| 4 | Doctor A has activated template with DIAGNOSIS | Template active for Doctor A | ⬜ |
| 5 | Doctor B has activated different template with DIAGNOSIS | Template active for Doctor B | ⬜ |
| **Phase 2: Admin Modifies Segment Master - Prompt Text** |
| 6 | Admin opens TemplateAdminScreen → Segments | Segment list displays | ⬜ |
| 7 | Admin selects DIAGNOSIS segment | Segment details shown | ⬜ |
| 8 | Admin clicks "Edit Segment" | Edit form opens | ⬜ |
| 9 | Admin views current prompt text (500 words) | Current prompt displayed | ⬜ |
| 10 | Admin modifies prompt text - adds ICD-10 requirement | New text: "...include ICD-10 codes..." | ⬜ |
| 11 | Admin marks change as "Propagate to All" | Checkbox checked | ⬜ |
| 12 | Admin saves segment changes | Confirmation: "Update all templates?" | ⬜ |
| 13 | Admin confirms propagation | Success: "Segment updated in master + 5 templates" | ⬜ |
| **Phase 3: Verify Template Inheritance - Real-time** |
| 14 | Admin opens Template 1 segment configuration | Template segments load | ⬜ |
| 15 | Admin views DIAGNOSIS segment prompt | Prompt includes "ICD-10 codes" ✅ | ⬜ |
| 16 | Admin opens Template 2 segment configuration | Template segments load | ⬜ |
| 17 | Verify DIAGNOSIS prompt updated | Prompt includes "ICD-10 codes" ✅ | ⬜ |
| 18 | Verify all 5 templates updated | All templates reflect change | ⬜ |
| **Phase 4: Verify Consultation Type Inheritance** |
| 19 | Admin selects consultation type: OP | OP type selected | ⬜ |
| 20 | Admin views DIAGNOSIS segment in OP type | Segment configuration displayed | ⬜ |
| 21 | Verify prompt text updated | Prompt includes "ICD-10 codes" ✅ | ⬜ |
| 22 | Admin selects consultation type: CARDIOLOGY | CARDIOLOGY selected | ⬜ |
| 23 | Verify DIAGNOSIS prompt updated | Prompt includes "ICD-10 codes" ✅ | ⬜ |
| **Phase 5: Doctor A Records with Updated Template** |
| 24 | Doctor A opens VHR Screen (next day) | Screen loads | ⬜ |
| 25 | Doctor A starts new recording | Recording starts | ⬜ |
| 26 | Doctor A completes recording | Recording saved | ⬜ |
| 27 | System triggers extraction | Extraction starts | ⬜ |
| 28 | Verify extraction uses updated DIAGNOSIS prompt | Updated prompt sent to AI | ⬜ |
| 29 | Extraction completes | Results returned | ⬜ |
| 30 | Verify DIAGNOSIS output includes ICD-10 codes | Output: "Primary: Major Depression (F32.1)" ✅ | ⬜ |
| **Phase 6: Admin Modifies Segment Master - JSON Schema** |
| 31 | Admin edits DIAGNOSIS segment again | Edit form opens | ⬜ |
| 32 | Admin views current JSON schema | Schema displayed (object with fields) | ⬜ |
| 33 | Admin adds new field: "icd10_code" (string, required) | Schema modified | ⬜ |
| 34 | Admin marks as "Propagate to All" | Checkbox checked | ⬜ |
| 35 | Admin saves changes | Confirmation dialog | ⬜ |
| 36 | Admin confirms propagation | Success: "Schema updated in master + 5 templates" | ⬜ |
| **Phase 7: Verify Schema Changes Propagate** |
| 37 | Admin opens Template 1 → DIAGNOSIS schema | Schema viewer opens | ⬜ |
| 38 | Verify schema includes "icd10_code" field | Field present, type: string ✅ | ⬜ |
| 39 | Admin opens Template 3 → DIAGNOSIS schema | Schema viewer opens | ⬜ |
| 40 | Verify schema updated | Field present ✅ | ⬜ |
| **Phase 8: Doctor B Records with Updated Schema** |
| 41 | Doctor B starts new recording | Recording starts | ⬜ |
| 42 | Doctor B completes recording | Recording saved | ⬜ |
| 43 | System triggers extraction | Extraction starts | ⬜ |
| 44 | Verify extraction uses updated schema | Updated schema in system prompt | ⬜ |
| 45 | Extraction completes | Results returned | ⬜ |
| 46 | Verify DIAGNOSIS JSON includes "icd10_code" field | Output: {"diagnosis": "...", "icd10_code": "F32.1"} ✅ | ⬜ |
| 47 | Verify schema validation passes | No JSON validation errors | ⬜ |
| **Phase 9: Verify Historical Records Unchanged** |
| 48 | Admin queries old extraction (before change) | Old extraction loaded | ⬜ |
| 49 | Verify old extraction uses old prompt | Original prompt in metadata | ⬜ |
| 50 | Verify old extraction uses old schema | No "icd10_code" field (backward compatible) | ⬜ |
| 51 | Confirm historical data integrity preserved | Old extractions unchanged ✅ | ⬜ |
| **Phase 10: Opt-out Templates (Custom Override)** |
| 52 | Doctor C has template with custom DIAGNOSIS override | Custom prompt set | ⬜ |
| 53 | Admin makes segment master change | Change saved | ⬜ |
| 54 | Verify Doctor C's template NOT updated | Custom override preserved ✅ | ⬜ |
| 55 | Doctor C's extraction uses custom prompt | Original custom prompt used | ⬜ |

**Propagation Rules**:
- ✅ Master segment changes propagate to all templates by default
- ✅ Changes apply to future extractions only (historical data preserved)
- ✅ Templates with custom overrides are NOT updated (opt-out)
- ✅ Both prompt text and JSON schema changes propagate
- ✅ Propagation happens immediately (no delay)
- ✅ Consultation types inherit updated segments

**Critical Validations**:
- Segment master is single source of truth
- Changes propagate to all dependent templates and types
- Extraction uses latest segment definition
- Historical extractions remain unchanged
- Custom template overrides respected
- JSON schema validation enforces new fields

**Database Queries**:
```sql
-- Verify segment master updated
SELECT segment_code, prompt_section_text, schema_definition_json, updated_at
FROM segment_definitions
WHERE segment_code = 'DIAGNOSIS';

-- Count templates using this segment
SELECT COUNT(DISTINCT template_id) as template_count
FROM template_segments
WHERE segment_code = 'DIAGNOSIS';

-- Verify all templates updated (check timestamp)
SELECT t.template_name, ts.updated_at
FROM template_segments ts
JOIN templates t ON ts.template_id = t.id
WHERE ts.segment_code = 'DIAGNOSIS'
ORDER BY ts.updated_at DESC;

-- Verify consultation types updated
SELECT ct.type_code, cts.updated_at
FROM consultation_type_segments cts
JOIN consultation_types ct ON cts.consultation_type_id = ct.id
WHERE cts.segment_code = 'DIAGNOSIS'
ORDER BY cts.updated_at DESC;

-- Check extraction used updated schema
SELECT e.id, e.extraction_data->'diagnosis'->'icd10_code' as icd10_code
FROM extractions e
WHERE e.doctor_id = 'DOCTOR_B_UUID'
  AND e.created_at > '2025-11-23'
LIMIT 1;
```

**Edge Cases to Test**:
- What if template has custom brevity but inherits prompt? (Brevity preserved, prompt updated)
- What if segment removed from master? (Templates keep segment but show "deprecated" warning)
- What if schema change makes old data invalid? (Old extractions still accessible, new extractions enforce new schema)

---

### 3.14 Workflow: Auto-Activation when Admin Shares Template with 'use' Access (NEW)

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Admin Shares Template with 'use' Access** |
| 1 | Admin creates new template: "PSYCH_ENHANCED" | Template created successfully | ⬜ |
| 2 | Admin configures template with 12 segments | Segments configured | ⬜ |
| 3 | Admin opens ShareTemplateModal for template | Modal opens | ⬜ |
| 4 | Admin selects "Individual Doctors" tab | Tab active | ⬜ |
| 5 | Admin enters Doctor A's UUID | UUID entered | ⬜ |
| 6 | Admin selects access_level: "Use" | Radio button selected | ⬜ |
| 7 | Admin clicks "Share Template" | Sharing starts | ⬜ |
| 8 | Backend creates doctor_templates record | Record inserted | ⬜ |
| 9 | **Backend auto-activates template** | activate_template_for_doctor() called | ⬜ |
| 10 | Verify doctor_templates.is_active = true | Database query confirms | ⬜ |
| 11 | Verify other templates deactivated | Only one active per consultation type | ⬜ |
| 12 | Success message: "Shared and activated for 1 doctor" | Message displayed | ⬜ |
| **Phase 2: Doctor A Sees Auto-Activated Template** |
| 13 | Doctor A opens VHR Screen | Screen loads | ⬜ |
| 14 | Doctor A selects consultation type: PSYCHIATRY | Type selected | ⬜ |
| 15 | Template dropdown loads | Dropdown displays templates | ⬜ |
| 16 | Verify "PSYCH_ENHANCED" appears with ✓ Active badge | Template auto-activated ✅ | ⬜ |
| 17 | Verify template is pre-selected | Auto-selected as only active template | ⬜ |
| 18 | Doctor A starts recording immediately | No activation needed, recording starts | ⬜ |
| 19 | Verify recording uses auto-activated template | template_id matches PSYCH_ENHANCED | ⬜ |
| **Phase 3: Admin Upgrades Access from 'view' to 'use'** |
| 20 | Admin shares different template with Doctor B: 'view' access | Template shared, is_active = false | ⬜ |
| 21 | Doctor B opens DoctorTemplateConfigScreen | Screen loads | ⬜ |
| 22 | Verify template shows "Clone Only" badge | View-only access confirmed | ⬜ |
| 23 | Verify template NOT in VHR Screen dropdown | Not activated (view-only) | ⬜ |
| 24 | Admin upgrades Doctor B's access to 'use' | Update access_level request sent | ⬜ |
| 25 | **Backend auto-activates on upgrade** | activate_template_for_doctor() called | ⬜ |
| 26 | Verify doctor_templates.is_active = true | Activation confirmed | ⬜ |
| 27 | Doctor B refreshes VHR Screen | Screen reloads | ⬜ |
| 28 | Verify template NOW appears with ✓ Active | Auto-activated after upgrade ✅ | ⬜ |
| **Phase 4: Verify Auto-Activation Logs** |
| 29 | Admin checks backend logs | Logs displayed | ⬜ |
| 30 | Verify log: "Auto-activated template {id} for doctor {id}" | Log entry found | ⬜ |
| 31 | Verify log: "Shared template with 'use' access" | Log entry found | ⬜ |
| **Phase 5: Bulk Share with Hospital - Auto-Activation** |
| 32 | Admin shares template with Hospital X (10 doctors) | Bulk share starts | ⬜ |
| 33 | Admin selects access_level: 'use' | Access level set | ⬜ |
| 34 | Backend auto-activates for all 10 doctors | Batch activation | ⬜ |
| 35 | Verify 10 doctor_templates records with is_active=true | Database confirms | ⬜ |
| 36 | All 10 doctors see template in VHR Screen | Template visible to all | ⬜ |

**Critical Validations**:
- ✅ Auto-activation only happens when access_level = 'use'
- ✅ Auto-activation deactivates other templates of same consultation type
- ✅ Upgrading from 'view' to 'use' triggers auto-activation
- ✅ Bulk sharing auto-activates for all doctors
- ✅ Backend logs all auto-activation events

**Database Queries**:
```sql
-- Verify auto-activation on share
SELECT dt.template_id, dt.doctor_id, dt.is_active, dt.access_level, dt.activated_at
FROM doctor_templates dt
WHERE dt.template_id = 'PSYCH_ENHANCED_UUID'
  AND dt.is_active = true;
-- Expected: Record with is_active=true immediately after sharing

-- Verify only one active template per type
SELECT dt.doctor_id, dt.consultation_type_id, COUNT(*) as active_count
FROM doctor_templates dt
JOIN templates t ON dt.template_id = t.id
WHERE dt.is_active = true
GROUP BY dt.doctor_id, t.consultation_type_id
HAVING COUNT(*) > 1;
-- Expected: 0 rows (no conflicts)
```

---

### 3.15 Workflow: Doctor Activates Template Directly from Consultation Type (NEW)

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Doctor Sees Visible Consultation Types** |
| 1 | Admin creates consultation type: "CARDIO" | Type created with visibility rules | ⬜ |
| 2 | Admin assigns visibility: Hospital A only | Visibility configured | ⬜ |
| 3 | Admin adds 15 segments to CARDIO type | Segments assigned | ⬜ |
| 4 | Doctor C (Hospital A) logs in | Authenticated | ⬜ |
| 5 | Doctor C opens DoctorTemplateConfigScreen | Screen loads | ⬜ |
| 6 | Screen displays dual view: LEFT = Consultation Types | Left panel visible | ⬜ |
| 7 | Verify CARDIO appears in left panel | Consultation type visible ✅ | ⬜ |
| 8 | Verify CARDIO shows "Activate" button | Button displayed | ⬜ |
| 9 | Verify badge: "Activate" (blue) | Badge color correct | ⬜ |
| **Phase 2: Doctor Activates from Consultation Type** |
| 10 | Doctor C clicks "Activate" on CARDIO | Activation starts | ⬜ |
| 11 | Backend: activate_from_consultation_type() called | Function invoked | ⬜ |
| 12 | Backend checks visibility permission | check_consultation_type_visibility() returns true | ⬜ |
| 13 | Backend creates new template | Template record created | ⬜ |
| 14 | Verify template code: "CARDIO_DoctorC_20251123..." | Unique code generated | ⬜ |
| 15 | Verify template name: "My Cardiology Template" | Custom name assigned | ⬜ |
| 16 | Verify template.doctor_id = Doctor C | Ownership assigned | ⬜ |
| 17 | Backend clones all 15 segments from consultation_type_segments | Segments copied to template_segments | ⬜ |
| 18 | Verify segments inherit category, brevity, terminology | All properties cloned | ⬜ |
| 19 | Backend auto-activates new template | is_active = true | ⬜ |
| 20 | Success: "Created and activated new template for Cardiology" | Alert displayed | ⬜ |
| 21 | Dashboard refreshes | loadDashboard() called | ⬜ |
| **Phase 3: Verify New Template Appears** |
| 22 | Right panel (Templates) updates | Template list refreshed | ⬜ |
| 23 | Verify new template appears with "Owned" badge | Badge: green background | ⬜ |
| 24 | Verify template shows ✓ Active indicator | Green "Active" badge | ⬜ |
| 25 | Verify "Clone" button available (no "Activate" button) | Only clone button shown | ⬜ |
| 26 | Doctor C clicks on owned template | Template details expand | ⬜ |
| 27 | Verify 15 segments visible | All segments cloned | ⬜ |
| **Phase 4: Use New Template in VHR Screen** |
| 28 | Doctor C navigates to VHR Screen | Screen loads | ⬜ |
| 29 | Doctor C selects consultation type: CARDIO | Type selected | ⬜ |
| 30 | Template dropdown shows "My Cardiology Template" | Template visible | ⬜ |
| 31 | Verify template is pre-selected (only active one) | Auto-selected ✅ | ⬜ |
| 32 | Doctor C starts recording | Recording begins | ⬜ |
| 33 | Verify recording metadata includes template_id | template_id stored | ⬜ |
| 34 | Doctor C completes recording | Recording saved | ⬜ |
| 35 | Extraction uses new template's 15 segments | All segments extracted | ⬜ |
| **Phase 5: Doctor Without Visibility Cannot Activate** |
| 36 | Doctor D (Hospital B) logs in | Authenticated | ⬜ |
| 37 | Doctor D opens DoctorTemplateConfigScreen | Screen loads | ⬜ |
| 38 | Verify CARDIO does NOT appear in left panel | Consultation type hidden ❌ | ⬜ |
| 39 | Verify only visible types shown (OP, DISCHARGE, etc.) | Visibility enforced | ⬜ |
| **Phase 6: Activate Multiple Times from Same Type** |
| 40 | Doctor C clicks "Activate" on CARDIO again | New activation request | ⬜ |
| 41 | Backend creates SECOND template | New template created | ⬜ |
| 42 | Verify unique template code (different timestamp) | Unique code generated | ⬜ |
| 43 | Backend auto-activates new template | is_active = true for new template | ⬜ |
| 44 | Verify FIRST template deactivated | is_active = false for old template | ⬜ |
| 45 | Doctor C sees both templates in right panel | Both owned templates visible | ⬜ |
| 46 | Verify only NEW template has ✓ Active badge | Only one active | ⬜ |

**Critical Validations**:
- ✅ Only visible consultation types appear in left panel
- ✅ Activation creates new doctor-owned template
- ✅ All segments cloned from consultation_type_segments
- ✅ New template auto-activated
- ✅ Previous templates of same type deactivated
- ✅ Template immediately usable in VHR Screen
- ✅ Visibility rules enforced (doctors without access cannot activate)

**Backend Function Calls**:
```python
# Expected call sequence
1. POST /api/v1/doctor-templates/activate-from-consultation-type
2. activate_from_consultation_type(doctor_id, consultation_type_id, template_name)
3. check_consultation_type_visibility(doctor_id, consultation_type_id)  # Returns True
4. supabase.table("templates").insert(...)  # Creates template
5. supabase.table("consultation_type_segments").select(...)  # Gets segments
6. supabase.table("template_segments").insert(...)  # Clones segments
7. activate_template_for_doctor(doctor_id, template_id, consultation_type_id)  # Auto-activates
```

**Database Queries**:
```sql
-- Verify template created from consultation type
SELECT t.template_code, t.template_name, t.doctor_id, t.consultation_type_id,
       COUNT(ts.segment_id) as segment_count
FROM templates t
LEFT JOIN template_segments ts ON t.id = ts.template_id
WHERE t.doctor_id = 'DOCTOR_C_UUID'
  AND t.consultation_type_id = (SELECT id FROM consultation_types WHERE type_code = 'CARDIO')
GROUP BY t.id;
-- Expected: Template with 15 segments

-- Verify segments cloned correctly
SELECT ts.segment_code, ts.category, ts.brevity_level, ts.terminology_style
FROM template_segments ts
JOIN templates t ON ts.template_id = t.id
WHERE t.template_name = 'My Cardiology Template'
ORDER BY ts.display_order;
-- Expected: 15 segments with inherited properties
```

---

### 3.16 Workflow: Soft-Delete Template Conflict Resolution (NEW)

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Setup - Template Shared and Activated** |
| 1 | Admin creates template: "TEST_TEMPLATE" | Template created | ⬜ |
| 2 | Admin shares with Doctor E: access_level='use' | Shared and auto-activated | ⬜ |
| 3 | Verify doctor_templates.is_active = true | Activated ✅ | ⬜ |
| 4 | Verify templates.is_active = true | Template active ✅ | ⬜ |
| 5 | Doctor E sees template in VHR Screen | Template visible | ⬜ |
| **Phase 2: Admin Soft-Deletes Template** |
| 6 | Admin sets templates.is_active = false | Template soft-deleted | ⬜ |
| 7 | Verify doctor_templates.is_active still = true | Junction record unchanged | ⬜ |
| 8 | **Conflict State Created** | templates.is_active=false, doctor_templates.is_active=true | ⬜ |
| **Phase 3: Doctor E Tries to Access Soft-Deleted Template** |
| 9 | Doctor E refreshes VHR Screen | Screen reloads | ⬜ |
| 10 | Backend: get_templates(filter_type='doctor') called | Query executed | ⬜ |
| 11 | Backend filters out templates where is_active=false | Filter applied at line 1291 | ⬜ |
| 12 | Backend logs warning: "Skipping soft-deleted template..." | Warning logged | ⬜ |
| 13 | Verify template NOT in dropdown | Template filtered out ✅ | ⬜ |
| 14 | Verify no error thrown | Graceful handling ✅ | ⬜ |
| **Phase 4: Doctor E Tries to Activate Soft-Deleted Template** |
| 15 | Doctor E tries to activate via API (direct call) | API request sent | ⬜ |
| 16 | Backend: activate_template_for_doctor() called | Function invoked | ⬜ |
| 17 | Backend checks templates.is_active at line 282 | Check executed | ⬜ |
| 18 | Backend raises ValueError: "template has been deactivated by admin" | Error raised ✅ | ⬜ |
| 19 | Frontend receives 400 error | Error response | ⬜ |
| 20 | Error message displayed to user | "Contact admin to reactivate" | ⬜ |
| **Phase 5: Admin Tries to Share Soft-Deleted Template** |
| 21 | Admin tries to share soft-deleted template with Doctor F | Share attempt | ⬜ |
| 22 | Backend: share_template_with_doctor() called | Function invoked | ⬜ |
| 23 | Backend checks templates.is_active at line 50 | Check executed | ⬜ |
| 24 | Backend raises ValueError: "template has been deactivated" | Error raised ✅ | ⬜ |
| 25 | Admin sees error: "Reactivate the template first before sharing" | Error message displayed | ⬜ |
| **Phase 6: Admin Reactivates Template** |
| 26 | Admin sets templates.is_active = true | Template reactivated | ⬜ |
| 27 | Doctor E refreshes VHR Screen | Screen reloads | ⬜ |
| 28 | Template appears in dropdown again | Template visible ✅ | ⬜ |
| 29 | Verify doctor_templates.is_active still = true | Activation preserved | ⬜ |
| 30 | Doctor E can use template for recording | Template functional | ⬜ |
| **Phase 7: Verify Both Fields Checked** |
| 31 | Query templates WHERE is_active=false AND doctor_templates.is_active=true | Query executed | ⬜ |
| 32 | Verify these templates NOT in doctor's VHR Screen | Filtered out ✅ | ⬜ |
| 33 | Query templates WHERE is_active=true AND doctor_templates.is_active=false | Query executed | ⬜ |
| 34 | Verify these templates NOT in VHR Screen | Filtered out (not activated) ✅ | ⬜ |
| 35 | Query templates WHERE is_active=true AND doctor_templates.is_active=true | Query executed | ⬜ |
| 36 | Verify ONLY these templates in VHR Screen | Both fields must be true ✅ | ⬜ |

**Truth Table Verification**:

| templates.is_active | doctor_templates.is_active | Visible in VHR? | Can Activate? | Test Step |
|---------------------|---------------------------|-----------------|---------------|-----------|
| true | true | ✅ Yes | N/A | Step 35-36 |
| true | false | ❌ No | ✅ Yes | Step 33-34 |
| false | true | ❌ No | ❌ No | Step 9-13 |
| false | false | ❌ No | ❌ No | Step 15-20 |

**Critical Validations**:
- ✅ Soft-deleted templates filtered out of VHR Screen (even if doctor_templates.is_active=true)
- ✅ Cannot activate soft-deleted templates
- ✅ Cannot share soft-deleted templates
- ✅ Warning logged when conflict detected
- ✅ Reactivating template restores functionality
- ✅ Both fields must be true for template to appear in VHR

**Backend Code References**:
```python
# supabase_service.py:1291-1296 - Filter soft-deleted templates
if not template.get("is_active", True):
    logger.warning(
        f"Skipping soft-deleted template {template.get('id')} "
        f"(templates.is_active=false but doctor_templates.is_active=true)"
    )
    continue

# doctor_templates_service.py:282-286 - Prevent activation
if not template.data[0].get("is_active", True):
    raise ValueError(
        f"Cannot activate template {template_id} - "
        "template has been deactivated by admin."
    )

# doctor_templates_service.py:50-54 - Prevent sharing
if not template.data[0].get("is_active", True):
    raise ValueError(
        f"Cannot share template {template_id} - "
        "template has been deactivated by admin."
    )
```

**Database Queries**:
```sql
-- Find conflict scenarios (soft-deleted but activated)
SELECT t.template_code, t.is_active as template_active,
       dt.is_active as junction_active, dt.doctor_id
FROM templates t
JOIN doctor_templates dt ON t.id = dt.template_id
WHERE t.is_active = false AND dt.is_active = true;
-- Expected: May have orphaned records, but they're filtered out

-- Verify only both-true templates visible
SELECT t.template_code, t.is_active, dt.is_active, dt.doctor_id
FROM templates t
JOIN doctor_templates dt ON t.id = dt.template_id
WHERE t.is_active = true AND dt.is_active = true;
-- Expected: Only these appear in VHR Screen
```

---

### 3.17 Workflow: DoctorTemplateConfigScreen UI Changes (NEW)

| Step | Action | Expected Result | Status |
|------|--------|-----------------|--------|
| **Phase 1: Verify Left Panel (Consultation Types)** |
| 1 | Doctor logs in and opens DoctorTemplateConfigScreen | Screen loads with dual view | ⬜ |
| 2 | Verify LEFT panel header: "Consultation Types" | Header visible | ⬜ |
| 3 | Verify subtitle: "Create a new template by activating from a consultation type" | Subtitle visible | ⬜ |
| 4 | Verify consultation types displayed with badges | Types visible | ⬜ |
| 5 | Verify badge color: "Activate" (blue) | bg-blue-100 text-blue-800 | ⬜ |
| 6 | Verify each consultation type has "Activate" button | Button present | ⬜ |
| 7 | Verify button text: "Activate" | Correct button text | ⬜ |
| 8 | Click "Activate" button | Button changes to "Creating..." | ⬜ |
| 9 | Verify button disabled during creation | Button disabled | ⬜ |
| 10 | Wait for completion | Success alert appears | ⬜ |
| **Phase 2: Verify Right Panel (Templates)** |
| 11 | Verify RIGHT panel header: "Templates" | Header visible | ⬜ |
| 12 | Verify subtitle: "Your owned, shared, and global templates" | Subtitle visible | ⬜ |
| 13 | Verify templates displayed with badges | Templates visible | ⬜ |
| 14 | Verify badge types: "Owned", "Use / Clone", "Clone Only" | Badge variety correct | ⬜ |
| 15 | **Verify NO "Activate" button for templates** | Activate button absent ✅ | ⬜ |
| 16 | **Verify ONLY "Clone" button present** | Clone button visible ✅ | ⬜ |
| 17 | Verify "Clone" button for owned templates | Clone available even for owned | ⬜ |
| 18 | Verify "Clone" button for shared templates | Clone available | ⬜ |
| 19 | Verify "Clone" button for common templates | Clone available | ⬜ |
| 20 | Verify active template shows ✓ Active indicator | Green badge visible | ⬜ |
| 21 | Verify active template has green border | border-green-500 bg-green-50 | ⬜ |
| **Phase 3: Verify Instructions Panel** |
| 22 | Scroll to instructions panel | Panel visible | ⬜ |
| 23 | Verify instruction 1: "Activate from Consultation Type" | Text present | ⬜ |
| 24 | Verify mentions "auto-activated for use in VHR Screen" | Auto-activation mentioned ✅ | ⬜ |
| 25 | Verify instruction 2: "Clone Template" | Text present | ⬜ |
| 26 | Verify mentions "auto-activated for use" | Auto-activation mentioned ✅ | ⬜ |
| 27 | Verify instruction 3: "Access Levels" | Text present | ⬜ |
| 28 | Verify 'use' access = "Auto-activated for extractions" | Correct description ✅ | ⬜ |
| 29 | Verify 'view' access = "Can only clone (read-only)" | Correct description ✅ | ⬜ |
| 30 | Verify instruction 4: "Active Templates" | Text present | ⬜ |
| 31 | Verify mentions "auto-activated when shared by admin" | Auto-activation mentioned ✅ | ⬜ |
| 32 | Verify instruction 5: "Template Badges" | Text present | ⬜ |
| 33 | Verify badge descriptions match UI | Descriptions accurate | ⬜ |
| **Phase 4: Verify Component Header Documentation** |
| 34 | Developer opens DoctorTemplateConfigScreen.tsx | File opened | ⬜ |
| 35 | Verify header comment mentions dual view | Documentation accurate | ⬜ |
| 36 | Verify mentions auto-activation for created templates | Auto-activation documented ✅ | ⬜ |
| 37 | Verify mentions auto-activation for cloned templates | Auto-activation documented ✅ | ⬜ |
| 38 | Verify mentions auto-activation by backend for 'use' access | Auto-activation documented ✅ | ⬜ |
| 39 | Verify mentions VHR Screen only shows activated templates | Documented ✅ | ⬜ |
| **Phase 5: Verify Removed Functions** |
| 40 | Developer searches for handleActivateTemplate function | Function not found ✅ | ⬜ |
| 41 | Developer searches for activateDoctorTemplate import | Import not found ✅ | ⬜ |
| 42 | Verify only 3 imports from summaryApi | getDoctorDashboard, activateFromConsultationType, cloneTemplate | ⬜ |
| 43 | Verify no "Activate" button in template rendering | Button removed ✅ | ⬜ |

**UI/UX Validations**:
- ✅ Clear separation: LEFT = create new, RIGHT = clone existing
- ✅ No confusing "Activate" button for templates (auto-activated instead)
- ✅ Instructions clearly explain auto-activation behavior
- ✅ Badge system intuitive (color-coded)
- ✅ Active template visually distinct (green border + badge)

**Code Review Checklist**:
```typescript
// Verify these changes in DoctorTemplateConfigScreen.tsx
✅ Line 20-24: Only 3 imports (removed activateDoctorTemplate)
✅ Line 91-111: handleActivateFromConsultationType exists
✅ Line 113-132: handleCloneTemplate exists
✅ Line 134: handleActivateTemplate removed
✅ Line 323-333: Only "Clone" button in template panel (no "Activate" button)
✅ Line 327-348: Updated instructions explaining auto-activation
```

---

## Test Suite 4: Edge Cases & Error Scenarios

### 4.1 Template Ownership Edge Cases

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-ED-001 | Doctor tries to edit common template directly | Error: "Clone to customize" | ⬜ |
| TC-ED-002 | Doctor tries to edit shared template | Error: "Clone to customize" | ⬜ |
| TC-ED-003 | Doctor tries to delete owned template | Success (template deleted) | ⬜ |
| TC-ED-004 | Doctor tries to delete common template | Button disabled | ⬜ |
| TC-ED-005 | Admin tries to share template they don't own | Success (admins can share any template) | ⬜ |

---

### 4.2 Access Level Validation

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-ED-011 | Doctor with 'view' access tries to activate | 403 error | ⬜ |
| TC-ED-012 | Doctor with 'view' access tries to clone | Clone button hidden or disabled | ⬜ |
| TC-ED-013 | Doctor with 'use' access activates template | Success | ⬜ |
| TC-ED-014 | Change access_level from 'view' to 'use' | Doctor can now activate | ⬜ |

---

### 4.3 Cloning Edge Cases

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-ED-021 | Clone template with 50+ segments | All segments copied correctly | ⬜ |
| TC-ED-022 | Clone template while offline | Error message: connection failed | ⬜ |
| TC-ED-023 | Clone same template multiple times | Each clone gets unique name suffix | ⬜ |
| TC-ED-024 | Clone template with special characters in name | Name sanitized correctly | ⬜ |

---

### 4.4 Concurrent Access

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-ED-031 | Two doctors activate same template simultaneously | Both succeed, no race condition | ⬜ |
| TC-ED-032 | Admin shares while doctor is viewing | Doctor's list updates automatically or on refresh | ⬜ |
| TC-ED-033 | Admin revokes while doctor has template active | Template deactivated, doctor notified | ⬜ |

---

### 4.5 Data Validation

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-ED-041 | Share template with invalid UUID format | 400 error: Invalid UUID | ⬜ |
| TC-ED-042 | Share template with empty doctor list | 400 error: At least one doctor required | ⬜ |
| TC-ED-043 | Share template with null access_level | Defaults to 'use' | ⬜ |
| TC-ED-044 | Activate template with missing consultation_type_id | 400 error: Required field | ⬜ |

---

## Test Suite 5: UI/UX Testing

### 5.1 Responsive Design

| Test Case | Viewport | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-UI-001 | Desktop (1920x1080) | All components render correctly | ⬜ |
| TC-UI-002 | Laptop (1366x768) | No horizontal scroll, readable text | ⬜ |
| TC-UI-003 | Tablet (768x1024) | Layout adapts, modals fit screen | ⬜ |
| TC-UI-004 | Mobile (375x667) | Components stack vertically | ⬜ |

---

### 5.2 Accessibility

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-A11Y-001 | Tab navigation through form | All inputs accessible via keyboard | ⬜ |
| TC-A11Y-002 | Screen reader on TemplateSelector | Ownership badges announced | ⬜ |
| TC-A11Y-003 | High contrast mode | Text readable, buttons visible | ⬜ |
| TC-A11Y-004 | Focus indicators | Visible focus ring on all interactive elements | ⬜ |

---

### 5.3 Loading States

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-LS-001 | TemplateSelector loading | Spinner displays, "Loading templates..." | ⬜ |
| TC-LS-002 | Template activation in progress | Button shows "Activating..." with spinner | ⬜ |
| TC-LS-003 | Clone template in progress | "Cloning..." state with disabled button | ⬜ |
| TC-LS-004 | Segment drag in progress | Visual feedback during drag | ⬜ |

---

### 5.4 Error Messages

| Test Case | Error Scenario | Expected Message | Status |
|-----------|----------------|------------------|--------|
| TC-ERR-001 | Network timeout | "Connection timeout. Please try again." | ⬜ |
| TC-ERR-002 | 404 Not Found | "Template not found. It may have been deleted." | ⬜ |
| TC-ERR-003 | 403 Forbidden | "You don't have permission to perform this action." | ⬜ |
| TC-ERR-004 | 500 Server Error | "Server error. Please contact support." | ⬜ |

---

## Test Suite 6: Performance Testing

### 6.1 Load Performance

| Test Case | Scenario | Threshold | Status |
|-----------|----------|-----------|--------|
| TC-PERF-001 | Load 100 templates in TemplateSelector | < 2 seconds | ⬜ |
| TC-PERF-002 | Drag-and-drop segment with 50 segments | < 200ms response | ⬜ |
| TC-PERF-003 | Clone template with 50 segments | < 5 seconds | ⬜ |
| TC-PERF-004 | Share template with 100 doctors | < 10 seconds | ⬜ |

---

### 6.2 Database Performance

| Test Case | Scenario | Threshold | Status |
|-----------|----------|-----------|--------|
| TC-PERF-011 | Query accessible templates (500 templates) | < 1 second | ⬜ |
| TC-PERF-012 | Activate template (deactivate old, activate new) | < 500ms | ⬜ |
| TC-PERF-013 | Bulk share with hospital (50 doctors) | < 5 seconds | ⬜ |

---

## Test Suite 7: Security Testing

### 7.1 Authorization

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-SEC-001 | Doctor A tries to access Doctor B's owned template | 403 Forbidden | ⬜ |
| TC-SEC-002 | Doctor tries to share template (admin-only) | 403 Forbidden | ⬜ |
| TC-SEC-003 | Unauthenticated request to activate template | 401 Unauthorized | ⬜ |
| TC-SEC-004 | Doctor tries to activate template they don't have access to | 403 Forbidden | ⬜ |

---

### 7.2 Data Integrity

| Test Case | Scenario | Expected Result | Status |
|-----------|----------|-----------------|--------|
| TC-INT-001 | Verify only one active template per doctor+type | Database constraint enforced | ⬜ |
| TC-INT-002 | Delete template with active shares | Cascade delete shares OR prevent delete | ⬜ |
| TC-INT-003 | Clone template preserves all segment configurations | Exact copy created | ⬜ |
| TC-INT-004 | Revoke access removes junction table entry | No orphaned records | ⬜ |

---

## Test Suite 8: Database Verification

### 8.1 Schema Validation

| Test Case | Query | Expected Result | Status |
|-----------|-------|-----------------|--------|
| TC-DB-001 | Check `templates` table has `doctor_id` column | Column exists, nullable | ⬜ |
| TC-DB-002 | Check `doctor_templates` junction table exists | Table exists with correct columns | ⬜ |
| TC-DB-003 | Check `doctor_id` index on templates | Index exists for performance | ⬜ |
| TC-DB-004 | Check unique constraint on (doctor_id, template_id, consultation_type_id) | Constraint enforced | ⬜ |

---

### 8.2 Data Validation Queries

```sql
-- TC-DB-011: Verify only one active template per doctor per consultation type
SELECT doctor_id, consultation_type_id, COUNT(*) as active_count
FROM doctor_templates
WHERE is_active = true
GROUP BY doctor_id, consultation_type_id
HAVING COUNT(*) > 1;
-- Expected: 0 rows (no violations)

-- TC-DB-012: Verify common templates have NULL doctor_id
SELECT COUNT(*) as common_templates
FROM templates
WHERE doctor_id IS NULL;
-- Expected: > 0 (at least some common templates)

-- TC-DB-013: Verify doctor-owned templates have valid doctor_id
SELECT COUNT(*) as owned_templates
FROM templates
WHERE doctor_id IS NOT NULL;
-- Expected: >= 0

-- TC-DB-014: Verify access levels are valid
SELECT DISTINCT access_level FROM doctor_templates;
-- Expected: Only 'view' and 'use'
```

---

## Regression Testing Checklist

### Critical Paths
- [ ] Doctor can still create recordings (VHR tab)
- [ ] Extraction still works for all consultation types
- [ ] Template admin screen still allows creating templates
- [ ] Segment configuration still saves correctly
- [ ] Drag-and-drop still works in admin screen
- [ ] Bulk clone still works
- [ ] Doctor selector still loads doctors
- [ ] Consultation type selector still works

---

## Test Execution Summary

### Coverage Metrics
- Total Test Cases: **330+** (Updated with NEW tests)
- Backend API Tests: **54** (+24 NEW tests)
  - Auto-Activation Tests: 7
  - Activate from Consultation Type: 10
  - Soft-Delete Filtering: 7
  - Original Tests: 30
- Frontend Component Tests: **40**
- End-to-End Workflows: **196** (+71 NEW workflow steps)
  - Workflow 3.14: Auto-Activation (36 steps)
  - Workflow 3.15: Activate from Consultation Type (46 steps)
  - Workflow 3.16: Soft-Delete Conflict Resolution (36 steps)
  - Workflow 3.17: DoctorTemplateConfigScreen UI (43 steps)
  - Original Workflows: 125
- Edge Cases: **25**
- UI/UX Tests: **15**
- Performance Tests: **10**
- Security Tests: **8**

### NEW Test Coverage (2025-11-23)
- ✅ Auto-activation when admin shares with 'use' access
- ✅ Doctor activates template directly from consultation type
- ✅ Soft-delete template conflict resolution (templates.is_active vs doctor_templates.is_active)
- ✅ DoctorTemplateConfigScreen UI changes verification
- ✅ Backend endpoint testing for new features
- ✅ Truth table validation for both is_active fields

### Test Execution Log

| Date | Tester | Tests Run | Passed | Failed | Blocked | Notes |
|------|--------|-----------|--------|--------|---------|-------|
|      |        |           |        |        |         |       |

---

## Bug Report Template

```markdown
**Bug ID**: BUG-XXXX
**Title**: [Brief description]
**Severity**: Critical / High / Medium / Low
**Test Case**: TC-XX-XXX
**Component**: TemplateSelector / ShareTemplateModal / DoctorTemplateConfigScreen / Backend API

**Steps to Reproduce**:
1.
2.
3.

**Expected Result**:

**Actual Result**:

**Screenshots/Logs**:

**Environment**:
- Browser:
- OS:
- Backend Version:
- Frontend Version:

**Additional Notes**:
```

---

## Sign-Off Criteria

### Phase 1: Smoke Testing (1-2 hours)
- [ ] All backend endpoints return 200/201 for valid requests
- [ ] All frontend components load without errors
- [ ] Basic workflows (share, activate, clone) work

### Phase 2: Functional Testing (10-14 hours)
- [ ] All backend API tests pass (54 tests)
  - [ ] **NEW**: Auto-Activation Tests (7 tests)
  - [ ] **NEW**: Activate from Consultation Type (10 tests)
  - [ ] **NEW**: Soft-Delete Filtering (7 tests)
- [ ] All frontend component tests pass (40 tests)
- [ ] All end-to-end workflows pass (196 tests)
  - [ ] **Critical**: Workflow 3.6 - Segment Cloning (18 steps)
  - [ ] **Critical**: Workflow 3.7 - Segment Creation (26 steps)
  - [ ] **Critical**: Workflow 3.8 - Consultation Type Visibility (56 steps)
  - [ ] **NEW Critical**: Workflow 3.14 - Auto-Activation (36 steps)
  - [ ] **NEW Critical**: Workflow 3.15 - Activate from Consultation Type (46 steps)
  - [ ] **NEW Critical**: Workflow 3.16 - Soft-Delete Conflict (36 steps)
  - [ ] **NEW**: Workflow 3.17 - UI Changes Verification (43 steps)

### Phase 3: Integration Testing (2-4 hours)
- [ ] All edge cases covered (25 tests)
- [ ] Security tests pass (8 tests)
- [ ] Database integrity verified

### Phase 4: Performance & Load Testing (2-3 hours)
- [ ] All performance thresholds met
- [ ] System stable under load

### Final Sign-Off
- [ ] Zero critical bugs
- [ ] All high-priority bugs resolved or documented
- [ ] Regression tests pass
- [ ] Documentation updated
- [ ] QA Lead approval
- [ ] Product Owner approval

---

## Quick Reference: New Critical Workflows

### Workflow 3.6 Summary: Segment Cloning
```
Admin → Clone Segment → Assign to Doctor Template → Doctor Configures → Doctor Uses
```
**Test Time**: ~30 minutes
**Key Checkpoint**: Cloned segment extracts data correctly

### Workflow 3.7 Summary: Custom Segment Creation
```
Admin → Create Segment → Define Schema → Assign to Template → Doctor Customizes → Verify Extraction
```
**Test Time**: ~45 minutes
**Key Checkpoint**: Custom segment JSON schema validation

### Workflow 3.8 Summary: Consultation Type Visibility
```
Admin → Clone Consultation Type → Set Visibility Rules → Test Access Matrix (10 scenarios)
```
**Test Time**: ~90 minutes
**Key Checkpoints**:
- Hospital visibility works (6 tests)
- Specialization visibility works (6 tests)
- Doctor-specific visibility works (6 tests)
- Mixed and global visibility works (4 tests)

---

**Document Owner**: QA Team
**Last Updated**: 2025-11-23 (Updated with NEW auto-activation & consultation type activation tests)
**Version**: 2.0 (Added Workflows 3.14-3.17 + Backend Tests for New Features)
**Next Review**: After test execution
**Total Test Cases**: 330+ (Updated from 250+)

# Backend API Changes - Frontend Integration Required

**Date**: 2025-11-23
**Purpose**: Track backend API changes that require frontend code updates

---

## Fixed Issues (Tests Now Passing)

### 1. ✅ Deactivate Template Endpoint - Response Schema Updated

**File**: `backend/routers/doctor_templates.py:303-307`
**Endpoint**: `POST /api/v1/doctor-templates/deactivate`
**Change**: Added `is_active` field to response

**Before**:
```json
{
  "success": true,
  "message": "Template deactivated successfully"
}
```

**After**:
```json
{
  "success": true,
  "is_active": false,
  "message": "Template deactivated successfully"
}
```

**Frontend Impact**:
- ✅ **Action Required**: Update any frontend code calling this endpoint to handle the `is_active` field
- Check files: `app/components/DoctorTemplateConfigScreen.tsx`, `app/components/TemplateAdminScreen.tsx`
- Look for: API calls to `/api/v1/doctor-templates/deactivate`

**Test Coverage**: 2 tests now passing
- `TestDeactivateTemplate::test_deactivate_active_template` ✅
- `TestDeactivateTemplate::test_deactivate_already_inactive_template` ✅

---

### 2. ✅ Junction Table Test - Database Schema Fix

**File**: `backend/tests/test_template_workflows.py:652`
**Change**: Fixed field name from `json_schema` to `schema_definition_json`

**Database Schema**:
- Field name: `schema_definition_json` (NOT `json_schema`)
- Table: `segment_definitions`

**Frontend Impact**:
- ℹ️ **No direct impact** - This is a backend test fix
- But if frontend queries `segment_definitions` table directly, ensure you're using correct field name: `schema_definition_json`

**Test Coverage**: 1 test now passing
- `TestJunctionTableIntegration::test_segment_definitions_independent_of_consultation_types` ✅

---

### 3. ✅ Activate Template Endpoint - Response Schema Updated

**File**: `backend/routers/doctor_templates.py:264-270`
**Endpoint**: `POST /api/v1/doctor-templates/activate`
**Change**: Added `is_active` field to response

**Before**:
```json
{
  "success": true,
  "message": "Template activated successfully",
  "activated_template_id": "...",
  "deactivated_previous": false
}
```

**After**:
```json
{
  "success": true,
  "is_active": true,
  "message": "Template activated successfully",
  "activated_template_id": "...",
  "deactivated_previous": false
}
```

**Frontend Impact**:
- ✅ **Action Required**: Update frontend to expect `is_active` field in activate response
- Check files: `app/components/DoctorTemplateConfigScreen.tsx`, `app/components/TemplateSelector.tsx`

**Test Coverage**: 4 tests now passing
- `TestActivateTemplate::test_activate_shared_template` ✅
- `TestActivateTemplate::test_activate_replaces_previous_active_template` ✅
- `TestActivateTemplate::test_activate_template_without_sharing` ✅
- `TestActivateTemplate::test_activate_common_template` ✅

---

### 4. ✅ Template Activation Deactivation Logic - Fixed

**File**: `backend/services/doctor_templates_service.py:328-338`
**Issue**: Multiple templates could be active simultaneously for same consultation type
**Fix**: Now deactivates all other active templates before activating new one

**Backend Change**:
```python
# Before: Only deactivated templates with matching consultation_type_id in database
# After: Deactivates ALL currently active templates for the doctor (ensures only 1 active)
```

**Frontend Impact**:
- ✅ **Improvement**: UI will now correctly show only 1 active template at a time
- No code changes needed - backend now enforces this constraint

**Test Coverage**: Included in activate tests above

---

## Pending Fixes (In Progress)

---

### 4. ⏳ Revoke Template Access Endpoint - Not Implemented

**Endpoint**: `DELETE /api/v1/doctor-templates/revoke`
**Issue**: Endpoint returns 404 Not Found
**Status**: Not yet implemented

**Expected Behavior**:
```
DELETE /api/v1/doctor-templates/revoke?template_code={id}&doctor_id={id}
Response: { "success": true }
```

**Frontend Impact**:
- **Action Required** (after implementation): Implement frontend UI to revoke template access
- Likely needed in: Admin screens for template management

**Test Coverage**: 3 tests failing
- `TestRevokeTemplateAccess::test_revoke_template_access_single_doctor` ❌
- `TestRevokeTemplateAccess::test_revoke_template_access_multiple_doctors` ❌
- `TestRevokeTemplateAccess::test_revoke_nonexistent_access` ❌

---

### 5. ⏳ Activate from Consultation Type - Not Implemented

**Endpoint**: `POST /api/v1/doctor-templates/activate-from-consultation-type`
**Issue**: Endpoint returns 404 Not Found
**Status**: Not yet implemented

**Expected Behavior**:
```
POST /api/v1/doctor-templates/activate-from-consultation-type
Body: { "doctor_id": "...", "consultation_type_id": "...", "template_name": "..." }
Response: { "success": true, "template": { ... } }
```

**Frontend Impact**:
- **Action Required** (after implementation): Add frontend feature to create templates from consultation types
- VHR Screen, Template Admin Screen

**Test Coverage**: 2 tests failing
- `TestActivateFromConsultationType::test_activate_from_consultation_type_success` ❌
- `TestActivateFromConsultationType::test_activate_from_consultation_type_without_visibility` ❌

---

### 6. ⏳ Share with Hospital - Not Implemented

**Endpoint**: `POST /api/v1/doctor-templates/share-hospital`
**Issue**: Endpoint returns 404 Not Found
**Status**: Not yet implemented

**Expected Behavior**:
```
POST /api/v1/doctor-templates/share-hospital
Body: { "template_id": "...", "hospital_id": "...", "access_level": "use" }
Response: { "success": true, "shared_count": 5 }
```

**Frontend Impact**:
- **Action Required** (after implementation): Add bulk share feature for hospitals
- Admin template management screens

**Test Coverage**: 1 test failing (workflow test)

---

### 7. ⏳ Share with Specialization - Not Implemented

**Endpoint**: `POST /api/v1/doctor-templates/share-specialization`
**Issue**: Endpoint returns 404 Not Found
**Status**: Not yet implemented

**Expected Behavior**:
```
POST /api/v1/doctor-templates/share-specialization
Body: { "template_id": "...", "specialization": "Cardiology", "access_level": "use" }
Response: { "success": true, "shared_count": 3 }
```

**Frontend Impact**:
- **Action Required** (after implementation): Add bulk share feature for specializations
- Admin template management screens

**Test Coverage**: 1 test failing (workflow test)

---

### 8. ⏳ Activation Deactivation Logic - Multiple Templates Active

**Issue**: Backend allows multiple templates to be active simultaneously for same consultation type
**Expected**: Only 1 template should be active per doctor per consultation type
**Status**: Not yet fixed

**Frontend Impact**:
- **Possible UI Issue**: If multiple templates are active, which one should be displayed as "current"?
- **Action Required**: Add frontend validation/warning if multiple templates are shown as active

**Test Coverage**: 1 test failing
- `TestActivateTemplate::test_activate_replaces_previous_active_template` ❌

---

### 9. ⏳ Access Level Validation - View Access Allows Activation

**Issue**: Backend allows template activation with `access_level='view'` (should only allow `access_level='use'`)
**Expected**: Return 403 Forbidden when trying to activate with view-only access
**Status**: Not yet fixed

**Frontend Impact**:
- **UI/UX**: Disable "Activate" button for templates with view-only access
- **Error Handling**: Handle 403 errors gracefully when user tries to activate view-only templates

**Test Coverage**: 1 test failing
- `TestAccessLevelValidation::test_activate_template_with_view_access_fails` ❌

---

---

### 5. ✅ Access Level Validation - Fixed

**Files**:
- `backend/services/doctor_templates_service.py:297-324`
- `backend/tests/test_doctor_templates_api.py:1083-1132`

**Issue**: Backend allowed template activation with 'view' access (should reject with 403)
**Fix**:
1. Service function now checks junction table FIRST (even for common templates)
2. Junction table access level takes precedence over default behavior
3. Common templates can be explicitly shared with 'view' access to restrict activation
4. Test updated to use proper UUID string conversion

**Backend Behavior**:
```python
# Priority order for access checking:
1. If junction table entry exists → use that access level (view or use)
2. Else if doctor owns template → automatic 'use' access
3. Else if common template (no junction entry) → default 'use' access
```

**Frontend Impact**:
- ✅ **Improvement**: UI should disable "Activate" button for templates with 'view' access
- **Error Handling**: Handle 403 errors with message containing "view" when activation fails

**Test Coverage**: 2 tests now passing
- `TestAccessLevelValidation::test_activate_template_with_view_access_fails` ✅
- `TestAccessLevelValidation::test_activate_template_with_use_access_succeeds` ✅

---

### 6. ✅ Get Accessible Templates - Added active_only Parameter

**File**: `backend/routers/doctor_templates.py:320-369`
**Endpoint**: `GET /api/v1/doctor-templates/accessible`
**Change**: Added `active_only` query parameter to filter only active templates

**Before**:
- Endpoint returned all accessible templates regardless of activation status
- No way to filter for only active templates

**After**:
```
GET /api/v1/doctor-templates/accessible?doctor_id={id}&active_only=true
Returns: Only templates where is_active=True
```

**Frontend Impact**:
- ✅ **New Feature**: Frontend can now filter to show only activated templates
- **Use Case**: Display active template badge, filter dropdown for active templates only
- **Query Params**: Add `active_only=true` to get only active templates

**Test Coverage**: 1 test now passing
- `TestGetAccessibleTemplates::test_get_accessible_templates_only_active` ✅

---

## Test Script Fixes

### Fix 1: Test expecting wrong database field name
**File**: `backend/tests/test_template_workflows.py:652`
**Issue**: Test expected `json_schema` but database uses `schema_definition_json`
**Fix**: Changed assertion to use correct field name

### Fix 2: Test using wrong template type
**File**: `backend/tests/test_doctor_templates_api.py:1083-1132`
**Issues**:
1. Used common template (doctor_id=NULL) which always has 'use' access
2. UUID not converted to string for JSON serialization
**Fixes**:
1. Updated to allow junction table to override common template access
2. Added `str()` conversion for UUID objects in share_data and activate_data

### Fix 3: Test using 'view' access when 'use' access required
**File**: `backend/tests/test_doctor_templates_api.py:363-409`
**Test**: `test_activate_shared_template`
**Issue**: Test shared template with 'view' access and expected activation to succeed, but access level validation now rejects 'view' access
**Fix**: Updated test to:
1. Share with 'use' access (which auto-activates)
2. Deactivate manually to reset state
3. Then manually activate to test the activate endpoint
**Frontend Impact**: This aligns test with access level validation - frontend should also prevent activation of templates with 'view' access

---

## Summary

### ✅ Completed (6 backend fixes + 3 test fixes)

**Backend Fixes**:
1. Deactivate endpoint response schema - added `is_active` field (2 tests)
2. Activate endpoint response schema - added `is_active` field (4 tests)
3. Template deactivation logic - ensures only 1 active template per doctor
4. Access level validation - checks junction table first, rejects view access (2 tests)
5. Get accessible templates - added `active_only` parameter (1 test)
6. Junction table test - fixed field name (1 test)

**Test Script Fixes**:
1. Fixed field name assertion (json_schema → schema_definition_json)
2. Fixed access level test to properly test view restriction
3. Fixed test_activate_shared_template to use 'use' access instead of 'view' access

### ⏳ Remaining (4 missing endpoints affecting 12 workflow tests)
1. Revoke endpoint - not implemented (3 direct tests + workflow tests)
2. Activate from consultation type - not implemented (2 tests)
3. Share with hospital - not implemented (workflow tests)
4. Share with specialization - not implemented (workflow tests)

### Test Status (Final)
- **Total Tests**: 78
- **Passing**: 43
- **Failing**: 12 (down from 19!)
- **Skipped**: 23 (auto-activation + AI extraction tests)

**Progress**: 19 → 12 failures (**7 tests fixed, 37% improvement!**)

---

## Frontend Files to Check

Based on the API changes, these frontend files likely need updates:

1. **`app/components/DoctorTemplateConfigScreen.tsx`**
   - Template activation/deactivation
   - Access level handling

2. **`app/components/TemplateAdminScreen.tsx`**
   - Bulk sharing (hospital, specialization)
   - Template creation from consultation types
   - Revoke access functionality

3. **`app/components/TemplateSelector.tsx`**
   - Display active template status
   - Handle view vs use access levels

4. **`app/components/VHRScreen.tsx`**
   - Template selection and activation

5. **`lib/summaryApi.ts` (or similar API service file)**
   - Update API response types for all affected endpoints

---

**Last Updated**: 2025-11-23 16:30 UTC
**Updated By**: Claude Code (Backend Test Fixes)

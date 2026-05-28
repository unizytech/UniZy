# Schema Cleanup & Template Sharing Implementation Summary

**Migration**: `20251123000000_cleanup_schema_and_add_doctor_templates.sql`
**Date**: 2025-11-23
**Status**: Implementation Complete, Testing Pending

## Overview

This implementation consolidates the template management architecture by:
1. Removing redundant/unused database columns and tables
2. Creating a junction table (`doctor_templates`) for template sharing and activation
3. Replacing `doctor_segment_configurations` with template cloning architecture
4. Standardizing field naming conventions across the codebase

## Database Schema Changes

### Columns Dropped

| Table | Column | Reason |
|-------|--------|--------|
| `segment_definitions` | `is_common` | Legacy field, only appeared in comments |
| `templates` | `created_by` | Legacy varchar column, unused |
| `templates` | `specialty` | Duplicate of `specialization` field |

**Note**: `templates.created_by_doctor_id` was renamed to `templates.doctor_id` throughout the codebase for consistency.

### Tables Dropped

| Table | Reason |
|-------|--------|
| `template_version_history` | Never used in production |
| `doctor_segment_configurations` | Redundant with new template cloning architecture |

**Architectural Shift**: Instead of storing doctor-specific segment configurations in a separate table, doctors now **clone templates** to create their own owned template records. Segment customization is stored in `template_segments` linked to the new template.

### New Table: `doctor_templates`

**Purpose**: Junction table for template sharing and activation tracking (many-to-many relationship).

```sql
CREATE TABLE doctor_templates (
    id UUID PRIMARY KEY,
    doctor_id UUID NOT NULL,                    -- Doctor who has access
    template_id UUID NOT NULL,                  -- Template being shared
    access_level TEXT NOT NULL DEFAULT 'use',   -- 'view' | 'use'
    is_active BOOLEAN DEFAULT false,            -- Currently activated?
    activated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT fk_doctor_templates_doctor FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    CONSTRAINT fk_doctor_templates_template FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE,
    CONSTRAINT doctor_templates_unique UNIQUE (doctor_id, template_id)
);
```

**Key Concepts**:
- **Access Level**:
  - `view` - Doctor can see template (read-only)
  - `use` - Doctor can apply template for extractions
- **Activation**: Only one template per `consultation_type` can be `is_active=true` per doctor
- **Ownership vs Access**: `templates.doctor_id` determines ownership, `doctor_templates` table determines shared access

### New Database Functions

1. **`can_doctor_access_template(doctor_id, template_id)`**
   - Returns `TRUE` if:
     - Template is common (`templates.doctor_id = NULL`), OR
     - Doctor owns the template (`templates.doctor_id = doctor_id`), OR
     - Doctor has explicit access via `doctor_templates` table

2. **`get_active_template_for_doctor(doctor_id, consultation_type_id)`**
   - Returns currently active template for doctor + consultation type
   - Priority: Explicitly activated → Doctor-owned → Common template

## Template Architecture

### Template Ownership Model

```
templates.doctor_id = NULL    → Common/Admin Template (immutable, read-only)
templates.doctor_id = UUID    → Doctor-Owned Template (editable by owner only)
```

### Template Access Flow

1. **Common Templates**:
   - Available to all doctors (read-only)
   - Must clone to customize
   - Example: Hospital-wide discharge summary template

2. **Doctor-Owned Templates**:
   - Created by doctor OR cloned from common/other templates
   - Only owner can edit
   - Can be shared with other doctors (via `doctor_templates`)

3. **Shared Templates**:
   - Owned by one doctor, shared with others
   - Access controlled via `doctor_templates.access_level`
   - Recipients see read-only or can use for extractions (cannot edit)

### Template Cloning Workflow

**Old Approach** (REMOVED):
```
Doctor activates template → Copy segments to doctor_segment_configurations → Customize
```

**New Approach** (IMPLEMENTED):
```
Doctor clicks "Clone Template" → New template record created (doctor_id set to doctor)
                               → All template_segments copied with new template_id
                               → Doctor can customize their owned template
```

**Implementation**: `supabase_service.py::clone_template(source_template_id, doctor_id, new_template_name, new_template_code)`

## Code Changes Summary

### Backend Services

#### `backend/services/supabase_service.py`

**Changes**:
1. ✅ Renamed `created_by_doctor_id` → `doctor_id` throughout (lines 1477, 1482, 1757)
2. ✅ Removed `specialty` parameter from `create_template()` and `update_template()` functions
3. ✅ Removed all `doctor_segment_configurations` functions (lines 1175-1341):
   - `get_doctor_segment_configuration()`
   - `update_doctor_segment_configuration()`
   - `apply_template_to_doctor()` - REPLACED with `clone_template()`
4. ✅ Created `clone_template()` function (new implementation)
5. ✅ Updated `get_segment_definitions()` to use `template_segments` directly (lines 954-1040)
   - Removed RPC call to `get_doctor_segment_configuration`
   - Direct query to `template_segments` table
   - Merges template-specific configuration with segment definitions
6. ✅ Removed `is_common` comment (line 2908)

#### `backend/services/doctor_templates_service.py` (NEW)

**Purpose**: Service layer for template sharing and activation management.

**Key Functions**:
- `share_template_with_doctor(template_id, doctor_id, access_level)` - Share with single doctor
- `bulk_share_template(template_id, doctor_ids, access_level)` - Share with multiple doctors
- `share_template_with_hospital(template_id, hospital_id, access_level)` - Share with all doctors in hospital
- `share_template_with_specialization(template_id, specialization, access_level)` - Share with all doctors of specialization
- `activate_template_for_doctor(doctor_id, template_id, consultation_type_id)` - Activate template (deactivates others of same type)
- `deactivate_template_for_doctor(doctor_id, template_id)` - Deactivate template
- `get_doctor_accessible_templates(doctor_id, consultation_type_id, include_common)` - List all accessible templates
- `revoke_template_access(doctor_id, template_id)` - Revoke shared access

**Usage Example**:
```python
from services.doctor_templates_service import share_template_with_hospital, activate_template_for_doctor

# Admin shares hospital-wide template with all cardiology doctors
share_template_with_hospital(
    template_id=uuid.UUID("..."),
    hospital_id=uuid.UUID("..."),
    access_level="use"
)

# Doctor activates template for OP consultations
activate_template_for_doctor(
    doctor_id=uuid.UUID("..."),
    template_id=uuid.UUID("..."),
    consultation_type_id=uuid.UUID("...")
)
```

#### `backend/routers/summary.py`

**Changes**:
1. ✅ Removed `specialty` field from Pydantic models (`CreateTemplateRequest`, `UpdateTemplateRequest`)
2. ✅ Updated endpoint implementations to use `doctor_id` instead of `created_by_doctor_id`
3. ✅ Removed `specialty=request.specialty` from `create_template()` calls

### Frontend Types

#### `lib/types.ts`

**Changes**:
1. ✅ Updated `Template` interface:
   ```typescript
   // REMOVED
   specialty: string;
   created_by_doctor_id?: string | null;

   // ADDED/KEPT
   use_case: string;
   specialization?: string | null; // For visibility filtering
   doctor_id?: string | null;      // NULL = common, UUID = doctor-owned
   ```

2. ✅ Added `DoctorTemplate` interface (junction table type):
   ```typescript
   export interface DoctorTemplate {
     id: string;
     doctor_id: string;
     template_id: string;
     access_level: 'view' | 'use';
     is_active: boolean;
     activated_at: string;
     created_at: string;
     updated_at: string;
   }
   ```

## Migration File Details

**File**: `backend/supabase/migrations/20251123000000_cleanup_schema_and_add_doctor_templates.sql`

**Structure**:
1. Part 1: Drop unused columns (with conditional checks)
2. Part 2: Drop unused tables (`template_version_history`)
3. Part 3: Drop `doctor_segment_configurations` table and related functions
4. Part 4: Create `doctor_templates` junction table with indexes
5. Part 5: Create helper functions (`can_doctor_access_template`, `get_active_template_for_doctor`)
6. Part 6: Update triggers (auto-update `updated_at` timestamp)
7. Verification queries (check success/failure of operations)

**Safety Features**:
- All column drops wrapped in `DO $$ ... END $$` conditional blocks
- Uses `IF EXISTS` for table/function drops
- Includes verification queries to confirm success
- Comprehensive comments explaining architecture

## Testing Checklist

### Database Migration Testing

- [ ] Run migration on development database
- [ ] Verify all columns dropped successfully
- [ ] Verify all tables dropped successfully
- [ ] Verify `doctor_templates` table created with correct schema
- [ ] Verify indexes created on `doctor_templates`
- [ ] Test `can_doctor_access_template()` function
- [ ] Test `get_active_template_for_doctor()` function
- [ ] Verify triggers work (`update_doctor_templates_updated_at`)

### Backend Code Testing

- [ ] Test `clone_template()` function
  - [ ] Clone common template → doctor-owned template
  - [ ] Verify all `template_segments` copied correctly
  - [ ] Verify new template has `doctor_id` set
- [ ] Test `get_segment_definitions()` with doctor_id
  - [ ] Verify it uses `template_segments` table
  - [ ] Verify segment configuration merging works
  - [ ] Verify no references to `doctor_segment_configurations`
- [ ] Test template CRUD operations
  - [ ] Create template with `doctor_id` (not `created_by_doctor_id`)
  - [ ] Update template without `specialty` field
  - [ ] Verify `specialization` field works for filtering

### Template Sharing Service Testing

- [ ] Test `share_template_with_doctor()`
  - [ ] Share template with access_level='view'
  - [ ] Share template with access_level='use'
  - [ ] Verify cannot share owner's own template with themselves
  - [ ] Verify cannot share already-shared template (unique constraint)
- [ ] Test `bulk_share_template()`
  - [ ] Share with multiple doctors (success + failures)
  - [ ] Verify error handling for invalid doctors
- [ ] Test `share_template_with_hospital()`
  - [ ] Share with all doctors in hospital
  - [ ] Verify only active doctors get access
- [ ] Test `share_template_with_specialization()`
  - [ ] Share with all doctors of specialization
  - [ ] Verify correct filtering
- [ ] Test `activate_template_for_doctor()`
  - [ ] Activate owned template
  - [ ] Activate shared template
  - [ ] Activate common template
  - [ ] Verify only one template active per consultation_type
  - [ ] Verify other templates deactivated automatically
- [ ] Test `deactivate_template_for_doctor()`
- [ ] Test `get_doctor_accessible_templates()`
  - [ ] Verify returns owned templates
  - [ ] Verify returns shared templates
  - [ ] Verify returns common templates (if include_common=True)
  - [ ] Verify filtering by consultation_type_id
- [ ] Test `revoke_template_access()`
  - [ ] Revoke shared template access
  - [ ] Verify cannot revoke owned template
  - [ ] Verify cannot revoke common template

### Frontend Integration Testing

- [ ] Update any frontend components using `specialty` field
- [ ] Update any frontend components using `created_by_doctor_id` field
- [ ] Test `DoctorTemplate` interface usage (if applicable)
- [ ] Verify template selector shows access_level badge
- [ ] Verify template selector shows activated badge (`is_active`)

### API Endpoint Testing

- [ ] Test `POST /api/v1/summary/templates/{consultation_type}` (create template)
  - [ ] Verify `specialty` field not accepted
  - [ ] Verify `doctor_id` field works
- [ ] Test `PUT /api/v1/summary/templates/{template_id}` (update template)
  - [ ] Verify `specialty` field not accepted
- [ ] Test template activation endpoint (if exists)
  - [ ] Verify uses `doctor_templates` table

## Rollback Plan

If migration fails or causes issues:

1. **Rollback SQL** (create separate file):
   ```sql
   -- Restore doctor_segment_configurations table
   CREATE TABLE doctor_segment_configurations (...);

   -- Restore dropped columns
   ALTER TABLE segment_definitions ADD COLUMN is_common BOOLEAN DEFAULT false;
   ALTER TABLE templates ADD COLUMN created_by VARCHAR(255);
   ALTER TABLE templates ADD COLUMN specialty VARCHAR(100);

   -- Drop doctor_templates table
   DROP TABLE IF EXISTS doctor_templates CASCADE;
   ```

2. **Code Rollback**:
   - Revert `supabase_service.py` changes
   - Revert `summary.py` changes
   - Revert `types.ts` changes
   - Remove `doctor_templates_service.py`

3. **Git Rollback**:
   ```bash
   git revert <commit-hash>
   ```

## Next Steps

1. **Immediate**:
   - [ ] Run migration on development database
   - [ ] Execute testing checklist
   - [ ] Fix any issues discovered during testing

2. **Backend API Updates**:
   - [ ] Create API endpoints for template sharing (`POST /api/v1/templates/{id}/share`)
   - [ ] Create API endpoint for template cloning (`POST /api/v1/templates/{id}/clone`)
   - [ ] Update template activation endpoints to use `doctor_templates` table
   - [ ] Add template access control middleware (check `can_doctor_access_template()`)

3. **Frontend UI Updates**:
   - [ ] Add "Clone Template" button to template list
   - [ ] Add "Share Template" modal for admins
   - [ ] Show access_level badge on shared templates
   - [ ] Show "Activated" badge on active templates
   - [ ] Update template selector to filter by access

4. **Documentation**:
   - [ ] Update API documentation with new endpoints
   - [ ] Update TEMPLATE_MANAGEMENT_ARCHITECTURE.md with new architecture
   - [ ] Create template sharing guide for admins
   - [ ] Update CLAUDE.md with new architecture details

## Architecture Decisions

### Why Remove `doctor_segment_configurations`?

**Problem**: Two competing approaches for doctor customization:
1. Activate template → Copy segments to `doctor_segment_configurations` (old)
2. Clone template → New `templates` record + `template_segments` (new)

**Decision**: Keep template cloning approach only.

**Rationale**:
- Template cloning is more flexible (doctors can create/share/manage templates)
- `doctor_segment_configurations` was redundant (same data as `template_segments`)
- Template cloning supports ownership model (`templates.doctor_id`)
- Sharing templates via `doctor_templates` junction table is cleaner
- Reduces database complexity (one less table)

### Why `doctor_templates` Junction Table?

**Problem**: How to represent template sharing (many-to-many relationship)?

**Options Considered**:
1. ❌ Array column in `templates` table (`doctor_ids UUID[]`) - Hard to query, no metadata
2. ❌ Array column in `doctors` table (`template_ids UUID[]`) - Hard to maintain
3. ✅ Junction table `doctor_templates` - Standard many-to-many pattern

**Decision**: Create `doctor_templates` junction table.

**Benefits**:
- Standard many-to-many pattern (easy to query)
- Supports per-relationship metadata (`access_level`, `is_active`, `activated_at`)
- Supports bulk sharing operations (hospitals, specializations)
- Supports activation tracking (one active template per consultation_type)
- Easy to add future features (shared_by, sharing_reason, etc.)

### Why Distinguish `access_level` from `is_active`?

**Problem**: What does "doctor has access to template" mean?

**Decision**: Separate access from activation.

**Access Level** (`access_level`):
- `view` - Doctor can see template structure (read-only)
- `use` - Doctor can apply template for extractions

**Activation** (`is_active`):
- `true` - This is the doctor's currently selected template for this consultation_type
- `false` - Doctor has access but it's not currently activated

**Example**:
```
Doctor A has access to 5 OP templates:
- Template 1 (owned):     access_level='use', is_active=true   ← Currently using
- Template 2 (owned):     access_level='use', is_active=false
- Template 3 (shared):    access_level='use', is_active=false
- Template 4 (shared):    access_level='view', is_active=false ← Read-only
- Template 5 (common):    access_level='use', is_active=false
```

## References

- **Migration File**: `backend/supabase/migrations/20251123000000_cleanup_schema_and_add_doctor_templates.sql`
- **Service Layer**: `backend/services/doctor_templates_service.py`
- **Database Service**: `backend/services/supabase_service.py` (lines 954-1040, 1477-1757)
- **API Router**: `backend/routers/summary.py`
- **Frontend Types**: `lib/types.ts`
- **Architecture Guide**: `TEMPLATE_MANAGEMENT_ARCHITECTURE.md` (to be updated)

## Glossary

- **Common Template**: Template with `doctor_id=NULL`, available to all doctors (read-only)
- **Doctor-Owned Template**: Template with `doctor_id=UUID`, owned by specific doctor
- **Template Cloning**: Creating a new template record by copying an existing template
- **Template Sharing**: Granting access to a template via `doctor_templates` junction table
- **Template Activation**: Setting a template as the currently selected template for a doctor+consultation_type
- **Access Level**: Permission level for shared templates (`view` or `use`)
- **Segment Configuration**: Per-segment settings (category, brevity, terminology) stored in `template_segments`

# Admin Modules & Configuration System Rearchitecture - Implementation Guide

**Status:** Not Started
**Estimated Effort:** 32-44 hours (5-6 days)
**Downtime Required:** 5-10 minutes (Phase 3: Table Renames)
**Created:** 2025-11-22
**Last Updated:** 2025-11-22 (Enhanced with Edge Functions, Triggers & Indexes)

---

## 📋 MASTER TODO CHECKLIST

### Phase 1: Database Schema Migration (Non-Breaking) - 4-5 hours

- [ ] **1.1 Modify segment_definitions table**
  - [ ] Add segment_type column (TEXT, DEFAULT 'system')
  - [ ] Add doctor_id column (UUID, nullable, FK to doctors)
  - [ ] Add CHECK constraint for segment ownership
  - [ ] Verify description column exists
  - [ ] Verify default_category column exists
  - [ ] Verify is_active column exists (BOOLEAN, DEFAULT true)
  - [ ] Test soft delete functionality

- [ ] **1.2 Enhance consultation_type_segment_defaults (before rename)**
  - [ ] Add segment_id column (UUID)
  - [ ] Populate segment_id from segment_definitions.id
  - [ ] Add consultation_type_name column (TEXT)
  - [ ] Populate consultation_type_name from consultation_types
  - [ ] Add FK constraint on segment_id
  - [ ] Add index on segment_id
  - [ ] Verify data integrity

- [ ] **1.3 Enhance template_segment_configurations (before rename)**
  - [ ] Add segment_id column (UUID)
  - [ ] Populate segment_id from segment_definitions.id
  - [ ] Add template_name column (TEXT)
  - [ ] Populate template_name from templates
  - [ ] Add FK constraint on segment_id
  - [ ] Add index on segment_id
  - [ ] Verify data integrity

- [ ] **1.4 Add visibility controls to consultation_types**
  - [ ] Add visible_to_hospitals column (UUID[])
  - [ ] Add visible_to_doctors column (UUID[])
  - [ ] Add visible_to_specializations column (TEXT[])
  - [ ] Test visibility logic

- [ ] **1.5 Modify templates table**
  - [ ] Rename created_by_doctor_id → doctor_id
  - [ ] Add unique constraint (doctor_id, template_code)
  - [ ] Verify is_active column exists
  - [ ] Test constraints

- [ ] **1.6 Modify doctor_segment_configurations table**
  - [ ] Add template_id column (UUID, FK to templates)
  - [ ] Populate template_id from doctor_active_templates
  - [ ] Drop active_template_id column
  - [ ] Update unique constraint to (doctor_id, template_id, segment_code)
  - [ ] Verify data migration

- [ ] **1.7 Backup all affected tables**
  - [ ] Export segment_definitions
  - [ ] Export consultation_type_segment_defaults
  - [ ] Export template_segment_configurations
  - [ ] Export templates
  - [ ] Export doctor_active_templates
  - [ ] Export doctor_segment_configurations
  - [ ] Store backups securely with timestamp

### Phase 2: Data Migration Scripts - 2-3 hours

- [ ] **2.1 Create migration script: 025_add_segment_ownership_tracking.sql**
  - [ ] Write ALTER TABLE statements
  - [ ] Write UPDATE statements for data population
  - [ ] Add CHECK constraints
  - [ ] Test on local database copy

- [ ] **2.2 Create migration script: 026_add_junction_table_columns.sql**
  - [ ] Add columns to both junction tables
  - [ ] Populate segment_id values
  - [ ] Populate denormalized name columns
  - [ ] Add indexes and constraints

- [ ] **2.3 Create migration script: 027_migrate_template_ownership.sql**
  - [ ] Rename created_by_doctor_id → doctor_id
  - [ ] Add unique constraints
  - [ ] Update doctor_segment_configurations

- [ ] **2.4 Verify all migrations run successfully**
  - [ ] Test migrations on development database
  - [ ] Check for data integrity issues
  - [ ] Verify foreign key constraints
  - [ ] Document any issues found

### Phase 3: Table Renames (BREAKING - 5-10 min downtime) - 1 hour

- [ ] **3.1 Schedule maintenance window**
  - [ ] Notify stakeholders
  - [ ] Set maintenance mode if applicable
  - [ ] Create deployment checklist

- [ ] **3.2 Create migration script: 028_rename_junction_tables.sql**
  - [ ] Rename consultation_type_segment_defaults → consultation_type_segments
  - [ ] Rename template_segment_configurations → template_segments
  - [ ] Update primary key constraints
  - [ ] Update unique constraints
  - [ ] Test rename script

- [ ] **3.3 Execute table renames**
  - [ ] Run migration script
  - [ ] Verify tables renamed correctly
  - [ ] Check all constraints are intact

### Phase 4: Schema Cleanup, Edge Functions, Triggers & Indexes - 3-4 hours

- [ ] **4.1 Create migration script: 029_cleanup_deprecated_columns.sql**
  - [ ] Drop consultation_type_id from segment_definitions
  - [ ] Drop template_id from segment_definitions
  - [ ] Drop doctor_active_templates table CASCADE
  - [ ] Add visibility columns to consultation_types

- [ ] **4.2 Update Edge Functions (RPC Functions)**
  - [ ] Update apply_template_to_doctor() - Change table references
  - [ ] Update get_doctor_segment_configuration() - Major rewrite for new schema
  - [ ] Update validate_segment_configuration() - Update table references
  - [ ] Test all RPC functions after updates

- [ ] **4.3 Update Database Triggers**
  - [ ] Remove update_doctor_active_templates_updated_at trigger
  - [ ] Verify all other triggers still work after table renames
  - [ ] Test trigger functionality

- [ ] **4.4 Update and Create Indexes**
  - [ ] Drop deprecated indexes (consultation_type_id, template_id on segment_definitions)
  - [ ] Rename indexes for renamed tables
  - [ ] Create new indexes (segment_id, segment_type, doctor_id, denormalized names)
  - [ ] Verify index performance

- [ ] **4.5 Execute cleanup**
  - [ ] Run migration script
  - [ ] Verify no broken references
  - [ ] Test database integrity

### Phase 5: Backend Code Updates - 14-20 hours

#### 5.1 Update backend/services/supabase_service.py - 5-7 hours

- [ ] **Rename table references (global find/replace)**
  - [ ] template_segment_configurations → template_segments (11+ occurrences)
  - [ ] consultation_type_segment_defaults → consultation_type_segments (8+ occurrences)

- [ ] **Update get_template_configuration() (~line 1490)**
  - [ ] Change table name
  - [ ] Add is_active filter
  - [ ] Test function

- [ ] **Update update_template_segment_config() (~line 1970-2008)**
  - [ ] Add segment_id lookup logic
  - [ ] Add template_name denormalization
  - [ ] Update table name
  - [ ] Test function

- [ ] **Create create_segment_from_doctor_request()**
  - [ ] Write function signature
  - [ ] Add validation logic
  - [ ] Insert with segment_type='doctor'
  - [ ] Set is_active based on approval status
  - [ ] Test function

- [ ] **Create approve_doctor_segment()**
  - [ ] Write function signature
  - [ ] Update is_active to true
  - [ ] Handle scope assignment (global/consultation_types/template)
  - [ ] Insert into junction tables based on scope
  - [ ] Test all scope types

- [ ] **Update inherit_from_consultation_type() (~line 2083-2104)**
  - [ ] Change table name to consultation_type_segments
  - [ ] Use segment_id instead of segment_code matching
  - [ ] Add template_name denormalization
  - [ ] Test function

- [ ] **Update get_segment_definitions()**
  - [ ] Add is_active filter
  - [ ] Update junction table joins
  - [ ] Test function

- [ ] **Update get_consultation_type_segments()**
  - [ ] Change table name
  - [ ] Add is_active filter on joined segments
  - [ ] Test function

- [ ] **Create create_template_from_consultation_type()**
  - [ ] Write function signature
  - [ ] Create template record
  - [ ] Copy segments from consultation_type_segments to template_segments
  - [ ] Use segment_id for copying
  - [ ] Test function

- [ ] **Update get_doctor_templates()**
  - [ ] Filter by is_active
  - [ ] Update query logic
  - [ ] Test function

- [ ] **Update activate_preset() (if exists)**
  - [ ] Change table references
  - [ ] Test function

- [ ] **Update validate_segment_configuration()**
  - [ ] Update table references
  - [ ] Add is_active checks
  - [ ] Test function

- [ ] **Update all RPC function wrappers**
  - [ ] Find all functions that call Supabase RPC
  - [ ] Update table names in SQL strings
  - [ ] Test each RPC call

#### 5.2 Update backend/services/segment_registry.py - 1-2 hours

- [ ] **Update load_segments_for_mode() (~line 334)**
  - [ ] Change table name to template_segments
  - [ ] Add is_active filter with JOIN
  - [ ] Test with all modes (core/additional/full)

- [ ] **Update generate_extraction_artifacts()**
  - [ ] Verify table references
  - [ ] Test function

#### 5.3 Update backend/routers/summary.py - 4-5 hours

- [ ] **Update GET /admin/templates/{template_code}/segments (~line 1216)**
  - [ ] Change table name
  - [ ] Add is_active filter
  - [ ] Test endpoint

- [ ] **Update PUT /admin/templates/{template_code}/segments/{segment_code} (~line 1258)**
  - [ ] Add segment_id lookup
  - [ ] Add template_name denormalization
  - [ ] Change table name
  - [ ] Test endpoint

- [ ] **Update POST /admin/templates/{template_code}/segments/bulk (~line 1312)**
  - [ ] Add segment_id lookup for each segment
  - [ ] Add template_name denormalization
  - [ ] Change table name
  - [ ] Test endpoint

- [ ] **Update GET /admin/consultation-types/{type_code}/segments (~line 1566)**
  - [ ] Change table name
  - [ ] Add is_active filter
  - [ ] Test endpoint

- [ ] **Create POST /api/v1/admin/consultation-types/{type_code}/segments**
  - [ ] Write endpoint handler
  - [ ] Accept bulk segment assignments
  - [ ] Use segment_id
  - [ ] Add consultation_type_name denormalization
  - [ ] Test endpoint

- [ ] **Create DELETE /api/v1/admin/consultation-types/{type_code}/segments/{segment_code}**
  - [ ] Write endpoint handler
  - [ ] Remove from consultation_type_segments
  - [ ] Test endpoint

- [ ] **Create POST /api/v1/doctors/{doctor_id}/templates/create-from-consultation-type**
  - [ ] Write endpoint handler
  - [ ] Call create_template_from_consultation_type service
  - [ ] Return template details
  - [ ] Test endpoint

- [ ] **Create GET /api/v1/doctors/{doctor_id}/available-consultation-types**
  - [ ] Write endpoint handler
  - [ ] Implement visibility filtering logic
  - [ ] Test with different visibility scenarios

- [ ] **Create POST /api/v1/doctors/{doctor_id}/segments/request**
  - [ ] Write endpoint handler
  - [ ] Call create_segment_from_doctor_request service
  - [ ] Set is_active=false (pending approval)
  - [ ] Test endpoint

- [ ] **Create PUT /api/v1/admin/segments/{segment_id}/approve**
  - [ ] Write endpoint handler
  - [ ] Accept scope parameter (global/consultation_types/template)
  - [ ] Call approve_doctor_segment service
  - [ ] Test with all scope types

#### 5.4 Update backend/routers/doctors.py - 2-3 hours

- [ ] **Remove /activated-templates endpoints**
  - [ ] Identify all affected endpoints
  - [ ] Remove code
  - [ ] Update API documentation

- [ ] **Create new template CRUD endpoints**
  - [ ] GET /api/v1/doctors/{doctor_id}/templates
  - [ ] POST /api/v1/doctors/{doctor_id}/templates
  - [ ] GET /api/v1/doctors/{doctor_id}/templates/{template_id}
  - [ ] PUT /api/v1/doctors/{doctor_id}/templates/{template_id}
  - [ ] DELETE /api/v1/doctors/{doctor_id}/templates/{template_id}
  - [ ] Test all endpoints

- [ ] **Create segment request endpoints**
  - [ ] GET /api/v1/doctors/{doctor_id}/segment-requests (list pending)
  - [ ] Test endpoint

#### 5.5 Update SQL Migration Files - 2-3 hours

- [ ] **Update 024_fix_excluded_segments_in_full_mode.sql**
  - [ ] Replace table names
  - [ ] Add is_active filters
  - [ ] Test migration

- [ ] **Update 023_fix_duplicate_segments_with_distinct.sql**
  - [ ] Replace table names
  - [ ] Test migration

- [ ] **Update 022_show_excluded_segments_in_full_mode.sql**
  - [ ] Replace table names
  - [ ] Add is_active filters
  - [ ] Test migration

- [ ] **Update 019_drop_legacy_columns.sql**
  - [ ] Review if still relevant
  - [ ] Update if needed

- [ ] **Update 014_refactor_template_id_to_active_template_id.sql**
  - [ ] Review if still relevant
  - [ ] May need removal since we're dropping doctor_active_templates

- [ ] **Update 012_fix_apply_template_function.sql (RPC)**
  - [ ] Replace table names in function body
  - [ ] Add segment_id usage
  - [ ] Add is_active filters
  - [ ] Test RPC function

- [ ] **Update 006_fix_get_doctor_segment_config_with_template_hierarchy.sql (RPC)**
  - [ ] Replace table names in function body
  - [ ] Update JOIN logic for new schema
  - [ ] Add is_active filters
  - [ ] Test RPC function

- [ ] **Update 005_update_get_doctor_segment_config_function.sql**
  - [ ] Replace table names
  - [ ] Add is_active filters
  - [ ] Test function

### Phase 6: Frontend UI Changes - 12-15 hours

#### 6.1 Update TemplateAdminScreen.tsx - 5-6 hours

- [ ] **Add visibility controls for consultation types**
  - [ ] Create multi-select component for hospitals
  - [ ] Create multi-select component for doctors
  - [ ] Create multi-select component for specializations
  - [ ] Integrate into consultation type create/edit form
  - [ ] Test visibility logic

- [ ] **Add segment assignment UI**
  - [ ] Create "Manage Segments" panel for consultation types
  - [ ] Create available segments list (left side)
  - [ ] Create assigned segments list (right side)
  - [ ] Implement multi-select checkboxes
  - [ ] Implement drag-and-drop to assign/unassign
  - [ ] Call new POST/DELETE endpoints
  - [ ] Test assignment workflow

- [ ] **Enhance drag-and-drop with multi-select**
  - [ ] Add checkboxes to segment items
  - [ ] Add bulk action buttons (Move to CORE/ADDITIONAL/EXCLUDED)
  - [ ] Apply to selected segments
  - [ ] Test multi-select drag-and-drop

- [ ] **Add segment approval workflow**
  - [ ] Create pending segments list view
  - [ ] Filter by is_active=false and segment_type='doctor'
  - [ ] Show segment details and requesting doctor
  - [ ] Create approval modal with scope selection
  - [ ] Call approve endpoint
  - [ ] Test approval workflow

#### 6.2 Update DoctorTemplateConfigScreen.tsx - 6-7 hours

- [ ] **Redesign template activation flow**
  - [ ] Remove old activation logic
  - [ ] Add consultation type selector dropdown
  - [ ] Call GET /available-consultation-types endpoint
  - [ ] Create "Create Template from Type" button
  - [ ] Create template creation modal
  - [ ] Call POST /create-from-consultation-type endpoint
  - [ ] Test template creation

- [ ] **Create template list view**
  - [ ] Group templates by consultation type
  - [ ] Show template cards (name, segment count, last modified)
  - [ ] Add action buttons (Edit Segments, Rename, Delete)
  - [ ] Test list view

- [ ] **Update segment customization**
  - [ ] Ensure drag-and-drop works with new template_segments table
  - [ ] Add multi-select checkboxes
  - [ ] Add bulk action buttons
  - [ ] Save to template_segments (not doctor_segment_configurations)
  - [ ] Test customization

- [ ] **Add segment request workflow**
  - [ ] Create "Request New Segment" button
  - [ ] Create request form modal (name, code, description, prompt, schema)
  - [ ] Call POST /segments/request endpoint
  - [ ] Show pending requests with status
  - [ ] Test request workflow

#### 6.3 Update VHRScreen.tsx - 1-2 hours

- [ ] **Update template selection logic**
  - [ ] Call GET /doctors/{id}/templates endpoint
  - [ ] Filter by is_active=true
  - [ ] Remove template_name_override logic
  - [ ] Update dropdown to show template.template_name
  - [ ] Test template selection

### Phase 7: Testing & Validation - 4-6 hours

#### 7.1 Database Tests

- [ ] **Verify schema changes**
  - [ ] All columns exist as expected
  - [ ] All constraints are in place
  - [ ] All indexes created
  - [ ] Foreign keys intact

- [ ] **Test data integrity**
  - [ ] All segment_id values populated correctly
  - [ ] All denormalized names populated correctly
  - [ ] No orphaned records
  - [ ] Verify segment ownership tracking

- [ ] **Test segment_type and doctor_id logic**
  - [ ] Create system segment (segment_type='system', doctor_id=NULL)
  - [ ] Create doctor segment (segment_type='doctor', doctor_id populated)
  - [ ] Verify CHECK constraint works
  - [ ] Test soft delete (is_active=false)

#### 7.2 Backend API Tests

- [ ] **Test consultation type visibility**
  - [ ] Create consultation type with hospital visibility
  - [ ] Create consultation type with doctor visibility
  - [ ] Create consultation type with specialization visibility
  - [ ] Verify filtering works correctly

- [ ] **Test segment assignment to consultation types**
  - [ ] Assign single segment
  - [ ] Assign multiple segments (bulk)
  - [ ] Unassign segment
  - [ ] Verify junction table updates

- [ ] **Test template creation from consultation type**
  - [ ] Create template from type
  - [ ] Verify segments copied correctly
  - [ ] Verify segment_id used (not just segment_code)
  - [ ] Verify template_name denormalized

- [ ] **Test segment customization**
  - [ ] Update segment category
  - [ ] Update segment order
  - [ ] Update segment brevity/terminology
  - [ ] Verify updates saved to template_segments

- [ ] **Test doctor segment request workflow**
  - [ ] Doctor submits segment request (is_active=false)
  - [ ] Admin approves with scope=global
  - [ ] Admin approves with scope=consultation_types
  - [ ] Admin approves with scope=template
  - [ ] Verify is_active set to true
  - [ ] Verify junction table inserts

- [ ] **Test soft delete functionality**
  - [ ] Set segment is_active=false
  - [ ] Verify segment doesn't appear in active queries
  - [ ] Verify existing extractions still work (references by segment_id)

#### 7.3 Frontend Tests

- [ ] **Test admin UI**
  - [ ] Create consultation type with visibility rules
  - [ ] Assign segments to consultation type
  - [ ] Use bulk clone feature
  - [ ] Approve doctor segment request
  - [ ] Test all multi-select operations

- [ ] **Test doctor config UI**
  - [ ] View available consultation types (filtered by visibility)
  - [ ] Create template from consultation type
  - [ ] Customize template segments
  - [ ] Request new segment
  - [ ] View pending requests

- [ ] **Test VHR screen**
  - [ ] Select doctor
  - [ ] Select template
  - [ ] Verify correct template loaded
  - [ ] Perform recording with template

#### 7.4 Integration Tests

- [ ] **End-to-end workflow tests**
  - [ ] Admin creates consultation type → Doctor activates → Recording uses template
  - [ ] Doctor requests segment → Admin approves → Doctor uses in template → Recording extracts segment
  - [ ] Admin assigns segment to multiple consultation types → Doctors create templates → Verify no conflicts

- [ ] **Performance tests**
  - [ ] Test query performance with segment_id lookups
  - [ ] Test query performance with denormalized columns
  - [ ] Compare before/after migration performance

### Phase 8: Documentation & Deployment - 2-3 hours

- [ ] **Update API documentation**
  - [ ] Document new endpoints
  - [ ] Update existing endpoint docs
  - [ ] Add examples for new workflows

- [ ] **Update CLAUDE.md**
  - [ ] Document new schema structure
  - [ ] Update table relationships
  - [ ] Add segment ownership section
  - [ ] Update API endpoint list

- [ ] **Create deployment plan**
  - [ ] Write deployment checklist
  - [ ] Schedule maintenance window
  - [ ] Prepare rollback plan
  - [ ] Notify stakeholders

- [ ] **Post-deployment verification**
  - [ ] Run all migration scripts on production
  - [ ] Verify data integrity
  - [ ] Test critical workflows
  - [ ] Monitor for errors

---

## 📚 DETAILED IMPLEMENTATION GUIDE

### PHASE 1: Database Schema Migration (Non-Breaking)

#### 1.1 Modify segment_definitions Table

**Objective:** Transform segment_definitions into a pure master table with ownership tracking.

**Current State:**
- Has consultation_type_id and template_id foreign keys (to be removed)
- May or may not have description, default_category, is_active columns

**Target State:**
- id: UUID primary key (unique identifier)
- segment_code: TEXT (can repeat - not unique)
- segment_name: TEXT
- description: TEXT (segment description)
- prompt_section_text: TEXT (master prompt)
- schema_definition_json: JSONB (master schema)
- default_category: TEXT (CORE/ADDITIONAL/EXCLUDED)
- default_brevity_level: TEXT (concise/balanced/detailed)
- default_terminology_style: TEXT (medical_terms/simple_terms/as_spoken)
- is_active: BOOLEAN DEFAULT true (soft delete flag)
- segment_type: TEXT NOT NULL DEFAULT 'system' ('system' | 'doctor')
- doctor_id: UUID REFERENCES doctors(id) (nullable)
- created_at, updated_at: TIMESTAMP

**Migration SQL:**

```sql
-- File: backend/supabase/migrations/025_add_segment_ownership_tracking.sql

-- Add segment_type column
ALTER TABLE segment_definitions
ADD COLUMN IF NOT EXISTS segment_type TEXT DEFAULT 'system';

-- Add doctor_id column
ALTER TABLE segment_definitions
ADD COLUMN IF NOT EXISTS doctor_id UUID REFERENCES doctors(id);

-- Populate segment_type for all existing segments (default to 'system')
UPDATE segment_definitions
SET segment_type = 'system'
WHERE segment_type IS NULL;

-- Make segment_type NOT NULL
ALTER TABLE segment_definitions
ALTER COLUMN segment_type SET NOT NULL;

-- Add CHECK constraint for segment ownership
-- Either: (system segment with no doctor) OR (doctor segment with doctor_id)
ALTER TABLE segment_definitions
ADD CONSTRAINT segment_ownership_check
CHECK (
    (segment_type = 'system' AND doctor_id IS NULL) OR
    (segment_type = 'doctor' AND doctor_id IS NOT NULL)
);

-- Ensure other required columns exist
ALTER TABLE segment_definitions
ADD COLUMN IF NOT EXISTS description TEXT;

ALTER TABLE segment_definitions
ADD COLUMN IF NOT EXISTS default_category TEXT;

ALTER TABLE segment_definitions
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Add index on is_active for performance
CREATE INDEX IF NOT EXISTS idx_segment_definitions_is_active
ON segment_definitions(is_active);

-- Add index on segment_type for filtering
CREATE INDEX IF NOT EXISTS idx_segment_definitions_segment_type
ON segment_definitions(segment_type);

-- Add index on doctor_id for doctor-created segments
CREATE INDEX IF NOT EXISTS idx_segment_definitions_doctor_id
ON segment_definitions(doctor_id) WHERE doctor_id IS NOT NULL;

-- Add comment explaining the ownership model
COMMENT ON COLUMN segment_definitions.segment_type IS
'Type of segment: "system" (admin-created) or "doctor" (doctor-requested and approved)';

COMMENT ON COLUMN segment_definitions.doctor_id IS
'Doctor who requested this segment (only populated if segment_type=doctor)';

COMMENT ON COLUMN segment_definitions.is_active IS
'Soft delete flag: false means deleted or pending approval';
```

**Verification Queries:**

```sql
-- Verify segment_type distribution
SELECT segment_type, COUNT(*)
FROM segment_definitions
GROUP BY segment_type;

-- Verify CHECK constraint
-- This should FAIL (doctor segment without doctor_id)
INSERT INTO segment_definitions (segment_code, segment_name, segment_type)
VALUES ('test', 'Test', 'doctor');

-- This should SUCCEED
INSERT INTO segment_definitions
(segment_code, segment_name, segment_type, doctor_id)
VALUES ('test', 'Test', 'doctor', '<valid-doctor-uuid>');

-- Verify is_active defaults to true
SELECT is_active, COUNT(*)
FROM segment_definitions
GROUP BY is_active;
```

---

#### 1.2 Enhance consultation_type_segment_defaults (Before Rename)

**Objective:** Add segment_id and consultation_type_name for junction table functionality.

**Current State:**
- consultation_type_id: UUID FK
- segment_code: TEXT (used for matching)
- Various config fields (default_category, default_display_order, etc.)

**Target State (Pre-Rename):**
- consultation_type_id: UUID FK
- segment_id: UUID FK to segment_definitions(id) (NEW)
- segment_code: TEXT (keep for backward compatibility)
- consultation_type_name: TEXT (NEW - denormalized)
- default_category, default_display_order, default_brevity_level, default_terminology_style

**Migration SQL:**

```sql
-- File: backend/supabase/migrations/026_add_junction_table_columns.sql

-- PART 1: consultation_type_segment_defaults enhancements

-- Add segment_id column (nullable initially)
ALTER TABLE consultation_type_segment_defaults
ADD COLUMN IF NOT EXISTS segment_id UUID;

-- Populate segment_id from segment_definitions
-- Match on segment_code AND consultation_type_id (current relationship)
UPDATE consultation_type_segment_defaults ctsd
SET segment_id = (
    SELECT sd.id
    FROM segment_definitions sd
    WHERE sd.segment_code = ctsd.segment_code
    AND sd.consultation_type_id = ctsd.consultation_type_id
    LIMIT 1
);

-- For segments that don't have consultation_type_id match,
-- just match on segment_code (fallback)
UPDATE consultation_type_segment_defaults ctsd
SET segment_id = (
    SELECT sd.id
    FROM segment_definitions sd
    WHERE sd.segment_code = ctsd.segment_code
    AND sd.is_active = true
    LIMIT 1
)
WHERE segment_id IS NULL;

-- Add consultation_type_name column
ALTER TABLE consultation_type_segment_defaults
ADD COLUMN IF NOT EXISTS consultation_type_name TEXT;

-- Populate consultation_type_name from consultation_types
UPDATE consultation_type_segment_defaults ctsd
SET consultation_type_name = (
    SELECT ct.consultation_type_name
    FROM consultation_types ct
    WHERE ct.id = ctsd.consultation_type_id
);

-- Make segment_id NOT NULL (all should be populated now)
ALTER TABLE consultation_type_segment_defaults
ALTER COLUMN segment_id SET NOT NULL;

-- Add foreign key constraint
ALTER TABLE consultation_type_segment_defaults
ADD CONSTRAINT fk_consultation_type_segments_segment_id
FOREIGN KEY (segment_id) REFERENCES segment_definitions(id) ON DELETE CASCADE;

-- Add index on segment_id for lookups
CREATE INDEX IF NOT EXISTS idx_consultation_type_segment_defaults_segment_id
ON consultation_type_segment_defaults(segment_id);

-- Add index on consultation_type_name for searches
CREATE INDEX IF NOT EXISTS idx_consultation_type_segment_defaults_name
ON consultation_type_segment_defaults(consultation_type_name);

-- Add comments
COMMENT ON COLUMN consultation_type_segment_defaults.segment_id IS
'Foreign key to segment_definitions.id (canonical reference)';

COMMENT ON COLUMN consultation_type_segment_defaults.consultation_type_name IS
'Denormalized consultation type name for performance (reduces JOINs)';
```

**Verification Queries:**

```sql
-- Verify all segment_id values populated
SELECT COUNT(*)
FROM consultation_type_segment_defaults
WHERE segment_id IS NULL;
-- Should return 0

-- Verify all consultation_type_name values populated
SELECT COUNT(*)
FROM consultation_type_segment_defaults
WHERE consultation_type_name IS NULL;
-- Should return 0

-- Verify segment_id points to valid segments
SELECT ctsd.id, ctsd.segment_code, ctsd.segment_id, sd.segment_name
FROM consultation_type_segment_defaults ctsd
LEFT JOIN segment_definitions sd ON ctsd.segment_id = sd.id
WHERE sd.id IS NULL;
-- Should return 0 rows (no orphaned references)

-- Check data consistency
SELECT
    ctsd.segment_code,
    ctsd.segment_id,
    sd.segment_code as sd_segment_code,
    sd.segment_name
FROM consultation_type_segment_defaults ctsd
JOIN segment_definitions sd ON ctsd.segment_id = sd.id
LIMIT 10;
```

---

#### 1.3 Enhance template_segment_configurations (Before Rename)

**Objective:** Add segment_id and template_name for junction table functionality.

**Migration SQL:**

```sql
-- File: backend/supabase/migrations/026_add_junction_table_columns.sql (continued)

-- PART 2: template_segment_configurations enhancements

-- Add segment_id column (nullable initially)
ALTER TABLE template_segment_configurations
ADD COLUMN IF NOT EXISTS segment_id UUID;

-- Populate segment_id from segment_definitions
-- Match on segment_code only (templates can use any segment)
UPDATE template_segment_configurations tsc
SET segment_id = (
    SELECT sd.id
    FROM segment_definitions sd
    WHERE sd.segment_code = tsc.segment_code
    AND sd.is_active = true
    LIMIT 1
);

-- Add template_name column
ALTER TABLE template_segment_configurations
ADD COLUMN IF NOT EXISTS template_name TEXT;

-- Populate template_name from templates
UPDATE template_segment_configurations tsc
SET template_name = (
    SELECT t.template_name
    FROM templates t
    WHERE t.id = tsc.template_id
);

-- Make segment_id NOT NULL
ALTER TABLE template_segment_configurations
ALTER COLUMN segment_id SET NOT NULL;

-- Add foreign key constraint
ALTER TABLE template_segment_configurations
ADD CONSTRAINT fk_template_segments_segment_id
FOREIGN KEY (segment_id) REFERENCES segment_definitions(id) ON DELETE CASCADE;

-- Add index on segment_id
CREATE INDEX IF NOT EXISTS idx_template_segment_configurations_segment_id
ON template_segment_configurations(segment_id);

-- Add index on template_name
CREATE INDEX IF NOT EXISTS idx_template_segment_configurations_name
ON template_segment_configurations(template_name);

-- Add comments
COMMENT ON COLUMN template_segment_configurations.segment_id IS
'Foreign key to segment_definitions.id (canonical reference)';

COMMENT ON COLUMN template_segment_configurations.template_name IS
'Denormalized template name for performance (reduces JOINs)';
```

**Verification Queries:**

```sql
-- Verify all segment_id values populated
SELECT COUNT(*)
FROM template_segment_configurations
WHERE segment_id IS NULL;
-- Should return 0

-- Verify all template_name values populated
SELECT COUNT(*)
FROM template_segment_configurations
WHERE template_name IS NULL;
-- Should return 0

-- Verify segment_id points to valid segments
SELECT tsc.id, tsc.segment_code, tsc.segment_id, sd.segment_name
FROM template_segment_configurations tsc
LEFT JOIN segment_definitions sd ON tsc.segment_id = sd.id
WHERE sd.id IS NULL;
-- Should return 0 rows

-- Check data consistency
SELECT
    tsc.template_id,
    tsc.template_name,
    tsc.segment_code,
    tsc.segment_id,
    sd.segment_name
FROM template_segment_configurations tsc
JOIN segment_definitions sd ON tsc.segment_id = sd.id
LIMIT 10;
```

---

#### 1.4 Add Visibility Controls to consultation_types Table

**Objective:** Enable admin to control which doctors/hospitals can see consultation types.

**Migration SQL:**

```sql
-- File: backend/supabase/migrations/026_add_junction_table_columns.sql (continued)

-- PART 3: Add visibility controls to consultation_types

-- Add visibility control columns (all nullable)
ALTER TABLE consultation_types
ADD COLUMN IF NOT EXISTS visible_to_hospitals UUID[];

ALTER TABLE consultation_types
ADD COLUMN IF NOT EXISTS visible_to_doctors UUID[];

ALTER TABLE consultation_types
ADD COLUMN IF NOT EXISTS visible_to_specializations TEXT[];

-- Add indexes for array searches (GIN indexes for array contains)
CREATE INDEX IF NOT EXISTS idx_consultation_types_visible_hospitals
ON consultation_types USING GIN (visible_to_hospitals);

CREATE INDEX IF NOT EXISTS idx_consultation_types_visible_doctors
ON consultation_types USING GIN (visible_to_doctors);

CREATE INDEX IF NOT EXISTS idx_consultation_types_visible_specializations
ON consultation_types USING GIN (visible_to_specializations);

-- Add comments explaining visibility logic
COMMENT ON COLUMN consultation_types.visible_to_hospitals IS
'Array of hospital UUIDs. NULL = visible to all hospitals. Otherwise restricts visibility to listed hospitals.';

COMMENT ON COLUMN consultation_types.visible_to_doctors IS
'Array of doctor UUIDs. NULL = visible to all doctors. Otherwise restricts visibility to listed doctors.';

COMMENT ON COLUMN consultation_types.visible_to_specializations IS
'Array of specialization names. NULL = visible to all specializations. Otherwise restricts visibility to listed specializations.';
```

**Visibility Logic (Backend Implementation):**

```python
def get_visible_consultation_types(doctor_id: str):
    """
    Get consultation types visible to a specific doctor.

    Visibility Rules:
    - If ALL three arrays (hospitals, doctors, specializations) are NULL → visible to everyone
    - Otherwise, doctor must match at least ONE non-NULL array:
      - doctor_id in visible_to_doctors OR
      - doctor's hospital_id in visible_to_hospitals OR
      - doctor's specialization in visible_to_specializations
    """
    doctor = get_doctor(doctor_id)  # Get doctor's hospital_id and specialization

    query = supabase.table("consultation_types").select("*")

    # Build OR conditions
    query = query.or_(
        f"visible_to_hospitals.is.null,"
        f"visible_to_doctors.is.null,"
        f"visible_to_specializations.is.null,"
        f"visible_to_doctors.cs.{{{doctor_id}}},"  # cs = contains
        f"visible_to_hospitals.cs.{{{doctor.hospital_id}}},"
        f"visible_to_specializations.cs.{{{doctor.specialization}}}"
    )

    return query.execute().data
```

---

#### 1.5 Modify templates Table

**Objective:** Enforce doctor ownership and simplify template management.

**Migration SQL:**

```sql
-- File: backend/supabase/migrations/027_migrate_template_ownership.sql

-- Rename created_by_doctor_id to doctor_id for clarity
ALTER TABLE templates
RENAME COLUMN created_by_doctor_id TO doctor_id;

-- Add unique constraint: one template code per doctor
ALTER TABLE templates
ADD CONSTRAINT templates_doctor_code_unique
UNIQUE (doctor_id, template_code);

-- Ensure is_active column exists
ALTER TABLE templates
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Add index on is_active for filtering
CREATE INDEX IF NOT EXISTS idx_templates_is_active
ON templates(is_active);

-- Add index on doctor_id for lookups
CREATE INDEX IF NOT EXISTS idx_templates_doctor_id
ON templates(doctor_id);

-- Add comments
COMMENT ON COLUMN templates.doctor_id IS
'Doctor who owns this template (1 template = 1 doctor)';

COMMENT ON COLUMN templates.is_active IS
'Whether this template is active. Replaces doctor_active_templates functionality.';
```

**Verification Queries:**

```sql
-- Verify unique constraint works
-- This should FAIL if doctor already has template with same code
INSERT INTO templates (doctor_id, template_code, template_name, consultation_type_id)
VALUES ('<doctor-uuid>', 'existing-code', 'Duplicate Template', '<type-uuid>');

-- Check for duplicate templates that would violate constraint
SELECT doctor_id, template_code, COUNT(*)
FROM templates
GROUP BY doctor_id, template_code
HAVING COUNT(*) > 1;
-- Should return 0 rows
```

---

#### 1.6 Modify doctor_segment_configurations Table

**Objective:** Remove dependency on doctor_active_templates, link directly to templates.

**Migration SQL:**

```sql
-- File: backend/supabase/migrations/027_migrate_template_ownership.sql (continued)

-- Add template_id column (nullable initially for migration)
ALTER TABLE doctor_segment_configurations
ADD COLUMN IF NOT EXISTS template_id UUID;

-- Populate template_id from doctor_active_templates (migration data)
UPDATE doctor_segment_configurations dsc
SET template_id = dat.template_id
FROM doctor_active_templates dat
WHERE dsc.active_template_id = dat.id;

-- Make template_id NOT NULL
ALTER TABLE doctor_segment_configurations
ALTER COLUMN template_id SET NOT NULL;

-- Add foreign key constraint
ALTER TABLE doctor_segment_configurations
ADD CONSTRAINT fk_doctor_segment_config_template
FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE;

-- Drop active_template_id column (no longer needed)
ALTER TABLE doctor_segment_configurations
DROP COLUMN IF EXISTS active_template_id;

-- Update unique constraint
ALTER TABLE doctor_segment_configurations
DROP CONSTRAINT IF EXISTS doctor_segment_configurations_unique;

ALTER TABLE doctor_segment_configurations
ADD CONSTRAINT doctor_segment_configurations_unique
UNIQUE (doctor_id, template_id, segment_code);

-- Add index on template_id
CREATE INDEX IF NOT EXISTS idx_doctor_segment_config_template_id
ON doctor_segment_configurations(template_id);
```

**Verification Queries:**

```sql
-- Verify all template_id values populated
SELECT COUNT(*)
FROM doctor_segment_configurations
WHERE template_id IS NULL;
-- Should return 0

-- Verify template_id points to valid templates
SELECT dsc.id, dsc.template_id, t.template_name
FROM doctor_segment_configurations dsc
LEFT JOIN templates t ON dsc.template_id = t.id
WHERE t.id IS NULL;
-- Should return 0 rows
```

---

#### 1.7 Backup All Affected Tables

**Before executing any migrations, create comprehensive backups:**

```bash
# Backup script (run from backend/ directory)

timestamp=$(date +%Y%m%d_%H%M%S)
backup_dir="supabase/backups/${timestamp}"
mkdir -p "$backup_dir"

# Export each table as JSON
echo "Creating backups in $backup_dir..."

tables=(
    "segment_definitions"
    "consultation_type_segment_defaults"
    "template_segment_configurations"
    "templates"
    "doctor_active_templates"
    "doctor_segment_configurations"
    "consultation_types"
)

for table in "${tables[@]}"; do
    echo "Backing up $table..."
    # Use Supabase CLI or direct SQL dump
    # This is pseudocode - adjust for your setup
    supabase db dump --table "$table" > "$backup_dir/${table}.sql"
done

echo "Backup complete: $backup_dir"
```

**SQL Backup (Alternative):**

```sql
-- Export to CSV or create backup tables
CREATE TABLE segment_definitions_backup_20251122 AS
SELECT * FROM segment_definitions;

CREATE TABLE consultation_type_segment_defaults_backup_20251122 AS
SELECT * FROM consultation_type_segment_defaults;

CREATE TABLE template_segment_configurations_backup_20251122 AS
SELECT * FROM template_segment_configurations;

CREATE TABLE templates_backup_20251122 AS
SELECT * FROM templates;

CREATE TABLE doctor_active_templates_backup_20251122 AS
SELECT * FROM doctor_active_templates;

CREATE TABLE doctor_segment_configurations_backup_20251122 AS
SELECT * FROM doctor_segment_configurations;
```

---

### PHASE 2: Data Migration Scripts

All Phase 2 work is captured in the migration scripts created in Phase 1. See:
- `025_add_segment_ownership_tracking.sql`
- `026_add_junction_table_columns.sql`
- `027_migrate_template_ownership.sql`

**Execution Order:**

```bash
# Run migrations in sequence
psql $DATABASE_URL -f backend/supabase/migrations/025_add_segment_ownership_tracking.sql
psql $DATABASE_URL -f backend/supabase/migrations/026_add_junction_table_columns.sql
psql $DATABASE_URL -f backend/supabase/migrations/027_migrate_template_ownership.sql

# Or use Supabase CLI
supabase db push
```

---

### PHASE 3: Table Renames (BREAKING CHANGE)

**⚠️ REQUIRES MAINTENANCE WINDOW (5-10 minutes downtime)**

#### 3.1 Schedule Maintenance Window

**Pre-Deployment Checklist:**

- [ ] Notify all stakeholders 24 hours in advance
- [ ] Schedule during low-traffic period (e.g., 2-4 AM local time)
- [ ] Prepare rollback plan (backup restoration procedure)
- [ ] Test migration on staging environment
- [ ] Have emergency contact list ready
- [ ] Set up monitoring alerts

**Maintenance Window Steps:**

1. Enable maintenance mode (if applicable)
2. Stop backend services (to prevent in-flight requests)
3. Execute table rename migration
4. Deploy updated backend code with new table names
5. Restart backend services
6. Verify critical workflows
7. Disable maintenance mode

---

#### 3.2 Table Rename Migration Script

```sql
-- File: backend/supabase/migrations/028_rename_junction_tables.sql

-- ⚠️ BREAKING CHANGE - COORDINATE WITH BACKEND DEPLOYMENT

-- Rename consultation_type_segment_defaults → consultation_type_segments
ALTER TABLE consultation_type_segment_defaults
RENAME TO consultation_type_segments;

-- Rename template_segment_configurations → template_segments
ALTER TABLE template_segment_configurations
RENAME TO template_segments;

-- Update primary key constraint names (for clarity)
ALTER TABLE consultation_type_segments
DROP CONSTRAINT IF EXISTS consultation_type_segment_defaults_pkey;

ALTER TABLE consultation_type_segments
ADD CONSTRAINT consultation_type_segments_pkey PRIMARY KEY (id);

ALTER TABLE template_segments
DROP CONSTRAINT IF EXISTS template_segment_configurations_pkey;

ALTER TABLE template_segments
ADD CONSTRAINT template_segments_pkey PRIMARY KEY (id);

-- Update unique constraints
ALTER TABLE consultation_type_segments
DROP CONSTRAINT IF EXISTS consultation_type_segment_defaults_unique;

ALTER TABLE consultation_type_segments
ADD CONSTRAINT consultation_type_segments_unique
UNIQUE (consultation_type_id, segment_id);

ALTER TABLE template_segments
DROP CONSTRAINT IF EXISTS template_segment_configurations_unique;

ALTER TABLE template_segments
ADD CONSTRAINT template_segments_unique
UNIQUE (template_id, segment_id);

-- Rename indexes (optional but recommended for consistency)
ALTER INDEX IF EXISTS idx_consultation_type_segment_defaults_segment_id
RENAME TO idx_consultation_type_segments_segment_id;

ALTER INDEX IF EXISTS idx_consultation_type_segment_defaults_name
RENAME TO idx_consultation_type_segments_name;

ALTER INDEX IF EXISTS idx_template_segment_configurations_segment_id
RENAME TO idx_template_segments_segment_id;

ALTER INDEX IF EXISTS idx_template_segment_configurations_name
RENAME TO idx_template_segments_name;

-- Add comments to new table names
COMMENT ON TABLE consultation_type_segments IS
'Junction table: Maps segments to consultation types with type-specific configurations';

COMMENT ON TABLE template_segments IS
'Junction table: Maps segments to doctor templates with template-specific configurations';
```

**Deployment Coordination:**

```bash
# Step 1: Stop backend services
pm2 stop all  # or systemctl stop your-backend-service

# Step 2: Run table rename migration
psql $DATABASE_URL -f backend/supabase/migrations/028_rename_junction_tables.sql

# Step 3: Deploy updated backend code (with new table names)
git pull origin main
pip install -r requirements.txt  # if dependencies changed
pm2 restart all  # or systemctl start your-backend-service

# Step 4: Verify critical endpoints
curl http://localhost:8000/api/v1/summary/consultation-types
curl http://localhost:8000/api/v1/doctors/{doctor-id}/templates
```

---

### PHASE 4: Schema Cleanup

#### 4.1 Remove Deprecated Columns and Tables

```sql
-- File: backend/supabase/migrations/029_cleanup_deprecated_columns.sql

-- Remove foreign keys from segment_definitions
-- (These are now handled by junction tables)
ALTER TABLE segment_definitions
DROP COLUMN IF EXISTS consultation_type_id CASCADE;

ALTER TABLE segment_definitions
DROP COLUMN IF EXISTS template_id CASCADE;

-- Drop doctor_active_templates table completely
-- (Functionality replaced by templates.is_active flag)
DROP TABLE IF EXISTS doctor_active_templates CASCADE;

-- Verify segment_definitions now only has master columns
-- Run this to see remaining columns:
-- SELECT column_name, data_type
-- FROM information_schema.columns
-- WHERE table_name = 'segment_definitions';
--
-- Expected columns:
-- id, segment_code, segment_name, description, prompt_section_text,
-- schema_definition_json, default_category, default_brevity_level,
-- default_terminology_style, is_active, segment_type, doctor_id,
-- created_at, updated_at
```

**Verification Queries:**

```sql
-- Verify consultation_type_id removed from segment_definitions
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'segment_definitions'
AND column_name = 'consultation_type_id';
-- Should return 0 rows

-- Verify template_id removed from segment_definitions
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'segment_definitions'
AND column_name = 'template_id';
-- Should return 0 rows

-- Verify doctor_active_templates table dropped
SELECT table_name
FROM information_schema.tables
WHERE table_name = 'doctor_active_templates';
-- Should return 0 rows
```

---

#### 4.2 Update Edge Functions (RPC Functions)

**Objective:** Update all PostgreSQL functions that reference the old table names and schema.

**Affected Functions:**
1. `apply_template_to_doctor()` - Template application logic
2. `get_doctor_segment_configuration()` - Segment configuration retrieval
3. `validate_segment_configuration()` - Configuration validation

---

**4.2.1 Update apply_template_to_doctor() Function**

This function needs to be either REMOVED or completely rewritten since `doctor_active_templates` table is being dropped.

**Option 1: REMOVE (Recommended)**

Since the new architecture doesn't use `doctor_active_templates`, this function is no longer needed.

```sql
-- File: backend/supabase/migrations/030_update_edge_functions.sql

-- Drop the function since doctor_active_templates is being removed
DROP FUNCTION IF EXISTS public.apply_template_to_doctor(uuid, uuid, uuid);

COMMENT ON SCHEMA public IS 'apply_template_to_doctor function removed in migration 030 due to doctor_active_templates table removal. Template application now handled at application level.';
```

**Option 2: REWRITE (if still needed)**

If you want to keep a simpler version that copies from template to doctor config:

```sql
-- File: backend/supabase/migrations/030_update_edge_functions.sql

CREATE OR REPLACE FUNCTION public.apply_template_to_doctor(
    p_doctor_id UUID,
    p_template_id UUID
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    -- Delete existing doctor configurations for this template
    DELETE FROM doctor_segment_configurations
    WHERE doctor_id = p_doctor_id
      AND template_id = p_template_id;

    -- Copy template configurations to doctor configurations
    -- Using NEW table name and segment_id
    INSERT INTO doctor_segment_configurations (
        doctor_id,
        template_id,
        segment_code,
        segment_id,  -- NEW: Use segment_id
        category,
        display_order,
        brevity_level,
        terminology_style
    )
    SELECT
        p_doctor_id,
        p_template_id,
        ts.segment_code,
        ts.segment_id,  -- NEW: Include segment_id
        ts.category,
        ts.display_order,
        ts.brevity_level,
        ts.terminology_style
    FROM template_segments ts  -- NEW: Updated table name
    INNER JOIN segment_definitions sd ON ts.segment_id = sd.id
    WHERE ts.template_id = p_template_id
    AND sd.is_active = TRUE;  -- NEW: Only copy active segments
END;
$$;

COMMENT ON FUNCTION public.apply_template_to_doctor(uuid, uuid) IS
'Copy template segment configurations to doctor''s configuration.

Updated in migration 030 to:
- Remove active_template_id parameter (doctor_active_templates removed)
- Use template_segments table (renamed from template_segment_configurations)
- Use segment_id in addition to segment_code
- Filter by is_active segments only

Parameters:
  p_doctor_id: Doctor UUID
  p_template_id: Template UUID (from templates.id)';
```

---

**4.2.2 Update get_doctor_segment_configuration() Function**

This function requires a major rewrite since it references multiple deprecated tables and columns.

```sql
-- File: backend/supabase/migrations/030_update_edge_functions.sql

CREATE OR REPLACE FUNCTION public.get_doctor_segment_configuration(
    p_doctor_id UUID,
    p_consultation_type_id UUID,
    p_template_id UUID DEFAULT NULL,  -- NEW: Changed from p_active_template_id
    p_mode VARCHAR DEFAULT 'full'
) RETURNS TABLE(
    segment_code VARCHAR,
    segment_name VARCHAR,
    prompt_section_text TEXT,
    schema_definition_json JSONB,
    category VARCHAR,
    display_order INTEGER,
    brevity_level VARCHAR,
    terminology_style VARCHAR,
    is_required BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (sd.segment_code)
        sd.segment_code::VARCHAR,
        sd.segment_name::VARCHAR,

        -- Prompt section: doctor-specific → segment-default
        COALESCE(
            dsc.custom_prompt_section,
            sd.prompt_section_text
        ),

        -- Schema: doctor-specific → segment-default
        COALESCE(
            dsc.custom_schema_json,
            sd.schema_definition_json
        ),

        -- Category: doctor-specific → template → consultation type → segment-default
        COALESCE(
            dsc.category,
            ts.category,
            cts.default_category,
            sd.default_category
        )::VARCHAR AS category,

        -- Display order: doctor-specific → template → consultation type → segment-default
        COALESCE(
            dsc.display_order,
            ts.display_order,
            cts.default_display_order,
            sd.display_order
        ) AS display_order,

        -- Brevity level: doctor-specific → template → consultation type → segment-default
        COALESCE(
            dsc.brevity_level,
            ts.brevity_level,
            cts.default_brevity_level,
            sd.default_brevity_level
        )::VARCHAR AS brevity_level,

        -- Terminology style: doctor-specific → template → consultation type → segment-default
        COALESCE(
            dsc.terminology_style,
            ts.terminology_style,
            cts.default_terminology_style,
            sd.default_terminology_style
        )::VARCHAR AS terminology_style,

        -- Is required: always from segment definition
        sd.is_required AS is_required

    FROM segment_definitions sd

    -- NEW: Join via consultation_type_segments junction table
    LEFT JOIN consultation_type_segments cts
        ON cts.segment_id = sd.id
        AND cts.consultation_type_id = p_consultation_type_id

    -- NEW: Join doctor's template-specific config (if template provided)
    LEFT JOIN doctor_segment_configurations dsc
        ON dsc.segment_id = sd.id
        AND dsc.doctor_id = p_doctor_id
        AND dsc.template_id = p_template_id
        AND p_template_id IS NOT NULL

    -- NEW: Join template segment configuration (using template_segments)
    LEFT JOIN template_segments ts
        ON ts.segment_id = sd.id
        AND ts.template_id = p_template_id
        AND p_template_id IS NOT NULL

    WHERE sd.is_active = TRUE
        AND (
            -- Segment is assigned to this consultation type via junction table
            cts.segment_id IS NOT NULL
            OR
            -- OR segment is in doctor's template (template-specific segments)
            ts.segment_id IS NOT NULL
        )
        AND (
            -- Mode filter: include segments based on mode
            p_mode = 'full' OR
            (p_mode = 'core' AND COALESCE(
                dsc.category,
                ts.category,
                cts.default_category,
                sd.default_category
            ) = 'CORE') OR
            (p_mode = 'additional' AND COALESCE(
                dsc.category,
                ts.category,
                cts.default_category,
                sd.default_category
            ) = 'ADDITIONAL')
        )
        -- ALWAYS exclude 'EXCLUDED' segments
        AND COALESCE(
            dsc.category,
            ts.category,
            cts.default_category,
            sd.default_category
        ) != 'EXCLUDED'

    ORDER BY sd.segment_code,
        COALESCE(
            dsc.display_order,
            ts.display_order,
            cts.default_display_order,
            sd.display_order
        );
END;
$$;

COMMENT ON FUNCTION public.get_doctor_segment_configuration(uuid, uuid, uuid, varchar) IS
'Returns segment configuration for a doctor with template-based hierarchy.

MAJOR UPDATE in migration 030:
- Removed doctor_active_templates dependency
- Changed p_active_template_id → p_template_id (direct template reference)
- Uses consultation_type_segments junction table
- Uses template_segments junction table (renamed from template_segment_configurations)
- Uses segment_id for all joins (canonical reference)
- Filters by is_active segments only

Parameters:
  p_doctor_id: Doctor UUID
  p_consultation_type_id: Consultation type UUID (OP, DISCHARGE, RESPIRATORY)
  p_template_id: Template ID (from templates.id) - optional
  p_mode: Segment filter (''CORE'' | ''ADDITIONAL'' | ''full'')

Configuration Hierarchy (highest to lowest priority):
  1. Doctor''s template-specific config (doctor_segment_configurations)
  2. Template default (template_segments)
  3. Consultation type default (consultation_type_segments)
  4. Segment default (segment_definitions)';
```

---

**4.2.3 Update validate_segment_configuration() Function**

This function needs minor updates for new schema.

```sql
-- File: backend/supabase/migrations/030_update_edge_functions.sql

CREATE OR REPLACE FUNCTION public.validate_segment_configuration(
    p_doctor_id UUID
) RETURNS TABLE(
    is_valid BOOLEAN,
    error_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    required_segments_count INTEGER;
    core_required_segments_count INTEGER;
BEGIN
    -- Check that all required segments are present and in CORE category
    SELECT COUNT(*) INTO required_segments_count
    FROM segment_definitions
    WHERE is_required = TRUE
    AND is_active = TRUE;  -- Only count active segments

    SELECT COUNT(*) INTO core_required_segments_count
    FROM segment_definitions sd
    LEFT JOIN doctor_segment_configurations dsc
        ON dsc.segment_id = sd.id  -- NEW: Use segment_id instead of segment_code
        AND dsc.doctor_id = p_doctor_id
    WHERE sd.is_required = TRUE
        AND sd.is_active = TRUE
        AND COALESCE(dsc.category, sd.default_category) = 'CORE';

    IF core_required_segments_count < required_segments_count THEN
        RETURN QUERY SELECT FALSE, 'Required segments must be in CORE category for clinical safety'::TEXT;
    ELSE
        RETURN QUERY SELECT TRUE, NULL::TEXT;
    END IF;
END;
$$;

COMMENT ON FUNCTION public.validate_segment_configuration(uuid) IS
'Validates that all required segments are in CORE category for a doctor.

Updated in migration 030 to:
- Use segment_id for joins (instead of segment_code)
- Filter by is_active segments only

Parameters:
  p_doctor_id: Doctor UUID

Returns:
  is_valid: TRUE if configuration is valid
  error_message: NULL if valid, error description if invalid';
```

---

**4.2.4 Verification Queries for Edge Functions**

```sql
-- Test apply_template_to_doctor (if kept)
-- Should copy segments from template to doctor config
SELECT public.apply_template_to_doctor(
    '<doctor-uuid>'::UUID,
    '<template-uuid>'::UUID
);

-- Verify segments copied
SELECT COUNT(*)
FROM doctor_segment_configurations
WHERE doctor_id = '<doctor-uuid>'::UUID
AND template_id = '<template-uuid>'::UUID;


-- Test get_doctor_segment_configuration
-- Should return segments for doctor's template
SELECT *
FROM public.get_doctor_segment_configuration(
    '<doctor-uuid>'::UUID,
    '<consultation-type-uuid>'::UUID,
    '<template-uuid>'::UUID,
    'full'
);


-- Test validate_segment_configuration
-- Should return is_valid=TRUE if all required segments in CORE
SELECT *
FROM public.validate_segment_configuration('<doctor-uuid>'::UUID);
```

---

#### 4.3 Update Database Triggers

**Objective:** Remove triggers for deleted tables and verify remaining triggers work with renamed tables.

**4.3.1 Remove Deprecated Triggers**

```sql
-- File: backend/supabase/migrations/031_update_triggers.sql

-- Drop trigger for doctor_active_templates (table being removed)
DROP TRIGGER IF EXISTS update_doctor_active_templates_updated_at
ON public.doctor_active_templates;

-- Verify no orphaned triggers remain
-- This query should return 0 rows for doctor_active_templates
SELECT
    t.tgname as trigger_name,
    c.relname as table_name
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = 'public'
AND c.relname = 'doctor_active_templates';
-- Should return 0 rows after cleanup
```

**4.3.2 Verify Existing Triggers After Table Renames**

PostgreSQL triggers are not automatically renamed when tables are renamed, but they continue to work. However, it's good practice to rename them for consistency.

```sql
-- File: backend/supabase/migrations/031_update_triggers.sql

-- Note: Triggers created on renamed tables automatically work with new table names
-- The following verification queries ensure all triggers are functioning

-- List all triggers on renamed tables
SELECT
    t.tgname as trigger_name,
    c.relname as table_name,
    p.proname as function_name
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
JOIN pg_proc p ON t.tgfoid = p.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = 'public'
AND c.relname IN (
    'consultation_type_segments',  -- Renamed from consultation_type_segment_defaults
    'template_segments',           -- Renamed from template_segment_configurations
    'segment_definitions',
    'templates',
    'consultation_types'
)
ORDER BY c.relname, t.tgname;


-- Expected triggers (these should all exist and work):
-- consultation_types: update_consultation_types_updated_at
-- segment_definitions: update_segment_definitions_updated_at
-- templates: update_templates_updated_at
-- doctor_segment_configurations: update_doctor_segment_configurations_updated_at
```

**Note:** If no triggers exist on the junction tables, you may want to add `updated_at` triggers:

```sql
-- Optional: Add updated_at triggers to junction tables if they have updated_at columns

-- For consultation_type_segments (if it has updated_at column)
CREATE TRIGGER update_consultation_type_segments_updated_at
    BEFORE UPDATE ON public.consultation_type_segments
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- For template_segments (if it has updated_at column)
CREATE TRIGGER update_template_segments_updated_at
    BEFORE UPDATE ON public.template_segments
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();
```

---

#### 4.4 Update and Create Indexes

**Objective:** Remove deprecated indexes, rename indexes for consistency, and create new indexes for performance.

**4.4.1 Drop Deprecated Indexes**

```sql
-- File: backend/supabase/migrations/032_update_indexes.sql

-- Drop indexes on segment_definitions for columns being removed
DROP INDEX IF EXISTS public.idx_segment_definitions_consultation_type;
DROP INDEX IF EXISTS public.idx_segment_definitions_template_id;

-- These indexes referenced consultation_type_id and template_id columns
-- which are being removed from segment_definitions
```

**4.4.2 Rename Indexes for Renamed Tables**

```sql
-- File: backend/supabase/migrations/032_update_indexes.sql

-- Rename indexes for consultation_type_segment_defaults → consultation_type_segments
ALTER INDEX IF EXISTS public.idx_type_segment_defaults_type
    RENAME TO idx_consultation_type_segments_type_id;

ALTER INDEX IF EXISTS public.idx_type_segment_defaults_segment
    RENAME TO idx_consultation_type_segments_segment_code;

-- Rename indexes for template_segment_configurations → template_segments
ALTER INDEX IF EXISTS public.idx_template_segment_template_id
    RENAME TO idx_template_segments_template_id;

ALTER INDEX IF EXISTS public.idx_template_segment_category
    RENAME TO idx_template_segments_category;
```

**4.4.3 Create New Indexes for Segment Ownership**

```sql
-- File: backend/supabase/migrations/032_update_indexes.sql

-- Indexes for new segment ownership columns
CREATE INDEX IF NOT EXISTS idx_segment_definitions_segment_type
    ON public.segment_definitions(segment_type);

CREATE INDEX IF NOT EXISTS idx_segment_definitions_doctor_id
    ON public.segment_definitions(doctor_id)
    WHERE doctor_id IS NOT NULL;  -- Partial index for doctor segments only

-- Composite index for finding doctor's requested segments
CREATE INDEX IF NOT EXISTS idx_segment_definitions_doctor_active
    ON public.segment_definitions(doctor_id, is_active)
    WHERE segment_type = 'doctor';
```

**4.4.4 Create Indexes on New Foreign Keys (segment_id)**

```sql
-- File: backend/supabase/migrations/032_update_indexes.sql

-- Indexes on segment_id in junction tables (for join performance)
CREATE INDEX IF NOT EXISTS idx_consultation_type_segments_segment_id
    ON public.consultation_type_segments(segment_id);

CREATE INDEX IF NOT EXISTS idx_template_segments_segment_id
    ON public.template_segments(segment_id);

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_consultation_type_segments_type_segment
    ON public.consultation_type_segments(consultation_type_id, segment_id);

CREATE INDEX IF NOT EXISTS idx_template_segments_template_segment
    ON public.template_segments(template_id, segment_id);
```

**4.4.5 Create Indexes on Denormalized Columns**

```sql
-- File: backend/supabase/migrations/032_update_indexes.sql

-- Indexes on denormalized name columns (for search/filter performance)
CREATE INDEX IF NOT EXISTS idx_consultation_type_segments_name
    ON public.consultation_type_segments(consultation_type_name);

CREATE INDEX IF NOT EXISTS idx_template_segments_name
    ON public.template_segments(template_name);

-- Text search indexes (if doing text searches on names)
CREATE INDEX IF NOT EXISTS idx_consultation_type_segments_name_trgm
    ON public.consultation_type_segments
    USING gin(consultation_type_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_template_segments_name_trgm
    ON public.template_segments
    USING gin(template_name gin_trgm_ops);
```

**4.4.6 Create Indexes on Visibility Arrays**

```sql
-- File: backend/supabase/migrations/032_update_indexes.sql

-- GIN indexes for array containment queries on visibility controls
CREATE INDEX IF NOT EXISTS idx_consultation_types_visible_hospitals
    ON public.consultation_types USING GIN(visible_to_hospitals);

CREATE INDEX IF NOT EXISTS idx_consultation_types_visible_doctors
    ON public.consultation_types USING GIN(visible_to_doctors);

CREATE INDEX IF NOT EXISTS idx_consultation_types_visible_specializations
    ON public.consultation_types USING GIN(visible_to_specializations);
```

**4.4.7 Verify Index Performance**

```sql
-- Analyze tables to update statistics after index creation
ANALYZE public.segment_definitions;
ANALYZE public.consultation_type_segments;
ANALYZE public.template_segments;
ANALYZE public.consultation_types;

-- Check index usage (run this query after system has been running)
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
AND tablename IN (
    'segment_definitions',
    'consultation_type_segments',
    'template_segments',
    'templates',
    'consultation_types'
)
ORDER BY tablename, indexname;

-- Identify unused indexes (idx_scan = 0 after sufficient runtime)
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
AND idx_scan = 0
AND tablename IN (
    'segment_definitions',
    'consultation_type_segments',
    'template_segments'
)
ORDER BY tablename, indexname;
```

---

#### 4.5 Complete Migration Script Summary

**All Phase 4 migration scripts:**

1. `029_cleanup_deprecated_columns.sql` - Remove deprecated columns and tables
2. `030_update_edge_functions.sql` - Update all RPC functions
3. `031_update_triggers.sql` - Remove/update triggers
4. `032_update_indexes.sql` - Update and create indexes

**Execution Order:**

```bash
# 1. Cleanup (drops columns, tables)
psql $DATABASE_URL -f backend/supabase/migrations/029_cleanup_deprecated_columns.sql

# 2. Update edge functions (must be after cleanup since functions reference tables)
psql $DATABASE_URL -f backend/supabase/migrations/030_update_edge_functions.sql

# 3. Update triggers
psql $DATABASE_URL -f backend/supabase/migrations/031_update_triggers.sql

# 4. Update indexes (last, after all schema changes complete)
psql $DATABASE_URL -f backend/supabase/migrations/032_update_indexes.sql

# 5. Analyze all affected tables
psql $DATABASE_URL -c "ANALYZE public.segment_definitions;"
psql $DATABASE_URL -c "ANALYZE public.consultation_type_segments;"
psql $DATABASE_URL -c "ANALYZE public.template_segments;"
psql $DATABASE_URL -c "ANALYZE public.consultation_types;"
psql $DATABASE_URL -c "ANALYZE public.templates;"
```

---

### PHASE 5: Backend Code Updates

#### 5.1 Update backend/services/supabase_service.py

**5.1.1 Global Find/Replace Operations**

Before making function-level changes, perform these global replacements:

```python
# Find/Replace #1
# OLD: "template_segment_configurations"
# NEW: "template_segments"
# Occurrences: ~11+

# Find/Replace #2
# OLD: "consultation_type_segment_defaults"
# NEW: "consultation_type_segments"
# Occurrences: ~8+
```

**5.1.2 Update get_template_configuration() Function**

```python
# Location: ~line 1490

# BEFORE
def get_template_configuration(template_id: str):
    """Get all segment configurations for a template"""
    response = supabase.table("template_segment_configurations")\
        .select("*")\
        .eq("template_id", template_id)\
        .execute()
    return response.data

# AFTER
def get_template_configuration(template_id: str):
    """Get all segment configurations for a template"""
    response = supabase.table("template_segments")\
        .select("""
            *,
            segment_definitions!inner(
                id,
                segment_code,
                segment_name,
                prompt_section_text,
                schema_definition_json,
                is_active
            )
        """)\
        .eq("template_id", template_id)\
        .eq("segment_definitions.is_active", True)\
        .execute()
    return response.data
```

**5.1.3 Update update_template_segment_config() Function**

```python
# Location: ~line 1970-2008

# BEFORE
def update_template_segment_config(
    template_id: str,
    segment_code: str,
    category: str = None,
    display_order: int = None,
    brevity_level: str = None,
    terminology_style: str = None
):
    """Update a segment configuration for a template"""
    update_data = {}
    if category is not None:
        update_data["category"] = category
    if display_order is not None:
        update_data["display_order"] = display_order
    if brevity_level is not None:
        update_data["brevity_level"] = brevity_level
    if terminology_style is not None:
        update_data["terminology_style"] = terminology_style

    response = supabase.table("template_segment_configurations")\
        .update(update_data)\
        .eq("template_id", template_id)\
        .eq("segment_code", segment_code)\
        .execute()

    return response.data

# AFTER
def update_template_segment_config(
    template_id: str,
    segment_code: str,
    category: str = None,
    display_order: int = None,
    brevity_level: str = None,
    terminology_style: str = None
):
    """Update a segment configuration for a template"""
    # Lookup segment_id from segment_code
    segment = supabase.table("segment_definitions")\
        .select("id, segment_name")\
        .eq("segment_code", segment_code)\
        .eq("is_active", True)\
        .limit(1)\
        .execute()

    if not segment.data:
        raise ValueError(f"Segment {segment_code} not found or not active")

    segment_id = segment.data[0]["id"]

    # Get template_name for denormalization
    template = supabase.table("templates")\
        .select("template_name")\
        .eq("id", template_id)\
        .single()\
        .execute()

    template_name = template.data["template_name"]

    # Build update data
    update_data = {
        "segment_id": segment_id,  # Ensure segment_id is set
        "template_name": template_name  # Update denormalized name
    }

    if category is not None:
        update_data["category"] = category
    if display_order is not None:
        update_data["display_order"] = display_order
    if brevity_level is not None:
        update_data["brevity_level"] = brevity_level
    if terminology_style is not None:
        update_data["terminology_style"] = terminology_style

    response = supabase.table("template_segments")\
        .update(update_data)\
        .eq("template_id", template_id)\
        .eq("segment_code", segment_code)\
        .execute()

    return response.data
```

**5.1.4 Create create_segment_from_doctor_request() Function (NEW)**

```python
def create_segment_from_doctor_request(
    doctor_id: str,
    segment_code: str,
    segment_name: str,
    description: str = None,
    prompt_section_text: str = None,
    schema_definition_json: dict = None,
    default_category: str = "ADDITIONAL",
    default_brevity_level: str = "balanced",
    default_terminology_style: str = "medical_terms",
    approved: bool = False
):
    """
    Create a doctor-requested segment (pending or approved).

    Args:
        doctor_id: UUID of requesting doctor
        segment_code: Code for the segment
        segment_name: Human-readable name
        description: Optional description
        prompt_section_text: Prompt text for AI extraction
        schema_definition_json: JSON schema for extraction
        default_category: CORE/ADDITIONAL/EXCLUDED
        default_brevity_level: concise/balanced/detailed
        default_terminology_style: medical_terms/simple_terms/as_spoken
        approved: If True, sets is_active=True; if False, pending approval

    Returns:
        Created segment record
    """
    segment_data = {
        "segment_code": segment_code,
        "segment_name": segment_name,
        "description": description,
        "prompt_section_text": prompt_section_text,
        "schema_definition_json": schema_definition_json,
        "default_category": default_category,
        "default_brevity_level": default_brevity_level,
        "default_terminology_style": default_terminology_style,
        "segment_type": "doctor",  # Always 'doctor' for this function
        "doctor_id": doctor_id,  # Required for doctor segments
        "is_active": approved  # false = pending approval, true = approved
    }

    response = supabase.table("segment_definitions")\
        .insert(segment_data)\
        .execute()

    return response.data[0] if response.data else None
```

**5.1.5 Create approve_doctor_segment() Function (NEW)**

```python
def approve_doctor_segment(
    segment_id: str,
    scope: str,  # 'global' | 'consultation_types' | 'template'
    scope_ids: list[str] = None  # List of consultation_type_ids or [template_id]
):
    """
    Admin approves a doctor-requested segment and assigns its scope.

    Args:
        segment_id: UUID of the segment to approve
        scope: 'global' (all types), 'consultation_types' (specific types), 'template' (specific template)
        scope_ids: List of IDs based on scope type

    Returns:
        Updated segment record
    """
    # 1. Activate the segment
    segment = supabase.table("segment_definitions")\
        .update({"is_active": True})\
        .eq("id", segment_id)\
        .execute()

    if not segment.data:
        raise ValueError(f"Segment {segment_id} not found")

    segment_data = segment.data[0]

    # 2. Assign to scope
    if scope == "global":
        # Global scope: No junction table entry needed
        # Segment is available to all consultation types
        pass

    elif scope == "consultation_types":
        # Assign to specific consultation types
        if not scope_ids:
            raise ValueError("scope_ids required for consultation_types scope")

        for ct_id in scope_ids:
            # Get consultation type name
            ct = supabase.table("consultation_types")\
                .select("consultation_type_name")\
                .eq("id", ct_id)\
                .single()\
                .execute()

            # Insert into consultation_type_segments junction table
            junction_data = {
                "consultation_type_id": ct_id,
                "segment_id": segment_id,
                "segment_code": segment_data["segment_code"],
                "consultation_type_name": ct.data["consultation_type_name"],
                "default_category": segment_data["default_category"],
                "default_display_order": 999,  # Add to end by default
                "default_brevity_level": segment_data["default_brevity_level"],
                "default_terminology_style": segment_data["default_terminology_style"]
            }

            supabase.table("consultation_type_segments")\
                .insert(junction_data)\
                .execute()

    elif scope == "template":
        # Assign to specific template only
        if not scope_ids or len(scope_ids) != 1:
            raise ValueError("Exactly one template_id required for template scope")

        template_id = scope_ids[0]

        # Get template name
        template = supabase.table("templates")\
            .select("template_name")\
            .eq("id", template_id)\
            .single()\
            .execute()

        # Insert into template_segments junction table
        junction_data = {
            "template_id": template_id,
            "segment_id": segment_id,
            "segment_code": segment_data["segment_code"],
            "template_name": template.data["template_name"],
            "category": segment_data["default_category"],
            "display_order": 999,
            "brevity_level": segment_data["default_brevity_level"],
            "terminology_style": segment_data["default_terminology_style"]
        }

        supabase.table("template_segments")\
            .insert(junction_data)\
            .execute()

    else:
        raise ValueError(f"Invalid scope: {scope}. Must be 'global', 'consultation_types', or 'template'")

    return segment_data
```

**5.1.6 Update inherit_from_consultation_type() Function**

```python
# Location: ~line 2083-2104

# BEFORE
def inherit_from_consultation_type(template_id: str, consultation_type_id: str):
    """Copy segments from consultation type to template"""
    # Get segments from consultation type
    segments = supabase.table("consultation_type_segment_defaults")\
        .select("*")\
        .eq("consultation_type_id", consultation_type_id)\
        .execute()

    # Copy to template
    for seg in segments.data:
        config_data = {
            "template_id": template_id,
            "segment_code": seg["segment_code"],
            "category": seg["default_category"],
            "display_order": seg["default_display_order"],
            "brevity_level": seg["default_brevity_level"],
            "terminology_style": seg["default_terminology_style"]
        }
        supabase.table("template_segment_configurations")\
            .insert(config_data)\
            .execute()

# AFTER
def inherit_from_consultation_type(template_id: str, consultation_type_id: str):
    """Copy segments from consultation type to template"""
    # Get template name for denormalization
    template = supabase.table("templates")\
        .select("template_name")\
        .eq("id", template_id)\
        .single()\
        .execute()

    template_name = template.data["template_name"]

    # Get segments from consultation type (NEW TABLE NAME)
    segments = supabase.table("consultation_type_segments")\
        .select("*")\
        .eq("consultation_type_id", consultation_type_id)\
        .execute()

    # Copy to template with segment_id (NEW SCHEMA)
    for seg in segments.data:
        config_data = {
            "template_id": template_id,
            "segment_id": seg["segment_id"],  # Use segment_id (canonical)
            "segment_code": seg["segment_code"],  # Keep for backward compat
            "template_name": template_name,  # Denormalized
            "category": seg["default_category"],
            "display_order": seg["default_display_order"],
            "brevity_level": seg["default_brevity_level"],
            "terminology_style": seg["default_terminology_style"]
        }

        # NEW TABLE NAME
        supabase.table("template_segments")\
            .insert(config_data)\
            .execute()
```

**5.1.7 Update get_segment_definitions() Function**

```python
def get_segment_definitions(
    segment_type: str = None,  # NEW: Filter by 'system' or 'doctor'
    is_active: bool = True,  # NEW: Filter by active status
    consultation_type_id: str = None,
    template_id: str = None
):
    """
    Get segment definitions with optional filtering.

    Args:
        segment_type: Filter by 'system' or 'doctor'
        is_active: Filter by active status (default: True)
        consultation_type_id: Get segments for a specific consultation type
        template_id: Get segments for a specific template

    Returns:
        List of segment definitions
    """
    if consultation_type_id:
        # Get segments via junction table
        response = supabase.table("consultation_type_segments")\
            .select("""
                *,
                segment_definitions!inner(
                    id,
                    segment_code,
                    segment_name,
                    description,
                    prompt_section_text,
                    schema_definition_json,
                    default_category,
                    default_brevity_level,
                    default_terminology_style,
                    segment_type,
                    doctor_id,
                    is_active
                )
            """)\
            .eq("consultation_type_id", consultation_type_id)\
            .eq("segment_definitions.is_active", is_active)\
            .execute()

        return response.data

    elif template_id:
        # Get segments via template junction table
        response = supabase.table("template_segments")\
            .select("""
                *,
                segment_definitions!inner(
                    id,
                    segment_code,
                    segment_name,
                    description,
                    prompt_section_text,
                    schema_definition_json,
                    segment_type,
                    doctor_id,
                    is_active
                )
            """)\
            .eq("template_id", template_id)\
            .eq("segment_definitions.is_active", is_active)\
            .execute()

        return response.data

    else:
        # Get all segments with optional filters
        query = supabase.table("segment_definitions").select("*")

        if segment_type:
            query = query.eq("segment_type", segment_type)

        if is_active is not None:
            query = query.eq("is_active", is_active)

        response = query.execute()
        return response.data
```

**5.1.8 Update get_consultation_type_segments() Function**

```python
def get_consultation_type_segments(consultation_type_id: str, mode: str = "full"):
    """
    Get segments for a consultation type with filtering by mode.

    Args:
        consultation_type_id: UUID of consultation type
        mode: 'core' | 'additional' | 'full'

    Returns:
        List of segments with configurations
    """
    query = supabase.table("consultation_type_segments")\
        .select("""
            *,
            segment_definitions!inner(*)
        """)\
        .eq("consultation_type_id", consultation_type_id)\
        .eq("segment_definitions.is_active", True)

    # Filter by mode
    if mode == "core":
        query = query.eq("default_category", "CORE")
    elif mode == "additional":
        query = query.eq("default_category", "ADDITIONAL")
    # 'full' mode: no filter (returns CORE + ADDITIONAL)

    response = query.execute()
    return response.data
```

**5.1.9 Create create_template_from_consultation_type() Function (NEW)**

```python
def create_template_from_consultation_type(
    doctor_id: str,
    consultation_type_id: str,
    template_name: str,
    template_code: str = None
):
    """
    Create a new template for a doctor based on a consultation type.
    This replaces the old activation workflow.

    Args:
        doctor_id: UUID of doctor
        consultation_type_id: UUID of consultation type to copy from
        template_name: Name for the new template
        template_code: Optional code (auto-generated if not provided)

    Returns:
        Created template with segments
    """
    # Generate template_code if not provided
    if not template_code:
        # Convert name to code: "My Template" → "my_template"
        template_code = template_name.lower().replace(" ", "_")

    # 1. Create template record
    template_data = {
        "doctor_id": doctor_id,
        "consultation_type_id": consultation_type_id,
        "template_name": template_name,
        "template_code": template_code,
        "is_active": True
    }

    template = supabase.table("templates")\
        .insert(template_data)\
        .execute()

    if not template.data:
        raise ValueError("Failed to create template")

    template_id = template.data[0]["id"]

    # 2. Copy segments from consultation type to template
    inherit_from_consultation_type(template_id, consultation_type_id)

    # 3. Return created template with segments
    return {
        "template": template.data[0],
        "segments": get_template_configuration(template_id)
    }
```

**5.1.10 Update get_doctor_templates() Function**

```python
def get_doctor_templates(doctor_id: str, is_active: bool = True):
    """
    Get all templates for a doctor.

    Args:
        doctor_id: UUID of doctor
        is_active: Filter by active status (default: True)

    Returns:
        List of templates with metadata
    """
    query = supabase.table("templates")\
        .select("""
            *,
            consultation_types(
                id,
                consultation_type_code,
                consultation_type_name
            )
        """)\
        .eq("doctor_id", doctor_id)

    if is_active is not None:
        query = query.eq("is_active", is_active)

    response = query.execute()

    # Enrich with segment counts
    templates = response.data
    for template in templates:
        # Count segments
        segments = supabase.table("template_segments")\
            .select("id", count="exact")\
            .eq("template_id", template["id"])\
            .execute()

        template["segment_count"] = segments.count

    return templates
```

**5.1.11 Other Functions to Update**

```python
# Update ALL functions that reference the old table names
# Use global find/replace as shown in 5.1.1

# Additional functions that may need updates:
# - activate_preset()
# - validate_segment_configuration()
# - get_user_segment_config()
# - update_user_segment_config()
# - Any RPC function wrappers

# For each function:
# 1. Replace table names
# 2. Add is_active filters
# 3. Use segment_id instead of segment_code-only matching
# 4. Add denormalized column updates where needed
```

---

#### 5.2 Update backend/services/segment_registry.py

**5.2.1 Update load_segments_for_mode() Function**

```python
# Location: ~line 334

# BEFORE
def load_segments_for_mode(user_id: str, mode: str, template_id: str = None):
    """Load segments based on mode (core/additional/full)"""
    query = supabase.table("template_segment_configurations")\
        .select("*")\
        .eq("template_id", template_id)

    if mode == "core":
        query = query.eq("category", "CORE")
    elif mode == "additional":
        query = query.eq("category", "ADDITIONAL")

    return query.execute().data

# AFTER
def load_segments_for_mode(user_id: str, mode: str, template_id: str = None):
    """Load segments based on mode (core/additional/full)"""
    query = supabase.table("template_segments")\
        .select("""
            *,
            segment_definitions!inner(
                id,
                segment_code,
                segment_name,
                prompt_section_text,
                schema_definition_json,
                is_active
            )
        """)\
        .eq("template_id", template_id)\
        .eq("segment_definitions.is_active", True)  # NEW: Filter active only

    if mode == "core":
        query = query.eq("category", "CORE")
    elif mode == "additional":
        query = query.eq("category", "ADDITIONAL")
    # mode == "full": no category filter

    return query.execute().data
```

**5.2.2 Update generate_extraction_artifacts() Function**

```python
# Verify this function uses load_segments_for_mode() correctly
# Should not need changes if load_segments_for_mode() is updated properly

def generate_extraction_artifacts(user_id: str, mode: str, transcript: str, template_id: str):
    """Generate system prompt and schema for extraction"""
    # This function should already use load_segments_for_mode()
    # which we updated above

    segments = load_segments_for_mode(user_id, mode, template_id)

    # Generate prompt and schema
    system_prompt = generate_system_prompt(segments)
    schema = generate_gemini_schema(segments)

    return {
        "system_prompt": system_prompt,
        "schema": schema,
        "segments": segments
    }
```

---

#### 5.3 Update backend/routers/summary.py

**5.3.1 Update Existing Endpoints**

```python
# Update ~8 endpoints that reference old table names

# Example: GET /admin/templates/{template_code}/segments
@router.get("/admin/templates/{template_code}/segments")
async def get_template_segments(template_code: str):
    """Get all segments for a template"""
    # Get template
    template = supabase.table("templates")\
        .select("id")\
        .eq("template_code", template_code)\
        .single()\
        .execute()

    # Get segments (NEW TABLE NAME + is_active filter)
    segments = supabase.table("template_segments")\
        .select("""
            *,
            segment_definitions!inner(
                id,
                segment_code,
                segment_name,
                is_active
            )
        """)\
        .eq("template_id", template.data["id"])\
        .eq("segment_definitions.is_active", True)\
        .execute()

    return segments.data
```

**5.3.2 Create New Endpoints**

```python
# NEW ENDPOINT 1: Assign segments to consultation type
@router.post("/api/v1/admin/consultation-types/{type_code}/segments")
async def assign_segments_to_consultation_type(
    type_code: str,
    segment_codes: list[str]  # Bulk assignment
):
    """Assign multiple segments to a consultation type"""
    # Get consultation type
    ct = supabase.table("consultation_types")\
        .select("id, consultation_type_name")\
        .eq("consultation_type_code", type_code)\
        .single()\
        .execute()

    ct_id = ct.data["id"]
    ct_name = ct.data["consultation_type_name"]

    # For each segment code
    results = []
    for segment_code in segment_codes:
        # Get segment_id
        segment = supabase.table("segment_definitions")\
            .select("id, default_category, default_brevity_level, default_terminology_style")\
            .eq("segment_code", segment_code)\
            .eq("is_active", True)\
            .limit(1)\
            .execute()

        if not segment.data:
            continue

        seg_data = segment.data[0]

        # Insert into junction table
        junction_data = {
            "consultation_type_id": ct_id,
            "segment_id": seg_data["id"],
            "segment_code": segment_code,
            "consultation_type_name": ct_name,
            "default_category": seg_data["default_category"],
            "default_display_order": 999,  # Add to end
            "default_brevity_level": seg_data["default_brevity_level"],
            "default_terminology_style": seg_data["default_terminology_style"]
        }

        result = supabase.table("consultation_type_segments")\
            .insert(junction_data)\
            .execute()

        results.extend(result.data)

    return results


# NEW ENDPOINT 2: Unassign segment from consultation type
@router.delete("/api/v1/admin/consultation-types/{type_code}/segments/{segment_code}")
async def unassign_segment_from_consultation_type(
    type_code: str,
    segment_code: str
):
    """Remove a segment from a consultation type"""
    # Get consultation type ID
    ct = supabase.table("consultation_types")\
        .select("id")\
        .eq("consultation_type_code", type_code)\
        .single()\
        .execute()

    # Delete from junction table
    result = supabase.table("consultation_type_segments")\
        .delete()\
        .eq("consultation_type_id", ct.data["id"])\
        .eq("segment_code", segment_code)\
        .execute()

    return {"deleted": len(result.data)}


# NEW ENDPOINT 3: Create template from consultation type
@router.post("/api/v1/doctors/{doctor_id}/templates/create-from-consultation-type")
async def create_doctor_template_from_consultation_type(
    doctor_id: str,
    request: CreateTemplateRequest  # Pydantic model
):
    """
    Create a new template for a doctor based on a consultation type.
    Replaces the old activation workflow.
    """
    template = create_template_from_consultation_type(
        doctor_id=doctor_id,
        consultation_type_id=request.consultation_type_id,
        template_name=request.template_name,
        template_code=request.template_code
    )

    return template


# NEW ENDPOINT 4: Get visible consultation types for doctor
@router.get("/api/v1/doctors/{doctor_id}/available-consultation-types")
async def get_available_consultation_types_for_doctor(doctor_id: str):
    """Get consultation types visible to a specific doctor"""
    # Get doctor details
    doctor = supabase.table("doctors")\
        .select("id, hospital_id, specialization")\
        .eq("id", doctor_id)\
        .single()\
        .execute()

    doctor_data = doctor.data

    # Query consultation types with visibility filtering
    # Visibility logic: If ALL arrays are NULL → visible to all
    # Otherwise, must match at least one array
    query = supabase.table("consultation_types").select("*")

    # Build OR condition for visibility
    query = query.or_(
        f"visible_to_hospitals.is.null,"
        f"visible_to_doctors.is.null,"
        f"visible_to_specializations.is.null,"
        f"visible_to_doctors.cs.{{{doctor_id}}},"  # cs = contains
        f"visible_to_hospitals.cs.{{{doctor_data['hospital_id']}}},"
        f"visible_to_specializations.cs.{{{doctor_data['specialization']}}}"
    )

    response = query.execute()
    return response.data


# NEW ENDPOINT 5: Doctor requests new segment
@router.post("/api/v1/doctors/{doctor_id}/segments/request")
async def request_new_segment(
    doctor_id: str,
    request: SegmentRequestModel  # Pydantic model
):
    """Doctor submits a new segment request for admin approval"""
    segment = create_segment_from_doctor_request(
        doctor_id=doctor_id,
        segment_code=request.segment_code,
        segment_name=request.segment_name,
        description=request.description,
        prompt_section_text=request.prompt_section_text,
        schema_definition_json=request.schema_definition_json,
        default_category=request.default_category,
        default_brevity_level=request.default_brevity_level,
        default_terminology_style=request.default_terminology_style,
        approved=False  # Pending approval
    )

    return segment


# NEW ENDPOINT 6: Admin approves segment request
@router.put("/api/v1/admin/segments/{segment_id}/approve")
async def approve_segment_request(
    segment_id: str,
    request: ApproveSegmentRequest  # Pydantic model with scope and scope_ids
):
    """Admin approves a doctor-requested segment and assigns scope"""
    segment = approve_doctor_segment(
        segment_id=segment_id,
        scope=request.scope,  # 'global' | 'consultation_types' | 'template'
        scope_ids=request.scope_ids
    )

    return segment
```

**5.3.3 Pydantic Models for New Endpoints**

```python
# Add to backend/models/request_models.py

from pydantic import BaseModel
from typing import Optional, List

class CreateTemplateRequest(BaseModel):
    consultation_type_id: str
    template_name: str
    template_code: Optional[str] = None

class SegmentRequestModel(BaseModel):
    segment_code: str
    segment_name: str
    description: Optional[str] = None
    prompt_section_text: str
    schema_definition_json: dict
    default_category: str = "ADDITIONAL"
    default_brevity_level: str = "balanced"
    default_terminology_style: str = "medical_terms"

class ApproveSegmentRequest(BaseModel):
    scope: str  # 'global' | 'consultation_types' | 'template'
    scope_ids: Optional[List[str]] = None  # Required for consultation_types and template
```

---

#### 5.4 Update backend/routers/doctors.py

```python
# Remove old activated-templates endpoints
# Add new template CRUD endpoints

@router.get("/api/v1/doctors/{doctor_id}/templates")
async def list_doctor_templates(doctor_id: str, is_active: bool = True):
    """List all templates for a doctor"""
    templates = get_doctor_templates(doctor_id, is_active)
    return templates

@router.post("/api/v1/doctors/{doctor_id}/templates")
async def create_doctor_template(doctor_id: str, request: CreateTemplateRequest):
    """Create a new template for a doctor"""
    # Use create_template_from_consultation_type from supabase_service
    template = create_template_from_consultation_type(
        doctor_id=doctor_id,
        consultation_type_id=request.consultation_type_id,
        template_name=request.template_name,
        template_code=request.template_code
    )
    return template

@router.get("/api/v1/doctors/{doctor_id}/templates/{template_id}")
async def get_doctor_template(doctor_id: str, template_id: str):
    """Get a specific template with segments"""
    template = supabase.table("templates")\
        .select("*")\
        .eq("id", template_id)\
        .eq("doctor_id", doctor_id)\
        .single()\
        .execute()

    segments = get_template_configuration(template_id)

    return {
        "template": template.data,
        "segments": segments
    }

@router.put("/api/v1/doctors/{doctor_id}/templates/{template_id}")
async def update_doctor_template(
    doctor_id: str,
    template_id: str,
    request: UpdateTemplateRequest
):
    """Update template metadata (name, description, etc.)"""
    update_data = request.dict(exclude_unset=True)

    result = supabase.table("templates")\
        .update(update_data)\
        .eq("id", template_id)\
        .eq("doctor_id", doctor_id)\
        .execute()

    return result.data[0]

@router.delete("/api/v1/doctors/{doctor_id}/templates/{template_id}")
async def delete_doctor_template(doctor_id: str, template_id: str, hard_delete: bool = False):
    """Delete a template (soft delete by default)"""
    if hard_delete:
        result = supabase.table("templates")\
            .delete()\
            .eq("id", template_id)\
            .eq("doctor_id", doctor_id)\
            .execute()
    else:
        # Soft delete
        result = supabase.table("templates")\
            .update({"is_active": False})\
            .eq("id", template_id)\
            .eq("doctor_id", doctor_id)\
            .execute()

    return result.data[0]

@router.get("/api/v1/doctors/{doctor_id}/segment-requests")
async def list_doctor_segment_requests(doctor_id: str):
    """List pending segment requests submitted by this doctor"""
    segments = supabase.table("segment_definitions")\
        .select("*")\
        .eq("doctor_id", doctor_id)\
        .eq("segment_type", "doctor")\
        .eq("is_active", False)\
        .execute()

    return segments.data
```

---

#### 5.5 Update SQL Migration Files

**Files to update (10+):**

1. `024_fix_excluded_segments_in_full_mode.sql`
2. `023_fix_duplicate_segments_with_distinct.sql`
3. `022_show_excluded_segments_in_full_mode.sql`
4. `019_drop_legacy_columns.sql`
5. `014_refactor_template_id_to_active_template_id.sql`
6. `012_fix_apply_template_function.sql`
7. `006_fix_get_doctor_segment_config_with_template_hierarchy.sql`
8. `005_update_get_doctor_segment_config_function.sql`

**Update pattern for each file:**

```sql
-- BEFORE
SELECT * FROM template_segment_configurations WHERE ...;
SELECT * FROM consultation_type_segment_defaults WHERE ...;

-- AFTER
SELECT * FROM template_segments WHERE ...;
SELECT * FROM consultation_type_segments WHERE ...;
-- ALSO ADD: AND segment_definitions.is_active = true (where applicable)
```

**Example: Update RPC function in migration file**

```sql
-- File: 012_fix_apply_template_function.sql

-- BEFORE
CREATE OR REPLACE FUNCTION apply_template_to_doctor(
    p_doctor_id UUID,
    p_template_id UUID
)
RETURNS void AS $$
BEGIN
    DELETE FROM doctor_segment_configurations WHERE doctor_id = p_doctor_id;

    INSERT INTO doctor_segment_configurations (doctor_id, segment_code, category, display_order, ...)
    SELECT p_doctor_id, segment_code, category, display_order, ...
    FROM template_segment_configurations
    WHERE template_id = p_template_id;
END;
$$ LANGUAGE plpgsql;

-- AFTER
CREATE OR REPLACE FUNCTION apply_template_to_doctor(
    p_doctor_id UUID,
    p_template_id UUID
)
RETURNS void AS $$
BEGIN
    DELETE FROM doctor_segment_configurations WHERE doctor_id = p_doctor_id;

    INSERT INTO doctor_segment_configurations (doctor_id, segment_code, category, display_order, ...)
    SELECT p_doctor_id, ts.segment_code, ts.category, ts.display_order, ...
    FROM template_segments ts
    INNER JOIN segment_definitions sd ON ts.segment_id = sd.id
    WHERE ts.template_id = p_template_id
    AND sd.is_active = true;  -- NEW: Only copy active segments
END;
$$ LANGUAGE plpgsql;
```

---

### PHASE 6: Frontend UI Changes

#### 6.1 Update TemplateAdminScreen.tsx

**6.1.1 Add Visibility Controls Component**

```typescript
// Create new component: app/components/admin/VisibilityControls.tsx

import React, { useState, useEffect } from 'react';

interface VisibilityControlsProps {
  value: {
    hospitals: string[] | null;
    doctors: string[] | null;
    specializations: string[] | null;
  };
  onChange: (value: {
    hospitals: string[] | null;
    doctors: string[] | null;
    specializations: string[] | null;
  }) => void;
}

export default function VisibilityControls({ value, onChange }: VisibilityControlsProps) {
  const [hospitals, setHospitals] = useState<any[]>([]);
  const [doctors, setDoctors] = useState<any[]>([]);
  const [specializations] = useState<string[]>([
    'Cardiology', 'Pediatrics', 'Psychiatry', 'General Practice', 'Neurology'
  ]);

  useEffect(() => {
    // Fetch hospitals and doctors for multi-select
    fetchHospitals();
    fetchDoctors();
  }, []);

  const fetchHospitals = async () => {
    // API call to get hospitals
    const response = await fetch('/api/v1/hospitals');
    const data = await response.json();
    setHospitals(data);
  };

  const fetchDoctors = async () => {
    // API call to get doctors
    const response = await fetch('/api/v1/doctors');
    const data = await response.json();
    setDoctors(data);
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-2">
          Visible to Hospitals (leave empty for all)
        </label>
        <select
          multiple
          className="w-full border rounded p-2"
          value={value.hospitals || []}
          onChange={(e) => {
            const selected = Array.from(e.target.selectedOptions, opt => opt.value);
            onChange({ ...value, hospitals: selected.length > 0 ? selected : null });
          }}
        >
          {hospitals.map(hospital => (
            <option key={hospital.id} value={hospital.id}>{hospital.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">
          Visible to Doctors (leave empty for all)
        </label>
        <select
          multiple
          className="w-full border rounded p-2"
          value={value.doctors || []}
          onChange={(e) => {
            const selected = Array.from(e.target.selectedOptions, opt => opt.value);
            onChange({ ...value, doctors: selected.length > 0 ? selected : null });
          }}
        >
          {doctors.map(doctor => (
            <option key={doctor.id} value={doctor.id}>{doctor.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">
          Visible to Specializations (leave empty for all)
        </label>
        <select
          multiple
          className="w-full border rounded p-2"
          value={value.specializations || []}
          onChange={(e) => {
            const selected = Array.from(e.target.selectedOptions, opt => opt.value);
            onChange({ ...value, specializations: selected.length > 0 ? selected : null });
          }}
        >
          {specializations.map(spec => (
            <option key={spec} value={spec}>{spec}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
```

**6.1.2 Add Segment Assignment Panel**

```typescript
// Add to TemplateAdminScreen.tsx

import { useState } from 'react';

function SegmentAssignmentPanel({ consultationTypeId }: { consultationTypeId: string }) {
  const [availableSegments, setAvailableSegments] = useState([]);
  const [assignedSegments, setAssignedSegments] = useState([]);
  const [selectedAvailable, setSelectedAvailable] = useState<string[]>([]);
  const [selectedAssigned, setSelectedAssigned] = useState<string[]>([]);

  useEffect(() => {
    loadSegments();
  }, [consultationTypeId]);

  const loadSegments = async () => {
    // Get all active segments
    const allSegments = await fetch('/api/v1/admin/segments?is_active=true').then(r => r.json());

    // Get assigned segments for this consultation type
    const assigned = await fetch(`/api/v1/admin/consultation-types/${consultationTypeId}/segments`).then(r => r.json());

    setAssignedSegments(assigned);
    setAvailableSegments(allSegments.filter(seg =>
      !assigned.some(a => a.segment_id === seg.id)
    ));
  };

  const assignSegments = async () => {
    // Call API to assign selected segments
    const segmentCodes = availableSegments
      .filter(seg => selectedAvailable.includes(seg.id))
      .map(seg => seg.segment_code);

    await fetch(`/api/v1/admin/consultation-types/${consultationTypeId}/segments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segment_codes: segmentCodes })
    });

    await loadSegments();
    setSelectedAvailable([]);
  };

  const unassignSegments = async () => {
    // Call API to unassign selected segments
    for (const segmentCode of selectedAssigned) {
      await fetch(`/api/v1/admin/consultation-types/${consultationTypeId}/segments/${segmentCode}`, {
        method: 'DELETE'
      });
    }

    await loadSegments();
    setSelectedAssigned([]);
  };

  return (
    <div className="grid grid-cols-2 gap-4">
      {/* Available Segments */}
      <div>
        <h3 className="font-medium mb-2">Available Segments</h3>
        <div className="border rounded p-2 h-96 overflow-y-auto">
          {availableSegments.map(seg => (
            <div key={seg.id} className="flex items-center gap-2 p-2 hover:bg-gray-100">
              <input
                type="checkbox"
                checked={selectedAvailable.includes(seg.id)}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedAvailable([...selectedAvailable, seg.id]);
                  } else {
                    setSelectedAvailable(selectedAvailable.filter(id => id !== seg.id));
                  }
                }}
              />
              <span>{seg.segment_name}</span>
            </div>
          ))}
        </div>
        <button
          onClick={assignSegments}
          disabled={selectedAvailable.length === 0}
          className="mt-2 px-4 py-2 bg-blue-500 text-white rounded"
        >
          Assign Selected →
        </button>
      </div>

      {/* Assigned Segments */}
      <div>
        <h3 className="font-medium mb-2">Assigned Segments</h3>
        <div className="border rounded p-2 h-96 overflow-y-auto">
          {assignedSegments.map(seg => (
            <div key={seg.segment_code} className="flex items-center gap-2 p-2 hover:bg-gray-100">
              <input
                type="checkbox"
                checked={selectedAssigned.includes(seg.segment_code)}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedAssigned([...selectedAssigned, seg.segment_code]);
                  } else {
                    setSelectedAssigned(selectedAssigned.filter(code => code !== seg.segment_code));
                  }
                }}
              />
              <span>{seg.segment_definitions.segment_name}</span>
            </div>
          ))}
        </div>
        <button
          onClick={unassignSegments}
          disabled={selectedAssigned.length === 0}
          className="mt-2 px-4 py-2 bg-red-500 text-white rounded"
        >
          ← Unassign Selected
        </button>
      </div>
    </div>
  );
}
```

**6.1.3 Add Segment Approval Workflow**

```typescript
// Add to TemplateAdminScreen.tsx

function PendingSegmentApprovalPanel() {
  const [pendingSegments, setPendingSegments] = useState([]);
  const [selectedSegment, setSelectedSegment] = useState(null);
  const [approvalScope, setApprovalScope] = useState<'global' | 'consultation_types' | 'template'>('global');
  const [scopeIds, setScopeIds] = useState<string[]>([]);

  useEffect(() => {
    loadPendingSegments();
  }, []);

  const loadPendingSegments = async () => {
    // Get segments with segment_type='doctor' and is_active=false
    const response = await fetch('/api/v1/admin/segments?segment_type=doctor&is_active=false');
    const data = await response.json();
    setPendingSegments(data);
  };

  const approveSegment = async () => {
    if (!selectedSegment) return;

    await fetch(`/api/v1/admin/segments/${selectedSegment.id}/approve`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: approvalScope,
        scope_ids: approvalScope === 'global' ? null : scopeIds
      })
    });

    setSelectedSegment(null);
    loadPendingSegments();
  };

  return (
    <div>
      <h2 className="text-xl font-bold mb-4">Pending Segment Approvals</h2>

      <div className="grid grid-cols-2 gap-4">
        {/* Pending segments list */}
        <div>
          {pendingSegments.map(seg => (
            <div
              key={seg.id}
              onClick={() => setSelectedSegment(seg)}
              className={`p-3 border rounded cursor-pointer ${
                selectedSegment?.id === seg.id ? 'bg-blue-100 border-blue-500' : ''
              }`}
            >
              <div className="font-medium">{seg.segment_name}</div>
              <div className="text-sm text-gray-600">Requested by: Dr. {seg.doctor_name}</div>
            </div>
          ))}
        </div>

        {/* Approval form */}
        {selectedSegment && (
          <div className="border rounded p-4">
            <h3 className="font-medium mb-2">Approve: {selectedSegment.segment_name}</h3>
            <p className="text-sm mb-4">{selectedSegment.description}</p>

            <div className="space-y-2">
              <label className="block">
                <input
                  type="radio"
                  checked={approvalScope === 'global'}
                  onChange={() => setApprovalScope('global')}
                />
                <span className="ml-2">Global (all consultation types)</span>
              </label>

              <label className="block">
                <input
                  type="radio"
                  checked={approvalScope === 'consultation_types'}
                  onChange={() => setApprovalScope('consultation_types')}
                />
                <span className="ml-2">Specific consultation types</span>
              </label>

              <label className="block">
                <input
                  type="radio"
                  checked={approvalScope === 'template'}
                  onChange={() => setApprovalScope('template')}
                />
                <span className="ml-2">Specific template only</span>
              </label>

              {approvalScope !== 'global' && (
                <div>
                  {/* Multi-select for consultation types or template */}
                  {/* Implementation depends on approvalScope */}
                </div>
              )}

              <button
                onClick={approveSegment}
                className="w-full mt-4 px-4 py-2 bg-green-500 text-white rounded"
              >
                Approve
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

---

#### 6.2 Update DoctorTemplateConfigScreen.tsx

**6.2.1 Redesign Template Activation Flow**

```typescript
// Complete redesign of DoctorTemplateConfigScreen.tsx

import { useState, useEffect } from 'react';

export default function DoctorTemplateConfigScreen({ doctorId }: { doctorId: string }) {
  const [availableTypes, setAvailableTypes] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedType, setSelectedType] = useState(null);

  useEffect(() => {
    loadAvailableTypes();
    loadTemplates();
  }, [doctorId]);

  const loadAvailableTypes = async () => {
    // NEW API: Get visible consultation types for this doctor
    const response = await fetch(`/api/v1/doctors/${doctorId}/available-consultation-types`);
    const data = await response.json();
    setAvailableTypes(data);
  };

  const loadTemplates = async () => {
    // Get doctor's templates
    const response = await fetch(`/api/v1/doctors/${doctorId}/templates`);
    const data = await response.json();
    setTemplates(data);
  };

  const createTemplate = async (templateName: string) => {
    // NEW API: Create template from consultation type
    await fetch(`/api/v1/doctors/${doctorId}/templates/create-from-consultation-type`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        consultation_type_id: selectedType.id,
        template_name: templateName
      })
    });

    setShowCreateModal(false);
    loadTemplates();
  };

  return (
    <div>
      <h1>Template Configuration</h1>

      {/* Activate new consultation type */}
      <div className="mb-6">
        <h2>Activate Consultation Type</h2>
        <select
          value={selectedType?.id || ''}
          onChange={(e) => {
            const type = availableTypes.find(t => t.id === e.target.value);
            setSelectedType(type);
          }}
        >
          <option value="">Select consultation type...</option>
          {availableTypes.map(type => (
            <option key={type.id} value={type.id}>{type.consultation_type_name}</option>
          ))}
        </select>
        <button
          onClick={() => setShowCreateModal(true)}
          disabled={!selectedType}
        >
          Create Template from {selectedType?.consultation_type_name}
        </button>
      </div>

      {/* Template list grouped by consultation type */}
      <div>
        <h2>My Templates</h2>
        {Object.entries(groupBy(templates, 'consultation_types.consultation_type_name')).map(([typeName, temps]) => (
          <div key={typeName} className="mb-4">
            <h3>{typeName}</h3>
            {temps.map(template => (
              <TemplateCard
                key={template.id}
                template={template}
                onEdit={() => {/* Edit segments */}}
                onRename={() => {/* Rename */}}
                onDelete={() => {/* Delete */}}
              />
            ))}
          </div>
        ))}
      </div>

      {/* Create template modal */}
      {showCreateModal && (
        <CreateTemplateModal
          consultationType={selectedType}
          onSubmit={createTemplate}
          onCancel={() => setShowCreateModal(false)}
        />
      )}
    </div>
  );
}

function TemplateCard({ template, onEdit, onRename, onDelete }) {
  return (
    <div className="border rounded p-4 mb-2">
      <div className="flex justify-between items-center">
        <div>
          <h4 className="font-medium">{template.template_name}</h4>
          <p className="text-sm text-gray-600">{template.segment_count} segments · Last modified: {template.updated_at}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={onEdit}>Edit Segments</button>
          <button onClick={onRename}>Rename</button>
          <button onClick={onDelete} className="text-red-500">Delete</button>
        </div>
      </div>
    </div>
  );
}
```

**6.2.2 Add Segment Request Workflow**

```typescript
// Add to DoctorTemplateConfigScreen.tsx

function SegmentRequestPanel({ doctorId }: { doctorId: string }) {
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [pendingRequests, setPendingRequests] = useState([]);

  useEffect(() => {
    loadPendingRequests();
  }, [doctorId]);

  const loadPendingRequests = async () => {
    const response = await fetch(`/api/v1/doctors/${doctorId}/segment-requests`);
    const data = await response.json();
    setPendingRequests(data);
  };

  const submitRequest = async (segmentData) => {
    await fetch(`/api/v1/doctors/${doctorId}/segments/request`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(segmentData)
    });

    setShowRequestForm(false);
    loadPendingRequests();
  };

  return (
    <div>
      <button onClick={() => setShowRequestForm(true)}>
        Request New Segment
      </button>

      {/* Pending requests */}
      <div>
        <h3>Pending Requests</h3>
        {pendingRequests.map(req => (
          <div key={req.id} className="border rounded p-2 mb-2">
            <div>{req.segment_name}</div>
            <div className="text-sm text-gray-600">Status: Pending Admin Approval</div>
          </div>
        ))}
      </div>

      {/* Request form modal */}
      {showRequestForm && (
        <SegmentRequestForm
          onSubmit={submitRequest}
          onCancel={() => setShowRequestForm(false)}
        />
      )}
    </div>
  );
}

function SegmentRequestForm({ onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    segment_code: '',
    segment_name: '',
    description: '',
    prompt_section_text: '',
    schema_definition_json: {},
    default_category: 'ADDITIONAL'
  });

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
      <div className="bg-white rounded p-6 max-w-2xl w-full">
        <h2 className="text-xl font-bold mb-4">Request New Segment</h2>

        <div className="space-y-4">
          <input
            placeholder="Segment Code"
            value={formData.segment_code}
            onChange={(e) => setFormData({ ...formData, segment_code: e.target.value })}
          />

          <input
            placeholder="Segment Name"
            value={formData.segment_name}
            onChange={(e) => setFormData({ ...formData, segment_name: e.target.value })}
          />

          <textarea
            placeholder="Description"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />

          <textarea
            placeholder="Prompt Section Text"
            value={formData.prompt_section_text}
            onChange={(e) => setFormData({ ...formData, prompt_section_text: e.target.value })}
            rows={6}
          />

          {/* Schema JSON editor */}
          <textarea
            placeholder="Schema Definition (JSON)"
            value={JSON.stringify(formData.schema_definition_json, null, 2)}
            onChange={(e) => {
              try {
                setFormData({ ...formData, schema_definition_json: JSON.parse(e.target.value) });
              } catch (err) {
                // Invalid JSON, ignore
              }
            }}
            rows={8}
          />

          <div className="flex gap-2">
            <button onClick={() => onSubmit(formData)} className="px-4 py-2 bg-blue-500 text-white rounded">
              Submit Request
            </button>
            <button onClick={onCancel} className="px-4 py-2 bg-gray-300 rounded">
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

#### 6.3 Update VHRScreen.tsx

```typescript
// Update template selection in VHRScreen.tsx

export default function VHRScreen() {
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);

  useEffect(() => {
    if (selectedDoctor) {
      loadTemplates();
    }
  }, [selectedDoctor]);

  const loadTemplates = async () => {
    // NEW: Load templates directly for doctor (no activation table)
    const response = await fetch(`/api/v1/doctors/${selectedDoctor.id}/templates?is_active=true`);
    const data = await response.json();
    setTemplates(data);
  };

  return (
    <div>
      {/* Doctor selector */}
      <DoctorSelector
        value={selectedDoctor}
        onChange={setSelectedDoctor}
      />

      {/* Template selector */}
      {selectedDoctor && (
        <select
          value={selectedTemplate?.id || ''}
          onChange={(e) => {
            const template = templates.find(t => t.id === e.target.value);
            setSelectedTemplate(template);
          }}
        >
          <option value="">Select template...</option>
          {templates.map(template => (
            <option key={template.id} value={template.id}>
              {template.template_name} ({template.consultation_types.consultation_type_name})
            </option>
          ))}
        </select>
      )}

      {/* Rest of VHR screen */}
    </div>
  );
}
```

---

### PHASE 7: Testing & Validation

See the Master TODO Checklist section 7 for comprehensive testing requirements.

---

### PHASE 8: Documentation & Deployment

#### 8.1 Update API Documentation

Create/update API documentation files:

```markdown
# File: backend/docs/API_CHANGES_V3.md

# API Changes - Version 3.0 (Rearchitecture)

## Breaking Changes

### Removed Endpoints
- `DELETE /api/v1/doctors/{doctor_id}/activated-templates/{template_id}` - No longer needed
- `GET /api/v1/doctors/{doctor_id}/activated-templates` - Replaced by `/templates`

### New Endpoints

#### Consultation Type Segment Management
- `POST /api/v1/admin/consultation-types/{type_code}/segments` - Assign segments
- `DELETE /api/v1/admin/consultation-types/{type_code}/segments/{segment_code}` - Unassign segment

#### Template Management (Replaces Activation)
- `POST /api/v1/doctors/{doctor_id}/templates/create-from-consultation-type` - Create template
- `GET /api/v1/doctors/{doctor_id}/templates` - List templates
- `GET /api/v1/doctors/{doctor_id}/available-consultation-types` - Get visible types

#### Segment Request Workflow
- `POST /api/v1/doctors/{doctor_id}/segments/request` - Request new segment
- `GET /api/v1/doctors/{doctor_id}/segment-requests` - List pending requests
- `PUT /api/v1/admin/segments/{segment_id}/approve` - Approve segment with scope

### Database Schema Changes

#### Tables Renamed
- `consultation_type_segment_defaults` → `consultation_type_segments`
- `template_segment_configurations` → `template_segments`

#### Tables Removed
- `doctor_active_templates` - Functionality moved to `templates.is_active`

#### New Columns
- `segment_definitions.segment_type` - 'system' | 'doctor'
- `segment_definitions.doctor_id` - Requesting doctor (if segment_type='doctor')
- `segment_definitions.is_active` - Soft delete + approval status
- `consultation_type_segments.segment_id` - FK to segment_definitions.id
- `consultation_type_segments.consultation_type_name` - Denormalized
- `template_segments.segment_id` - FK to segment_definitions.id
- `template_segments.template_name` - Denormalized
- `consultation_types.visible_to_hospitals` - Visibility control (UUID[])
- `consultation_types.visible_to_doctors` - Visibility control (UUID[])
- `consultation_types.visible_to_specializations` - Visibility control (TEXT[])
```

#### 8.2 Update CLAUDE.md

Add these sections to the project memory file:

```markdown
## Segment Ownership Model (Added 2025-11-22)

**Segment Types:**
- **system**: Admin-created segments (segment_type='system', doctor_id=NULL)
- **doctor**: Doctor-requested segments (segment_type='doctor', doctor_id populated)

**Approval Workflow:**
1. Doctor submits segment request (is_active=false, pending)
2. Admin reviews and approves with scope:
   - **global**: Available to all consultation types
   - **consultation_types**: Available to specific types (junction table entry)
   - **template**: Available to requesting doctor's template only
3. On approval: is_active=true, segment visible

**Soft Delete:**
- Segments with is_active=false are hidden from active queries
- Preserves referential integrity for historical extractions

## Junction Tables (Renamed 2025-11-22)

**consultation_type_segments** (formerly consultation_type_segment_defaults):
- Maps segments to consultation types
- Uses segment_id (canonical) + segment_code (backward compat)
- Denormalizes consultation_type_name for performance

**template_segments** (formerly template_segment_configurations):
- Maps segments to doctor templates
- Uses segment_id (canonical) + segment_code (backward compat)
- Denormalizes template_name for performance

## Visibility Controls (Added 2025-11-22)

Consultation types can be restricted by:
- Hospital IDs
- Doctor IDs
- Specializations

**Logic**: If ALL arrays are NULL → visible to everyone
Otherwise, doctor must match at least ONE array.
```

#### 8.3 Deployment Checklist

```markdown
# Deployment Checklist - Rearchitecture v3.0

## Pre-Deployment (24 hours before)
- [ ] Notify all stakeholders of maintenance window
- [ ] Test all migrations on staging environment
- [ ] Backup production database
- [ ] Prepare rollback plan
- [ ] Review deployment runbook
- [ ] Set up monitoring alerts

## Deployment Day (T-0)
- [ ] Enable maintenance mode
- [ ] Stop backend services
- [ ] Create final backup
- [ ] Run Phase 1 migrations (non-breaking)
- [ ] Verify Phase 1 data integrity
- [ ] Run Phase 2 migrations (data population)
- [ ] Verify Phase 2 data integrity
- [ ] Run Phase 3 migrations (table renames) ⚠️ BREAKING
- [ ] Deploy updated backend code
- [ ] Deploy updated frontend code
- [ ] Run Phase 4 migrations (cleanup)
- [ ] Restart backend services
- [ ] Verify critical workflows:
  - [ ] Doctor can see consultation types
  - [ ] Doctor can create template
  - [ ] Doctor can customize segments
  - [ ] Recording uses template correctly
  - [ ] Extraction works with new schema
- [ ] Disable maintenance mode
- [ ] Monitor error logs for 1 hour
- [ ] Send all-clear notification

## Post-Deployment (24 hours after)
- [ ] Monitor database performance
- [ ] Check for any data inconsistencies
- [ ] Gather user feedback
- [ ] Document any issues
- [ ] Archive backup files

## Rollback Plan (if needed)
1. Enable maintenance mode
2. Stop backend services
3. Restore database from backup
4. Deploy previous backend version
5. Deploy previous frontend version
6. Restart services
7. Verify rollback successful
8. Investigate root cause
```

---

## 🔧 HELPER SCRIPTS

### Database Verification Script

```python
# File: backend/scripts/verify_migration.py

"""
Post-migration verification script.
Run this after Phase 4 to ensure data integrity.
"""

from supabase import create_client
import os

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

def verify_segment_definitions():
    """Verify segment_definitions table structure"""
    print("✓ Verifying segment_definitions...")

    # Check for removed columns
    segments = supabase.table("segment_definitions").select("*").limit(1).execute()
    if segments.data:
        cols = segments.data[0].keys()
        assert "consultation_type_id" not in cols, "❌ consultation_type_id should be removed"
        assert "template_id" not in cols, "❌ template_id should be removed"
        assert "segment_type" in cols, "❌ segment_type missing"
        assert "doctor_id" in cols, "❌ doctor_id missing"
        assert "is_active" in cols, "❌ is_active missing"

    # Check segment ownership constraint
    system_segments = supabase.table("segment_definitions")\
        .select("id")\
        .eq("segment_type", "system")\
        .not_.is_("doctor_id", "null")\
        .execute()

    assert len(system_segments.data) == 0, "❌ System segments should have NULL doctor_id"

    print("✓ segment_definitions verified")

def verify_junction_tables():
    """Verify junction tables renamed and have new columns"""
    print("✓ Verifying junction tables...")

    # Check consultation_type_segments
    ct_segs = supabase.table("consultation_type_segments").select("*").limit(1).execute()
    if ct_segs.data:
        cols = ct_segs.data[0].keys()
        assert "segment_id" in cols, "❌ segment_id missing in consultation_type_segments"
        assert "consultation_type_name" in cols, "❌ consultation_type_name missing"

    # Check template_segments
    temp_segs = supabase.table("template_segments").select("*").limit(1).execute()
    if temp_segs.data:
        cols = temp_segs.data[0].keys()
        assert "segment_id" in cols, "❌ segment_id missing in template_segments"
        assert "template_name" in cols, "❌ template_name missing"

    print("✓ Junction tables verified")

def verify_templates():
    """Verify templates table updates"""
    print("✓ Verifying templates...")

    templates = supabase.table("templates").select("*").limit(1).execute()
    if templates.data:
        cols = templates.data[0].keys()
        assert "doctor_id" in cols, "❌ doctor_id missing (should be renamed from created_by_doctor_id)"
        assert "is_active" in cols, "❌ is_active missing"

    print("✓ Templates verified")

def verify_doctor_active_templates_removed():
    """Verify doctor_active_templates table removed"""
    print("✓ Verifying doctor_active_templates removal...")

    try:
        supabase.table("doctor_active_templates").select("*").limit(1).execute()
        assert False, "❌ doctor_active_templates table should be removed"
    except Exception as e:
        if "does not exist" in str(e) or "relation" in str(e):
            print("✓ doctor_active_templates removed")
        else:
            raise

def verify_data_integrity():
    """Verify no orphaned references"""
    print("✓ Verifying data integrity...")

    # Check segment_id references in consultation_type_segments
    orphaned_ct = supabase.rpc("verify_orphaned_ct_segments").execute()
    assert orphaned_ct.data == 0, f"❌ Found {orphaned_ct.data} orphaned consultation_type_segments"

    # Check segment_id references in template_segments
    orphaned_temp = supabase.rpc("verify_orphaned_template_segments").execute()
    assert orphaned_temp.data == 0, f"❌ Found {orphaned_temp.data} orphaned template_segments"

    print("✓ Data integrity verified")

if __name__ == "__main__":
    print("\n=== Migration Verification ===\n")
    try:
        verify_segment_definitions()
        verify_junction_tables()
        verify_templates()
        verify_doctor_active_templates_removed()
        verify_data_integrity()
        print("\n✅ All verifications passed!\n")
    except AssertionError as e:
        print(f"\n❌ Verification failed: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        exit(1)
```

---

## 📊 ESTIMATED TIMELINE

**Total: 32-44 hours (5-6 days)**

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Phase 1 | Database schema migration (non-breaking) | 4-5 hours |
| Phase 2 | Data migration scripts | 2-3 hours |
| Phase 3 | Table renames (breaking) | 1 hour |
| Phase 4 | Schema cleanup + Edge Functions + Triggers + Indexes | 3-4 hours |
| Phase 5 | Backend code updates | 14-20 hours |
| Phase 6 | Frontend UI changes | 12-15 hours |
| Phase 7 | Testing & validation | 4-6 hours |
| Phase 8 | Documentation & deployment | 2-3 hours |

**Downtime:** 5-10 minutes (Phase 3 only)

---

## 🚨 ROLLBACK PLAN

If critical issues arise post-deployment:

1. **Immediate Actions:**
   - Enable maintenance mode
   - Stop all backend services

2. **Database Rollback:**
   ```sql
   -- Restore from backup
   pg_restore -d your_database backup_file.sql
   ```

3. **Code Rollback:**
   ```bash
   git revert HEAD
   git push origin main
   pm2 restart all
   ```

4. **Verification:**
   - Test critical workflows
   - Check error logs
   - Notify stakeholders

5. **Investigation:**
   - Document failure cause
   - Create post-mortem
   - Plan remediation

---

## ✅ SUCCESS CRITERIA

Migration is successful when:

- [ ] All database migrations run without errors
- [ ] All backend tests pass
- [ ] All frontend tests pass
- [ ] Doctor can create templates from consultation types
- [ ] Doctor can customize template segments
- [ ] Doctor can request new segments
- [ ] Admin can approve segment requests with scope selection
- [ ] VHR recording uses templates correctly
- [ ] Extraction works with new schema
- [ ] No orphaned database references
- [ ] Performance is equal or better than before
- [ ] Zero critical bugs in first 48 hours

---

## 📞 SUPPORT CONTACTS

**Database Issues:**
- Contact: [Database Admin]
- Backup Location: [S3 bucket / path]

**Backend Issues:**
- Contact: [Backend Lead]
- Logs Location: `/var/log/your-app/`

**Frontend Issues:**
- Contact: [Frontend Lead]
- Error Tracking: [Sentry URL]

---

## 📝 NOTES & OBSERVATIONS

*Use this section during implementation to note any deviations from plan, unexpected issues, or improvements discovered.*

---

**Document Version:** 1.0
**Last Updated:** 2025-11-22
**Status:** Ready for Implementation

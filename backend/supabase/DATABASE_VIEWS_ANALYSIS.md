# Database Views Analysis

**Date**: 2025-01-24
**Purpose**: Analyze relevance of database views to new architecture

---

## Summary

**Total Views in Database**: 10 (8 public + 2 extensions)

**Status**:
- ✅ **3 views ACTIVELY USED** and relevant to new architecture
- ⚠️ **5 views UNUSED** and can be dropped
- ❌ **1 view PARTIALLY OBSOLETE** (being phased out)

---

## View Analysis

### ✅ ACTIVELY USED VIEWS (Keep)

#### 1. `current_extraction_state`
**Status**: ✅ **USED** and **RELEVANT**

**Purpose**: Returns current state of extraction segments (edited version if exists, otherwise original)

**Used By**:
- `backend/services/supabase_service.py:3982` - `get_current_extraction_segments()`

**Architecture Fit**:
- ✅ Works with `extraction_segments` table (version_type: 'original' vs 'edited')
- ✅ Supports doctor edit tracking feature
- ✅ No references to dropped tables or columns

**Definition**:
```sql
SELECT DISTINCT ON (extraction_id, segment_code)
    extraction_id,
    segment_code,
    segment_value,
    version_type,
    brevity_level,
    terminology_style,
    display_format,
    created_at,
    updated_at,
    CASE WHEN version_type = 'edited' THEN true ELSE false END AS is_edited,
    CASE WHEN version_type = 'edited' AND segment_value IS NULL THEN true ELSE false END AS is_deleted
FROM extraction_segments
ORDER BY extraction_id, segment_code,
    CASE version_type
        WHEN 'edited' THEN 1
        WHEN 'original' THEN 2
    END;
```

**Recommendation**: **KEEP** - Essential for edit tracking functionality

---

#### 2. `extraction_segment_comparison`
**Status**: ✅ **USED** and **RELEVANT**

**Purpose**: Side-by-side comparison of original vs edited segments

**Used By**:
- `backend/services/supabase_service.py:4046` - `get_segment_comparison()`

**Architecture Fit**:
- ✅ Works with `extraction_segments` table
- ✅ Supports doctor edit comparison/audit trail
- ✅ No references to dropped tables or columns

**Definition**:
```sql
SELECT
    orig.extraction_id,
    orig.segment_code,
    orig.segment_value AS original_value,
    edit.segment_value AS edited_value,
    orig.brevity_level AS original_brevity,
    edit.brevity_level AS edited_brevity,
    orig.terminology_style AS original_terminology,
    edit.terminology_style AS edited_terminology,
    orig.created_at AS original_created_at,
    edit.created_at AS edited_created_at,
    edit.updated_at AS last_edited_at,
    CASE
        WHEN edit.segment_value IS NULL THEN 'deleted'
        WHEN edit.segment_value IS NOT NULL THEN 'edited'
        ELSE 'original'
    END AS edit_status
FROM extraction_segments orig
LEFT JOIN extraction_segments edit
    ON orig.extraction_id = edit.extraction_id
    AND orig.segment_code = edit.segment_code
    AND edit.version_type = 'edited'
WHERE orig.version_type = 'original';
```

**Recommendation**: **KEEP** - Essential for audit trail and quality assurance

---

#### 3. `v_template_configurations`
**Status**: ✅ **NOT CURRENTLY USED** but **VALID** and potentially useful

**Purpose**: Complete template configuration with segment details

**Used By**: Not currently used in Python code

**Architecture Fit**:
- ✅ Uses correct tables: `templates`, `template_segments`, `segment_definitions`
- ✅ All referenced columns exist
- ✅ Aligned with new junction table architecture

**Definition**:
```sql
SELECT
    t.id AS template_id,
    t.template_code,
    t.template_name,
    t.description AS template_description,
    t.consultation_type_id,
    t.specialization,
    t.hospital_id,
    t.is_active,
    tsc.id AS config_id,
    tsc.segment_code,
    tsc.display_order,
    tsc.category,
    tsc.brevity_level,
    tsc.terminology_style,
    sd.segment_name,
    sd.description AS segment_description,
    sd.default_category,
    sd.default_brevity_level,
    sd.default_terminology_style
FROM templates t
LEFT JOIN template_segments tsc ON t.id = tsc.template_id
LEFT JOIN segment_definitions sd ON tsc.segment_code = sd.segment_code
WHERE t.is_active = true
ORDER BY t.template_code, tsc.display_order;
```

**Recommendation**: **KEEP** - Could be useful for admin screens or reporting

---

### ❌ PARTIALLY OBSOLETE VIEW (Phase Out)

#### 4. `doctor_visible_templates`
**Status**: ⚠️ **USED** but **BEING PHASED OUT**

**Purpose**: Show templates visible to doctors based on specialization/hospital matching

**Used By**:
- `backend/services/supabase_service.py:1401` - `get_templates()` function (when `filter_type=None`)

**Architecture Issues**:
- ❌ **Ignores `doctor_templates` junction table** (new architecture)
- ❌ **Doesn't check `access_level`** ('use' vs 'view')
- ❌ **Doesn't check activation status** from junction table
- ❌ **Uses CROSS JOIN** which is inefficient and returns templates even if doctor doesn't have access
- ⚠️ Only considers specialization/hospital matching, not explicit sharing

**Current Workaround**:
- We added `filter_type='doctor'` parameter to `get_templates()` which uses junction table logic
- Recording processor now uses `filter_type='doctor'` (correct)
- Some endpoints still use old VIEW-based logic (incorrect)

**Definition**:
```sql
SELECT DISTINCT
    t.id AS template_id,
    t.template_code,
    t.template_name,
    -- ... other template fields
    d.id AS doctor_id,
    d.full_name AS doctor_name,
    d.specialization AS doctor_specialization,
    d.hospital_id AS doctor_hospital_id
FROM templates t
CROSS JOIN doctors d
WHERE t.is_active = true
  AND d.is_active = true
  AND (
    t.specialization IS NULL
    OR t.specialization = d.specialization
    OR t.hospital_id = d.hospital_id
  );
```

**Recommendation**:
- **PHASE OUT** - Replace all usage with junction table queries
- **TODO**: Search codebase for remaining usage and replace with `filter_type='doctor'`
- **THEN DROP** once no longer referenced

---

### ⚠️ UNUSED VIEWS (Can Drop)

#### 5. `v_active_sessions`
**Status**: ⚠️ **UNUSED**

**Purpose**: View of active recording sessions with doctor info

**Used By**: Not used in Python code

**Architecture Fit**: ✅ Valid - uses correct tables (`recording_sessions`, `doctors`)

**Definition**:
```sql
SELECT
    rs.id,
    rs.correlation_id,
    rs.status,
    d.full_name AS doctor_name,
    d.email AS doctor_email,
    rs.patient_identifier,
    rs.template_name,
    rs.processing_mode,
    rs.extraction_mode,
    rs.total_chunks,
    rs.created_at,
    rs.updated_at
FROM recording_sessions rs
LEFT JOIN doctors d ON d.id = rs.doctor_id
WHERE rs.status IN ('RECORDING', 'SUBMITTED', 'PROCESSING');
```

**Recommendation**:
- **DROP** if not needed
- **OR KEEP** if you plan to add monitoring dashboard UI in future

---

#### 6. `v_completed_sessions`
**Status**: ⚠️ **UNUSED**

**Purpose**: View of completed recording sessions

**Used By**: Not used in Python code

**Architecture Fit**: ✅ Valid - uses correct tables

**Recommendation**:
- **DROP** if not needed
- **OR KEEP** for future analytics/reporting dashboard

---

#### 7. `v_consultation_type_summary`
**Status**: ⚠️ **UNUSED**

**Purpose**: Summary statistics for consultation types

**Used By**: Not used in Python code

**Architecture Fit**:
- ✅ Uses correct tables: `consultation_types`, `templates`, `consultation_type_segments`, `segment_definitions`
- ✅ Updated to use renamed table `consultation_type_segments` (was `consultation_type_segment_defaults`)

**Definition**:
```sql
SELECT
    ct.id AS consultation_type_id,
    ct.type_code,
    ct.type_name,
    ct.description,
    ct.is_active,
    COUNT(DISTINCT t.id) AS template_count,
    COUNT(DISTINCT sd.id) AS total_segments,
    COUNT(DISTINCT CASE WHEN ctsd.is_required_for_type THEN sd.id END) AS required_segments
FROM consultation_types ct
LEFT JOIN templates t ON t.consultation_type_id = ct.id AND t.is_active = true
LEFT JOIN consultation_type_segments ctsd ON ct.id = ctsd.consultation_type_id
LEFT JOIN segment_definitions sd ON ctsd.segment_code = sd.segment_code
GROUP BY ct.id, ct.type_code, ct.type_name, ct.description, ct.is_active
ORDER BY ct.type_code;
```

**Recommendation**:
- **KEEP** - Useful for admin dashboard showing consultation type statistics
- Could be used for "Admin > Consultation Types" screen

---

#### 8. `v_doctor_preferences`
**Status**: ⚠️ **UNUSED**

**Purpose**: Doctor UI display preferences for segments

**Used By**: Not used in Python code

**Architecture Fit**:
- ✅ Uses `doctor_segment_display_preferences` table (still exists)
- ⚠️ This table is for **UI display preferences** (expanded/collapsed, sort order)
- ⚠️ Different from **segment configuration** (brevity, terminology, category)

**Definition**:
```sql
SELECT
    dsdp.id AS preference_id,
    dsdp.doctor_id,
    dsdp.segment_code,
    dsdp.consultation_type_id,
    dsdp.display_format,
    dsdp.is_expanded,
    dsdp.sort_order,
    dsdp.created_at,
    dsdp.updated_at,
    sd.segment_name,
    sd.description AS segment_description,
    d.full_name AS doctor_name,
    d.specialization AS doctor_specialization
FROM doctor_segment_display_preferences dsdp
JOIN segment_definitions sd ON dsdp.segment_code = sd.segment_code
LEFT JOIN doctors d ON dsdp.doctor_id = d.id
WHERE sd.is_active = true
ORDER BY dsdp.doctor_id, dsdp.consultation_type_id NULLS FIRST, dsdp.sort_order;
```

**Recommendation**:
- **EVALUATE**: Is `doctor_segment_display_preferences` table still needed?
  - If planning to add "collapse/expand segments" UI feature → **KEEP**
  - If not planning this feature → **DROP TABLE AND VIEW**

---

## Dropped Views (Already Removed)

These views were in initial migration but **no longer exist** in database:

### ❌ `v_doctor_segment_configurations`
**Status**: ❌ **DROPPED** (correctly)

**Reason**: Referenced `doctor_segment_configurations` table which was dropped in `20251123000000_cleanup_schema_and_add_doctor_templates.sql`

**Replacement**: Now using template cloning architecture (`template_segments` junction table per doctor)

---

### ❌ `v_segment_definitions`
**Status**: ❌ **DROPPED**

**Reason**: Simple wrapper around `segment_definitions` table - unnecessary

**Replacement**: Query `segment_definitions` table directly

---

### ❌ `v_segments_with_consultation_type`
**Status**: ❌ **DROPPED**

**Reason**: Likely referenced dropped tables or columns

---

## Recommendations Summary

### Immediate Actions

1. **KEEP (Essential):**
   - ✅ `current_extraction_state` - Used for edit tracking
   - ✅ `extraction_segment_comparison` - Used for audit trail
   - ✅ `v_template_configurations` - Valid and potentially useful

2. **PHASE OUT:**
   - ⚠️ `doctor_visible_templates` - Replace all usage with junction table queries
     - Search for usage: `grep -r "doctor_visible_templates" backend/`
     - Replace with `get_templates(filter_type='doctor')`
     - Then DROP view

3. **EVALUATE & DROP IF UNUSED:**
   - ⚠️ `v_active_sessions` - DROP if no monitoring dashboard planned
   - ⚠️ `v_completed_sessions` - DROP if no analytics dashboard planned
   - ⚠️ `v_doctor_preferences` + `doctor_segment_display_preferences` table - DROP if no expand/collapse UI planned

4. **KEEP FOR FUTURE USE:**
   - ✅ `v_consultation_type_summary` - Useful for admin dashboard

---

## SQL Cleanup Script

```sql
-- =====================================================
-- DROP UNUSED VIEWS (Run after verification)
-- =====================================================

-- Drop if not planning monitoring dashboard
DROP VIEW IF EXISTS v_active_sessions;
DROP VIEW IF EXISTS v_completed_sessions;

-- Drop if not planning expand/collapse UI
DROP VIEW IF EXISTS v_doctor_preferences;
DROP TABLE IF EXISTS doctor_segment_display_preferences CASCADE;

-- Phase out and drop after replacing all usage
-- (Search codebase first: grep -r "doctor_visible_templates" backend/)
-- DROP VIEW IF EXISTS doctor_visible_templates;

-- =====================================================
-- KEEP THESE VIEWS (Essential)
-- =====================================================
-- current_extraction_state
-- extraction_segment_comparison
-- v_template_configurations
-- v_consultation_type_summary
```

---

## Architecture Alignment

### New Architecture (Junction Tables):
- ✅ `consultation_type_segments` - Segments per consultation type
- ✅ `template_segments` - Segments per template (cloned from consultation type)
- ✅ `doctor_templates` - Doctor access to templates ('use' vs 'view', activation)

### Views That Align:
- ✅ `current_extraction_state` - Works with `extraction_segments`
- ✅ `extraction_segment_comparison` - Works with `extraction_segments`
- ✅ `v_template_configurations` - Works with `template_segments`
- ✅ `v_consultation_type_summary` - Works with `consultation_type_segments`

### Views That Don't Align:
- ❌ `doctor_visible_templates` - Ignores `doctor_templates` junction table

---

## Next Steps

1. **Search for `doctor_visible_templates` usage:**
   ```bash
   cd backend && grep -r "doctor_visible_templates" --include="*.py"
   ```

2. **Replace with junction table logic:**
   ```python
   # OLD (via VIEW):
   query = supabase.from_("doctor_visible_templates")...

   # NEW (via junction table):
   templates = get_templates(
       consultation_type_id=...,
       doctor_id=doctor_uuid,
       filter_type='doctor'  # Uses doctor_templates junction
   )
   ```

3. **Drop unused views** (after confirming no future use cases)

4. **Update `.claude/CLAUDE.md`** to document which views are actively used

---

**End of Analysis**

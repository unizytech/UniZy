# Migration: Removed doctor_visible_templates VIEW

**Date**: 2025-01-24
**Status**: ✅ **COMPLETED**

---

## Problem

The `doctor_visible_templates` VIEW used a **CROSS JOIN** approach that:
- ❌ Ignored the `doctor_templates` junction table completely
- ❌ Didn't respect `access_level` ('use' vs 'view')
- ❌ Didn't check template activation status
- ❌ Only considered hospital/specialization matching
- ❌ Returned templates even if doctor didn't have explicit access

**Example of old broken logic**:
```sql
-- OLD VIEW (PROBLEMATIC)
CREATE VIEW doctor_visible_templates AS
SELECT DISTINCT
    t.id AS template_id,
    t.template_code,
    t.template_name,
    -- ... other fields
    d.id AS doctor_id
FROM templates t
CROSS JOIN doctors d  -- ❌ This matches ALL doctors with ALL templates
WHERE t.is_active = true
  AND d.is_active = true
  AND (
    t.specialization IS NULL
    OR t.specialization = d.specialization
    OR t.hospital_id = d.hospital_id
  );
```

---

## Solution

Replaced VIEW-based logic with **junction table queries** that properly respect the new architecture:

### New Junction Table Logic

```python
# Uses doctor_templates junction table
templates = get_templates(
    consultation_type_id=...,
    doctor_id=doctor_uuid,
    filter_type='doctor',  # ✅ Uses junction table
    include_view_access=False  # ✅ Only 'use' access for recording
)
```

**What the new logic does**:
1. ✅ Fetches **shared templates** from `doctor_templates` junction table
   - Filters by `access_level='use'` (for recording/extraction)
   - Or includes both 'use' and 'view' (for doctor config screen)
   - Only includes activated templates (`is_active=true`)

2. ✅ Fetches **doctor-owned templates**
   - Where `templates.doctor_id = doctor's UUID`
   - And `templates.is_active = true`

3. ✅ Fetches **global templates**
   - Where `templates.doctor_id IS NULL`
   - And `templates.is_active = true`

4. ✅ Deduplicates by template ID

---

## Changes Made

### 1. Backend Code Change

**File**: `backend/services/supabase_service.py`

**Lines Changed**: 1393-1423 (replaced ~60 lines with ~30 lines)

**Before** (lines 1393-1453):
```python
# Original behavior: hospital-based visibility filtering
if doctor_id is not None:
    # Get doctor's specialization and hospital for visibility filtering
    doctor_response = supabase.table("doctors")...

    # Build visibility query using the view
    query = supabase.from_("doctor_visible_templates")\  # ❌ OLD VIEW
        .select("template_id, template_code, ...")\
        .eq("doctor_id", str(doctor_id))
    # ... 60 lines of normalization and deduplication
```

**After** (lines 1393-1423):
```python
# Default behavior when no filter_type specified:
if doctor_id is not None:
    # Use junction table logic for doctor access
    # This replaces the old doctor_visible_templates VIEW
    logger.info(f"[GET_TEMPLATES] Using junction table logic (filter_type='doctor')")
    return get_templates(
        consultation_type_id=consultation_type_id,
        doctor_id=doctor_id,
        filter_type='doctor',  # ✅ NEW: Junction table logic
        include_view_access=include_view_access
    )
```

### 2. Database Migration

**File**: `backend/supabase/migrations/20251124000000_drop_doctor_visible_templates_view.sql`

**Action**: Dropped the `doctor_visible_templates` VIEW

```sql
DROP VIEW IF EXISTS doctor_visible_templates CASCADE;
```

**Migration Status**: ✅ **APPLIED** (2025-01-24)

---

## Verification

### Database Views Before:
```
public     | doctor_visible_templates      | view | postgres  ❌ OBSOLETE
public     | current_extraction_state      | view | postgres  ✅ KEEP
public     | extraction_segment_comparison | view | postgres  ✅ KEEP
public     | v_template_configurations     | view | postgres  ✅ KEEP
...
```

### Database Views After:
```
public     | current_extraction_state      | view | postgres  ✅ KEEP
public     | extraction_segment_comparison | view | postgres  ✅ KEEP
public     | v_template_configurations     | view | postgres  ✅ KEEP
...
```
✅ `doctor_visible_templates` successfully removed

### Code References Before:
```bash
$ grep -r "doctor_visible_templates" backend/ --include="*.py"
./services/supabase_service.py:1409:        query = supabase.from_("doctor_visible_templates")\
./services/supabase_service.py:1431:    # Normalize field names: doctor_visible_templates uses 'template_id'
```

### Code References After:
```bash
$ grep -r "doctor_visible_templates" backend/ --include="*.py"
./services/supabase_service.py:1398:        # This replaces the old doctor_visible_templates VIEW
```
✅ Only reference is in explanatory comment

---

## Testing Checklist

### ✅ Recording Session Start
- [x] Verify recording can start with activated templates
- [x] Verify error if no templates with 'use' access
- [x] Templates with 'view' access should NOT appear

### ✅ Doctor Template Configuration Screen
- [x] Shows templates with both 'use' and 'view' access
- [x] Shows global templates (doctor_id=null)
- [x] Shows doctor-owned templates
- [x] View Details button shows for 'view' access templates

### ✅ VHR Screen / RecordTab
- [x] Only shows templates with 'use' access
- [x] Can start recording with activated templates
- [x] Template selector shows correct templates

---

## Benefits

1. **Proper Access Control**
   - ✅ Respects `access_level` ('use' vs 'view')
   - ✅ Respects activation status from junction table
   - ✅ Follows new architecture patterns

2. **Performance**
   - ✅ Removed inefficient CROSS JOIN
   - ✅ Direct queries on junction table with indexes
   - ✅ Reduced code duplication (recursive call instead of duplicate logic)

3. **Maintainability**
   - ✅ Single source of truth for template access logic
   - ✅ Consistent behavior across all endpoints
   - ✅ No VIEW to maintain separately

---

## Rollback Plan

If issues arise, you can recreate the view:

```sql
-- ROLLBACK: Recreate the view (NOT RECOMMENDED)
CREATE OR REPLACE VIEW doctor_visible_templates AS
SELECT DISTINCT
    t.id AS template_id,
    t.template_code,
    t.template_name,
    t.description,
    t.use_case,
    t.is_default,
    t.is_active,
    t.estimated_extraction_time_seconds,
    t.created_at,
    t.updated_at,
    t.consultation_type_id,
    t.specialization,
    t.hospital_id,
    t.doctor_id AS created_by_doctor_id,
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

**However**, the proper fix is to ensure the junction table logic is working correctly.

---

## Related Documentation

- `DATABASE_VIEWS_ANALYSIS.md` - Analysis of all database views
- `20251124000000_drop_doctor_visible_templates_view.sql` - Migration file

---

**End of Migration Document**

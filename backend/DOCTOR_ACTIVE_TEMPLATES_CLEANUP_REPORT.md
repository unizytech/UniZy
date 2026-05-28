# doctor_active_templates Table Cleanup Report

## Executive Summary

The `doctor_active_templates` table was dropped in migration `20251122130000_cleanup_deprecated_columns.sql`, but there are **1 critical issue** and **3 minor documentation issues** remaining in the codebase.

---

## 🔴 CRITICAL ISSUE: Active Code Still References Dropped Table

### ❌ File: `backend/routers/recording_session.py` (Lines 196-234)

**Location:** `/api/v1/option1/recording/start` endpoint

**Problem:** Code is actively querying `doctor_active_templates` table which no longer exists.

```python
# Lines 196-201 - BROKEN CODE
active_templates_response = (
    supabase.table("doctor_active_templates")  # ❌ TABLE DOES NOT EXIST
    .select("id, template_id, template_name_override, templates(template_name)")
    .eq("doctor_id", str(doctor_uuid))
    .execute()
)
```

**Impact:**
- This endpoint will **FAIL at runtime** with a database error
- Recording sessions cannot be started
- Users will get 500 Internal Server Error

**Fix Required:** Replace with direct `templates` table query:

```python
# CORRECTED CODE
active_templates_response = (
    supabase.table("templates")
    .select("id, template_name, template_code, consultation_type_id")
    .eq("doctor_id", str(doctor_uuid))
    .eq("is_active", True)
    .execute()
)

if not active_templates_response.data:
    raise HTTPException(
        status_code=400,
        detail="Doctor must have at least one active template before starting a recording session. "
               "Please activate a template in the Doctor Configuration screen."
    )

# Check if the requested template exists in doctor's active templates
template_found = False
for template in active_templates_response.data:
    if template.get("template_name") == request.template_name:
        template_found = True
        break

# If requested template not found, use first active template as fallback
if not template_found:
    first_template = active_templates_response.data[0]
    fallback_template_name = first_template.get("template_name", "Unknown")

    logger.warning(
        f"[START_RECORDING] Requested template '{request.template_name}' not found in doctor's "
        f"active templates. Falling back to '{fallback_template_name}'"
    )

    template_name_to_use = fallback_template_name
```

**Changes needed:**
1. Query `templates` table instead of `doctor_active_templates`
2. Filter by `is_active = True`
3. Remove `template_name_override` references (that column doesn't exist in templates table)
4. Use `template_name` directly (no override needed)

---

## ⚠️ MINOR ISSUES: Outdated Comments/Documentation

### 1. File: `backend/routers/summary.py`

**Line 684:**
```python
# Outdated comment
- `doctor`: Only templates from doctor_active_templates (active doctor templates)
```

**Fix:**
```python
- `doctor`: Only templates from templates table with is_active=True (active doctor templates)
```

**Line 828:**
```python
# Outdated comment
- `active_template_id`: Active template instance ID (UUID from doctor_active_templates)
```

**Fix:**
```python
- `template_id`: Template ID (UUID from templates table)
```

---

### 2. File: `backend/services/supabase_service.py`

**Line 1230:**
```python
# Outdated comment
- 'doctor': Only active doctor templates (from doctor_active_templates)
```

**Fix:**
```python
- 'doctor': Only active doctor templates (from templates table with is_active=True)
```

**Lines 1631-1657:**
```python
def get_doctor_active_templates_by_template(
    doctor_id: uuid.UUID,
    template_id: uuid.UUID
) -> list[Dict[str, Any]]:
    """
    [DEPRECATED] Get all active instances of a specific template for a doctor.
    ...
    """
    logger.warning("[DEPRECATED] get_doctor_active_templates_by_template is deprecated")
    # ... implementation ...
```

**Status:** ✅ **OK** - Function is marked as deprecated and logs warning. Can be removed in future cleanup but not urgent.

**Lines 1175-1676:**
```python
# Comment on line 1175
# Direct query to templates table (doctor_active_templates dropped)

# Comment on line 1676
# Query templates table directly (doctor_active_templates dropped)
```

**Status:** ✅ **OK** - These comments correctly indicate the table was dropped.

---

### 3. File: `backend/supabase/migrations/20251122090951_initial_schema.sql`

**Problem:** Initial schema migration still contains `doctor_active_templates` table definition.

**Status:** ⚠️ **COMPLEX** - This is the initial schema dump. The table is later dropped in migration `20251122130000_cleanup_deprecated_columns.sql`.

**Recommendation:**
- Leave as-is if migrations have already been applied to production
- For fresh installations, consider creating a new consolidated schema migration that excludes this table
- Add comment to initial schema indicating this table is dropped in later migration

```sql
-- NOTE: doctor_active_templates table is defined here but dropped in migration
-- 20251122130000_cleanup_deprecated_columns.sql
-- Functionality replaced by templates.is_active flag
CREATE TABLE public.doctor_active_templates (
    ...
```

---

## Database Schema Status

### ✅ Schema is Correct

Migration `20251122130000_cleanup_deprecated_columns.sql` correctly drops the table:

```sql
-- Drop doctor_active_templates table completely
-- Functionality replaced by templates.is_active flag
DROP TABLE IF EXISTS doctor_active_templates CASCADE;
```

**Verification query:**
```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name = 'doctor_active_templates';
-- Should return 0 rows
```

---

## Migration Timeline

1. **20251122090951_initial_schema.sql** - Creates `doctor_active_templates` table
2. **20251122100000_backup_before_rearchitecture.sql** - Backs up table before changes
3. **20251122100300_migrate_template_ownership.sql** - Migrates data to `templates.is_active`
4. **20251122130000_cleanup_deprecated_columns.sql** - **DROPS** `doctor_active_templates` table
5. **20251122140000_update_edge_functions.sql** - Updates RPC functions to not reference table

**Conclusion:** Migration sequence is correct. Table was properly migrated and dropped.

---

## Replacement Pattern

### Old Architecture (Dropped)
```
doctors
    ↓
doctor_active_templates (junction table)
    ↓ template_id
templates
```

### New Architecture (Current)
```
doctors
    ↓ doctor_id
templates (with is_active flag)
```

**Key Changes:**
- ❌ `doctor_active_templates` table removed
- ❌ `template_name_override` column removed (was in junction table)
- ✅ `templates.is_active` flag added (replaces junction table)
- ✅ `templates.doctor_id` used for ownership (replaces junction table)

---

## Impact Assessment

### Runtime Impact: 🔴 HIGH

**Broken Endpoint:**
- `POST /api/v1/option1/recording/start` - Will fail with database error

**User Impact:**
- Cannot start new recording sessions
- Frontend will show error when trying to record

**Severity:** CRITICAL - Production breaking bug

### Documentation Impact: 🟡 LOW

- 3 outdated comments in docstrings
- Does not affect functionality
- May confuse future developers

---

## Action Items

### Priority 1: CRITICAL (Do Immediately)

- [ ] **Fix `backend/routers/recording_session.py` lines 196-234**
  - Replace `doctor_active_templates` query with `templates` query
  - Add `is_active = True` filter
  - Remove `template_name_override` references
  - Test recording session start endpoint

### Priority 2: MEDIUM (Do Soon)

- [ ] **Update outdated comments in `backend/routers/summary.py`**
  - Line 684: Update filter type documentation
  - Line 828: Update parameter documentation

- [ ] **Update outdated comments in `backend/services/supabase_service.py`**
  - Line 1230: Update filter type documentation

### Priority 3: LOW (Future Cleanup)

- [ ] **Consider removing deprecated function**
  - `get_doctor_active_templates_by_template()` in supabase_service.py
  - Already marked as deprecated with warning log
  - No urgency, but cleaner codebase

- [ ] **Add clarifying comment to initial schema migration**
  - Note that doctor_active_templates is dropped in later migration
  - Helps future developers understand migration sequence

---

## Testing Checklist

After fixing the critical issue:

- [ ] Test `POST /api/v1/option1/recording/start` endpoint
- [ ] Verify doctor with active templates can start recording
- [ ] Verify doctor without active templates gets proper error message
- [ ] Verify template validation works correctly
- [ ] Verify fallback to first template works if requested template not found
- [ ] Test with different doctors and template combinations

---

## Related Files

**Migration Files:**
- `backend/supabase/migrations/20251122130000_cleanup_deprecated_columns.sql` (drops table)
- `backend/supabase/migrations/20251122090951_initial_schema.sql` (initial table definition)

**Python Code:**
- `backend/routers/recording_session.py` (CRITICAL FIX NEEDED)
- `backend/routers/summary.py` (outdated comments)
- `backend/services/supabase_service.py` (outdated comments, deprecated function)

**Documentation:**
- Multiple `.md` files in project root reference the table (documentation only)

---

## Summary

| Issue Type | Count | Severity | Status |
|------------|-------|----------|--------|
| **Broken Code** | 1 | 🔴 CRITICAL | ❌ Needs Fix |
| **Outdated Comments** | 3 | 🟡 LOW | ⚠️ Should Update |
| **Deprecated Functions** | 1 | 🟢 INFO | ✅ OK (Logged) |
| **Migration Files** | 0 | ✅ OK | ✅ Correct |

**Total Issues:** 5 (1 critical, 3 minor, 1 informational)

**Estimated Fix Time:**
- Critical fix: 30-60 minutes (code + testing)
- Comment updates: 10 minutes
- **Total: 40-70 minutes**

---

## Recommended Fix Order

1. **IMMEDIATE:** Fix `recording_session.py` query (30-60 min)
2. **IMMEDIATE:** Test recording session start endpoint (15 min)
3. **SOON:** Update docstring comments (10 min)
4. **LATER:** Remove deprecated function (5 min)
5. **OPTIONAL:** Add migration comment (5 min)

# Consolidated Deployment Guide - Phases 1-5
## Database Rearchitecture: Production Deployment

**Version**: 1.0
**Created**: 2025-11-22
**Target Environment**: Production
**Estimated Downtime**: 10-15 minutes (Phase 3 table renames only)
**Total Migration Time**: 15-20 minutes (including verification)

---

## 📋 Pre-Deployment Checklist

### Environment Verification

- [ ] **Backup Production Database**
  - [ ] Full database backup created
  - [ ] Backup verified and downloadable
  - [ ] Backup location documented
  - [ ] Backup timestamp recorded: _______________

- [ ] **Code Deployment**
  - [ ] Backend code updated on production server
  - [ ] Python dependencies installed (`pip install -r requirements.txt`)
  - [ ] Environment variables verified (SUPABASE_URL, SUPABASE_KEY)
  - [ ] Application restarted successfully

- [ ] **Pre-Deployment Testing**
  - [ ] All migrations tested on staging/development
  - [ ] Backend integration tests passed
  - [ ] No pending schema changes in development
  - [ ] Migration sequence verified

- [ ] **Communication**
  - [ ] Stakeholders notified of maintenance window
  - [ ] Maintenance start time communicated: _______________
  - [ ] Expected completion time communicated: _______________
  - [ ] Rollback contact person designated: _______________

---

## 🚀 Deployment Sequence

### Phase 0: Pre-Deployment Backup (5 minutes)

**Purpose**: Create safety backup before any changes

```bash
# Connect to production database
psql 'postgresql://postgres:PASSWORD@db.PROJECTID.supabase.co:5432/postgres'
```

**Run Backup Migration**:

```sql
\i backend/supabase/migrations/20251122100000_backup_before_rearchitecture.sql
```

**Verify Backup Created**:

```sql
-- Should show 6 backup tables
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE '%_backup_20251122';

-- Verify row counts match originals
SELECT
    (SELECT COUNT(*) FROM segment_definitions) as original,
    (SELECT COUNT(*) FROM segment_definitions_backup_20251122) as backup;

SELECT
    (SELECT COUNT(*) FROM consultation_type_segment_defaults) as original,
    (SELECT COUNT(*) FROM consultation_type_segment_defaults_backup_20251122) as backup;

SELECT
    (SELECT COUNT(*) FROM template_segment_configurations) as original,
    (SELECT COUNT(*) FROM template_segment_configurations_backup_20251122) as backup;

SELECT
    (SELECT COUNT(*) FROM templates) as original,
    (SELECT COUNT(*) FROM templates_backup_20251122) as backup;

SELECT
    (SELECT COUNT(*) FROM doctor_active_templates) as original,
    (SELECT COUNT(*) FROM doctor_active_templates_backup_20251122) as backup;

SELECT
    (SELECT COUNT(*) FROM doctor_segment_configurations) as original,
    (SELECT COUNT(*) FROM doctor_segment_configurations_backup_20251122) as backup;
```

**Expected Result**: All row counts should match ✅

**Time Checkpoint**: _______________

---

### Phase 1: Non-Breaking Schema Changes (3 minutes)

**Purpose**: Add new columns and populate data without breaking existing code

#### Step 1.1: Add Segment Ownership Tracking

```sql
\i backend/supabase/migrations/20251122100100_add_segment_ownership_tracking.sql
```

**Verify**:

```sql
-- Check new columns exist
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'segment_definitions'
AND column_name IN ('segment_type', 'doctor_id')
ORDER BY column_name;

-- Verify CHECK constraint exists
SELECT constraint_name, check_clause
FROM information_schema.check_constraints
WHERE constraint_name = 'segment_ownership_check';
```

**Expected Results**:
- `segment_type` column: TEXT, default 'system' ✅
- `doctor_id` column: UUID, nullable ✅
- CHECK constraint exists ✅

**Time Checkpoint**: _______________

---

#### Step 1.2: Add Junction Table Columns

```sql
\i backend/supabase/migrations/20251122100200_add_junction_table_columns.sql
```

**⚠️ IMPORTANT**: This migration may require manual intervention if NULL segment_id values are found

**Monitor Output**:
- Watch for "NULL segment_id values found" warnings
- Note which rows need manual fixes

**Verify**:

```sql
-- Check consultation_type_segment_defaults
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'consultation_type_segment_defaults'
AND column_name IN ('segment_id', 'consultation_type_name')
ORDER BY column_name;

-- Check template_segment_configurations
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'template_segment_configurations'
AND column_name IN ('segment_id', 'template_name')
ORDER BY column_name;

-- Verify visibility columns added to consultation_types
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'consultation_types'
AND column_name IN ('visible_to_hospitals', 'visible_to_doctors', 'visible_to_specializations')
ORDER BY column_name;

-- Check for NULL segment_id values
SELECT COUNT(*) as null_count
FROM consultation_type_segment_defaults
WHERE segment_id IS NULL;

SELECT COUNT(*) as null_count
FROM template_segment_configurations
WHERE segment_id IS NULL;
```

**Expected Results**:
- New columns exist in both junction tables ✅
- Visibility columns added to consultation_types ✅
- NULL count should be 0 (or documented exceptions) ✅

**If NULL values found**, run manual fixes:

```sql
-- Example fix (adjust UUIDs based on your data)
UPDATE consultation_type_segment_defaults
SET segment_id = (
    SELECT id FROM segment_definitions
    WHERE segment_code = consultation_type_segment_defaults.segment_code
    LIMIT 1
)
WHERE segment_id IS NULL;

UPDATE template_segment_configurations
SET segment_id = (
    SELECT id FROM segment_definitions
    WHERE segment_code = template_segment_configurations.segment_code
    LIMIT 1
)
WHERE segment_id IS NULL;
```

**Time Checkpoint**: _______________

---

#### Step 1.3: Migrate Template Ownership

```sql
\i backend/supabase/migrations/20251122100300_migrate_template_ownership.sql
```

**Monitor Output**:
- Watch for "NULL template_id" warnings in doctor_segment_configurations
- Note count of affected rows

**Verify**:

```sql
-- Verify templates.doctor_id exists (renamed from created_by_doctor_id)
SELECT column_name FROM information_schema.columns
WHERE table_name = 'templates' AND column_name = 'doctor_id';

-- Verify created_by_doctor_id doesn't exist (should return 0 rows)
SELECT column_name FROM information_schema.columns
WHERE table_name = 'templates' AND column_name = 'created_by_doctor_id';

-- Verify unique constraint exists
SELECT constraint_name FROM information_schema.table_constraints
WHERE table_name = 'templates' AND constraint_name = 'templates_doctor_code_unique';

-- Check doctor_segment_configurations.template_id populated
SELECT COUNT(*) as total,
       COUNT(template_id) as with_template_id,
       COUNT(*) - COUNT(template_id) as null_template_id
FROM doctor_segment_configurations;
```

**Expected Results**:
- templates.doctor_id exists ✅
- templates.created_by_doctor_id does NOT exist ✅
- Unique constraint exists ✅
- Most template_id values populated (some NULLs acceptable) ✅

**Time Checkpoint**: _______________

---

### Phase 3: Table Renames (BREAKING - 2 minutes downtime)

**⚠️ CRITICAL**: This phase causes downtime. Backend must be stopped during execution.

#### Step 3.1: Stop Backend Application

```bash
# Stop your backend service (method depends on deployment)
# Examples:
systemctl stop your-backend-service
# OR
docker stop your-backend-container
# OR
kill -TERM $(cat /var/run/backend.pid)
```

**Verify Application Stopped**:

```bash
# Check process is not running
ps aux | grep "python.*main.py"  # Should return nothing
# OR check port is free
lsof -i :8000  # Should return nothing
```

**Time Checkpoint (Downtime Start)**: _______________

---

#### Step 3.2: Rename Junction Tables

```sql
\i backend/supabase/migrations/20251122120000_rename_junction_tables.sql
```

**Monitor Output**:
- May see "relation already exists" for primary key (non-critical)
- Verify no fatal errors

**Verify**:

```sql
-- Verify old table names don't exist
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('consultation_type_segment_defaults', 'template_segment_configurations');
-- Should return 0 rows

-- Verify new table names exist
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('consultation_type_segments', 'template_segments');
-- Should return 2 rows

-- Verify constraints renamed
SELECT constraint_name, table_name
FROM information_schema.table_constraints
WHERE table_name IN ('consultation_type_segments', 'template_segments')
ORDER BY table_name, constraint_name;
```

**Expected Results**:
- Old table names do NOT exist ✅
- New table names exist ✅
- Constraints updated to new table names ✅

**Time Checkpoint**: _______________

---

### Phase 4.1: Cleanup Deprecated Columns (1 minute)

**Purpose**: Remove old columns and tables no longer needed

```sql
\i backend/supabase/migrations/20251122130000_cleanup_deprecated_columns.sql
```

**Monitor Output**:
- CASCADE drop will affect views and functions (expected)
- Note which views/functions are dropped (will be recreated in Phase 4.2)

**Verify**:

```sql
-- Verify columns dropped from segment_definitions
SELECT column_name FROM information_schema.columns
WHERE table_name = 'segment_definitions'
AND column_name IN ('consultation_type_id', 'template_id');
-- Should return 0 rows

-- Verify doctor_active_templates table dropped
SELECT table_name FROM information_schema.tables
WHERE table_name = 'doctor_active_templates';
-- Should return 0 rows

-- Verify visibility columns exist in consultation_types
SELECT column_name FROM information_schema.columns
WHERE table_name = 'consultation_types'
AND column_name IN ('visible_to_hospitals', 'visible_to_doctors', 'visible_to_specializations');
-- Should return 3 rows
```

**Expected Results**:
- consultation_type_id dropped from segment_definitions ✅
- template_id dropped from segment_definitions ✅
- doctor_active_templates table does NOT exist ✅
- Visibility columns exist ✅

**Time Checkpoint**: _______________

---

### Phase 4.2: Update RPC Functions (2 minutes)

**Purpose**: Update database functions to work with new schema

```sql
\i backend/supabase/migrations/20251122140000_update_edge_functions.sql
```

**Verify**:

```sql
-- Verify dropped functions don't exist
\df get_active_template_id_by_name
\df get_default_active_template_id
-- Should return "Did not find any function"

-- Verify updated functions exist with new signatures
\df apply_template_to_doctor
-- Should show: (uuid, uuid) - 2 parameters

\df get_doctor_segment_configuration
-- Should show: (uuid, uuid, uuid, character varying)

\df validate_segment_configuration
-- Should show: (uuid)

-- Count total RPC functions
SELECT COUNT(*) as total_functions
FROM information_schema.routines
WHERE routine_schema = 'public' AND routine_type = 'FUNCTION';
-- Should show 14 functions (2 dropped, 3 updated, 9 unchanged)
```

**Expected Results**:
- Dropped functions do NOT exist ✅
- Updated functions have correct signatures ✅
- Total function count is 14 ✅

**Time Checkpoint**: _______________

---

### Step 3.3: Start Backend Application

**Deploy Updated Backend Code**:

```bash
# Pull latest backend code
cd /path/to/backend
git pull origin main

# Install dependencies
pip install -r requirements.txt

# Start backend service
systemctl start your-backend-service
# OR
docker start your-backend-container
# OR
python main.py &
```

**Verify Application Started**:

```bash
# Check process is running
ps aux | grep "python.*main.py"

# Check port is listening
lsof -i :8000

# Test health endpoint
curl http://localhost:8000/health
# OR
curl http://your-production-domain.com/health
```

**Time Checkpoint (Downtime End)**: _______________

**Total Downtime**: _______________ (should be 10-15 minutes)

---

## ✅ Post-Deployment Verification

### Database Integrity Checks (5 minutes)

**Run All Verification Queries**:

```sql
-- 1. Verify all migrations applied
SELECT version, name, applied_at
FROM supabase_migrations
WHERE version >= '20251122100000'
ORDER BY version;
-- Should show 6 migrations

-- 2. Check foreign key constraints
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
AND tc.table_name IN ('segment_definitions', 'consultation_type_segments', 'template_segments',
                      'templates', 'doctor_segment_configurations')
ORDER BY tc.table_name, tc.constraint_name;
-- Verify all expected foreign keys exist

-- 3. Check indexes
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
AND tablename IN ('segment_definitions', 'consultation_type_segments', 'template_segments',
                  'templates', 'doctor_segment_configurations')
ORDER BY tablename, indexname;
-- Verify all necessary indexes exist

-- 4. Check data integrity
-- Verify no orphaned records
SELECT 'consultation_type_segments orphans' as check_name, COUNT(*) as orphans
FROM consultation_type_segments cts
LEFT JOIN segment_definitions sd ON cts.segment_id = sd.id
WHERE sd.id IS NULL

UNION ALL

SELECT 'template_segments orphans', COUNT(*)
FROM template_segments ts
LEFT JOIN segment_definitions sd ON ts.segment_id = sd.id
WHERE sd.id IS NULL

UNION ALL

SELECT 'doctor_segment_config orphans', COUNT(*)
FROM doctor_segment_configurations dsc
LEFT JOIN segment_definitions sd ON dsc.segment_id = sd.id
WHERE sd.id IS NULL;
-- All counts should be 0

-- 5. Verify segment ownership logic
SELECT segment_type, COUNT(*) as count,
       SUM(CASE WHEN doctor_id IS NULL THEN 1 ELSE 0 END) as null_doctor_id,
       SUM(CASE WHEN doctor_id IS NOT NULL THEN 1 ELSE 0 END) as has_doctor_id
FROM segment_definitions
GROUP BY segment_type;
-- system segments should have NULL doctor_id
-- doctor segments should have NOT NULL doctor_id

-- 6. Check triggers
SELECT trigger_name, event_object_table, action_statement
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table, trigger_name;
-- Verify all update_updated_at_column triggers exist
```

**Expected Results**:
- 6 migrations applied ✅
- All foreign keys intact ✅
- All indexes exist ✅
- No orphaned records (count = 0) ✅
- Segment ownership logic correct ✅
- All triggers exist ✅

---

### Backend API Tests (5 minutes)

**Test Critical Endpoints**:

```bash
# 1. Test template listing
curl -X GET "http://localhost:8000/api/v1/summary/templates/OP?filter_type=all" \
  -H "accept: application/json"

# 2. Test segment configuration
curl -X GET "http://localhost:8000/api/v1/summary/segments/OP" \
  -H "accept: application/json"

# 3. Test consultation types
curl -X GET "http://localhost:8000/api/v1/summary/consultation-types" \
  -H "accept: application/json"

# 4. Test extraction (with sample doctor_id and transcript)
curl -X POST "http://localhost:8000/api/v1/summary/extract" \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "Sample patient consultation transcript...",
    "consultation_type_code": "OP",
    "doctor_id": "YOUR_DOCTOR_UUID",
    "mode": "core"
  }'
```

**Expected Results**:
- All endpoints return 200 OK ✅
- No 500 Internal Server Errors ✅
- No database-related errors in logs ✅
- Responses contain expected data structure ✅

---

### Monitor Application Logs (10 minutes)

**Check for Errors**:

```bash
# View recent backend logs
tail -f /var/log/your-backend.log
# OR
docker logs -f your-backend-container
# OR
journalctl -u your-backend-service -f
```

**Watch For**:
- Database connection errors ❌
- Table not found errors ❌
- Column not found errors ❌
- Foreign key constraint violations ❌
- RPC function errors ❌

**Expected**: Clean logs with no database-related errors ✅

---

## 🔄 Rollback Procedure

**If Critical Errors Occur, Follow These Steps**:

### Option 1: Restore from Backup Tables (Fast - 5 minutes)

```sql
-- Stop backend application
-- Then restore tables from backups

BEGIN;

-- Drop new tables
DROP TABLE IF EXISTS consultation_type_segments CASCADE;
DROP TABLE IF EXISTS template_segments CASCADE;

-- Restore from backups
CREATE TABLE consultation_type_segment_defaults AS
SELECT * FROM consultation_type_segment_defaults_backup_20251122;

CREATE TABLE template_segment_configurations AS
SELECT * FROM template_segment_configurations_backup_20251122;

-- Restore dropped columns to segment_definitions
ALTER TABLE segment_definitions ADD COLUMN consultation_type_id UUID;
ALTER TABLE segment_definitions ADD COLUMN template_id UUID;

-- Restore doctor_active_templates table
CREATE TABLE doctor_active_templates AS
SELECT * FROM doctor_active_templates_backup_20251122;

-- Restore templates.created_by_doctor_id
ALTER TABLE templates RENAME COLUMN doctor_id TO created_by_doctor_id;

COMMIT;

-- Verify rollback
SELECT COUNT(*) FROM consultation_type_segment_defaults;
SELECT COUNT(*) FROM template_segment_configurations;
SELECT COUNT(*) FROM doctor_active_templates;
```

**Then**:
- Redeploy old backend code
- Restart application
- Verify functionality

---

### Option 2: Full Database Restore (Slow - 30+ minutes)

```bash
# Restore from full database backup (created in Phase 0)
pg_restore --clean --if-exists \
  -d postgresql://postgres:PASSWORD@db.PROJECTID.supabase.co:5432/postgres \
  /path/to/backup/production_backup_TIMESTAMP.dump
```

**Then**:
- Redeploy old backend code
- Restart application
- Verify functionality

---

## 📊 Success Criteria

Deployment is considered successful when:

- [ ] All 6 migrations applied successfully
- [ ] No database errors in application logs (10 min monitoring)
- [ ] All backend API tests pass
- [ ] All foreign keys and constraints intact
- [ ] No orphaned records found
- [ ] Segment ownership logic working correctly
- [ ] Frontend functionality unaffected (or Phase 6 deployed)
- [ ] User-facing features working normally

---

## 📝 Post-Deployment Tasks

### Immediate (Same Day)

- [ ] **Monitor application for 2-4 hours**
  - Check error logs every 30 minutes
  - Monitor API response times
  - Watch for database-related errors

- [ ] **Verify user-reported issues**
  - Check support channels
  - Test critical user workflows
  - Document any anomalies

- [ ] **Update deployment log**
  - Record deployment completion time
  - Note any issues encountered
  - Document resolutions applied

---

### Within 1 Week

- [ ] **Clean up backup tables** (after confirming stability)
  ```sql
  DROP TABLE IF EXISTS segment_definitions_backup_20251122;
  DROP TABLE IF EXISTS consultation_type_segment_defaults_backup_20251122;
  DROP TABLE IF EXISTS template_segment_configurations_backup_20251122;
  DROP TABLE IF EXISTS templates_backup_20251122;
  DROP TABLE IF EXISTS doctor_active_templates_backup_20251122;
  DROP TABLE IF EXISTS doctor_segment_configurations_backup_20251122;
  ```

- [ ] **Optional: Rename legacy index**
  ```sql
  ALTER INDEX template_segment_configurations_template_id_segment_code_key
  RENAME TO template_segments_template_id_segment_code_key;
  ```

- [ ] **Schedule Phase 6 deployment** (Frontend UI Changes)

---

### Within 1 Month

- [ ] **Review deprecation warnings** in logs
  - Identify deprecated function usage
  - Plan removal of deprecated functions

- [ ] **Implement feature enhancements** (if needed)
  - Doctor segment request workflow
  - Admin segment approval workflow
  - Consultation type visibility filtering

---

## 🆘 Emergency Contacts

**Database Issues**:
- DBA Contact: _______________
- Escalation: _______________

**Backend Issues**:
- Backend Lead: _______________
- On-Call Engineer: _______________

**Deployment Lead**:
- Name: _______________
- Phone: _______________
- Email: _______________

---

## 📚 Reference Documentation

**Migration Files**:
- Phase 0: `20251122100000_backup_before_rearchitecture.sql`
- Phase 1.1: `20251122100100_add_segment_ownership_tracking.sql`
- Phase 1.2: `20251122100200_add_junction_table_columns.sql`
- Phase 1.3: `20251122100300_migrate_template_ownership.sql`
- Phase 3: `20251122120000_rename_junction_tables.sql`
- Phase 4.1: `20251122130000_cleanup_deprecated_columns.sql`
- Phase 4.2: `20251122140000_update_edge_functions.sql`

**Implementation Summaries**:
- Phase 1: `PHASE_1_COMPLETION_SUMMARY.md`
- Phase 3: `PHASE_3_COMPLETION_SUMMARY.md`
- Phase 4: `PHASE_4_STATUS.md`
- Phase 5.1: `PHASE_5_COMPLETION_SUMMARY.md`
- Phase 5.2: `PHASE_5.2_RPC_CALLS_UPDATE_SUMMARY.md`
- Phase 5.3: `PHASE_5.3_DROPPED_COLUMNS_CLEANUP.md`

**Review Documents**:
- Implementation review: `IMPLEMENTATION_REVIEW_PHASES_1-5.md`
- Rearchitecture guide: `REARCHITECTURE_IMPLEMENTATION_GUIDE.md`

---

## ✅ Deployment Sign-Off

**Deployment Completed By**: _______________

**Date**: _______________

**Time Started**: _______________

**Time Completed**: _______________

**Total Downtime**: _______________

**Issues Encountered**:
_______________________________________________________________
_______________________________________________________________
_______________________________________________________________

**Resolutions Applied**:
_______________________________________________________________
_______________________________________________________________
_______________________________________________________________

**Sign-Off**:
- Deployment Lead: _______________ Date: _______________
- Database Administrator: _______________ Date: _______________
- Backend Lead: _______________ Date: _______________

---

**End of Consolidated Deployment Guide - Phases 1-5**

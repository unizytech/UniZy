# Consultation History API - Latency Optimization Plan

**Endpoint:** `GET /api/v1/patients/{patientId}/consultations`
**File:** `backend/routers/patient_history.py` (lines 1521-1648)

## Current Sequential DB Calls (Critical Path)

| # | Function | DB Query | Notes |
|---|----------|----------|-------|
| 1 | `resolve_patient_id()` (line 341) | `patients` by `patient_id` | Always runs |
| 2 | `resolve_patient_id()` (line 353) | `patients` by `id` (UUID fallback) | Runs if #1 finds nothing |
| 3 | `get_patient_info()` (line 311) | `patients` by `id` | **Redundant** — same table as step 1/2 |
| 4 | Count query (line 566) | `medical_extractions` count | Separate round-trip |
| 5 | Main query (line 571) | `medical_extractions` paginated | Separate round-trip |
| 6 | `batch_get_doctor_names()` (line 442) | `doctors` IN query | After results return |
| 7 | `batch_get_consultation_type_names()` (line 464) | `consultation_types` IN query | After results return |

## Root Causes of Latency

1. **Redundant patient lookup** (lines 336-399, 309-319): `resolve_patient_id` already queries the `patients` table, then `get_patient_info` queries it again for the same row. That's 2 (or 3) round-trips just to get patient info.

2. **Sequential count + data queries** (lines 559-571): The count query and the main data query run sequentially. They could run in parallel since they're independent.

3. **Batch lookups run sequentially** (lines 578-579): `batch_get_doctor_names` and `batch_get_consultation_type_names` are independent of each other but run sequentially.

4. **All helper functions are synchronous** (not `async`): `resolve_patient_id`, `get_patient_info`, `batch_get_doctor_names`, `batch_get_consultation_type_names` are all synchronous blocking calls. No concurrency is possible.

5. **Fetching full extraction JSON** (lines 548-550): `edited_extraction_json` and `original_extraction_json` are potentially large JSON blobs fetched for every row, just to extract a diagnosis and chief complaint preview.

## Estimated Latency

Each Supabase REST API call adds ~50-150ms of network latency.

- **Best case** (patient found by external_id): ~5 calls x 50ms = **250ms+**
- **Worst case** (UUID fallback): ~7 calls x 100ms = **700ms+**

## Proposed Fixes (Priority Order)

### Fix 1: Merge resolve + patient_info into a single query
- Combine `resolve_patient_id()` and `get_patient_info()` into one function that returns both the UUID and patient info in a single DB call.
- **Saves:** 1-2 round-trips

### Fix 2: Run count + data queries concurrently
- Use `asyncio.gather()` to run the count query and the paginated data query in parallel.
- **Saves:** 1 round-trip (~50-150ms)

### Fix 3: Run batch lookups concurrently
- Use `asyncio.gather()` to run `batch_get_doctor_names` and `batch_get_consultation_type_names` in parallel.
- **Saves:** 1 round-trip (~50-150ms)

### Fix 4: Select only needed fields from extraction JSON
- Instead of fetching full `edited_extraction_json` and `original_extraction_json`, use a Supabase RPC or computed column to extract only diagnosis/chief complaint at the DB level.
- Alternatively, store preview fields (primary_diagnosis, chief_complaint) as separate columns on `medical_extractions`.
- **Saves:** Significant payload reduction, faster network transfer

### Fix 5: Use a database view or RPC with JOINs
- Create a Postgres view/function that joins `medical_extractions` with `doctors` and `consultation_types`, returning all needed data in a single query.
- **Saves:** Reduces 3 queries (main + doctor names + consultation types) to 1

## Expected Improvement

| Scenario | Before | After (all fixes) |
|----------|--------|-------------------|
| Best case | ~250ms | ~100-150ms |
| Worst case | ~700ms | ~150-200ms |

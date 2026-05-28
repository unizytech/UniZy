# Prescreen API Latency Optimization Plan

**Endpoint:** `GET /api/v1/patients/{patient_id}/prescreen`
**File:** `backend/routers/patient_history.py:3527-3639`

---

## Root Causes (ranked by impact)

### 1. No Parallelism — Independent queries run sequentially

`patient_history.py:3553-3607` — All these calls are independent but run sequentially:

```
1. resolve_patient_id_or_404()
2. get_patient_info()
3. consultation count query
4. get_latest_prescreen_extraction()
5. build_emotion_pattern_summary()
6. get_top_interventions()
7. get_caution_and_summary_from_last_extraction()
8. build_clinical_timeline_data()
9. get_last_prescription_for_prescreen()
```

Steps 4–9 have **zero dependencies on each other** but run one after another.

---

### 2. Redundant Duplicate Queries (~4x the same table)

Functions `get_top_interventions`, `get_caution_and_summary_from_last_extraction`, `get_last_prescription_for_prescreen`, and `build_clinical_timeline_data` **all query `medical_extractions`** with the same filters:
- `.eq("patient_id", patient_uuid)`
- `.eq("doctor_id", doctor_id)`
- `.select("*, recording_sessions(template_code)")`
- `.order("created_at", desc=True)`

The same "find latest non-PRESCREEN extraction" logic is repeated 4 separate times with 4 separate DB round-trips.

---

### 3. N+1 Queries in `build_emotion_pattern_summary`

`patient_history.py:615-619` — For each of the N extraction IDs (typically 2), it makes a **separate DB query** to `extraction_segments`:

```python
for ext_id in extraction_ids:
    segments_result = supabase.table("extraction_segments")\
        .select("segment_code, segment_value")\
        .eq("extraction_id", ext_id)\
        .execute()
```

This turns 1 potential batch query into 2+ sequential queries.

---

### 4. N+1 in `get_caution_and_summary_from_last_extraction`

`patient_history.py:911-917` — Two separate calls to `get_segment_from_extraction()` for CAUTION and SUMMARY, each hitting the DB:

```python
caution = get_segment_from_extraction(extraction_id, "CAUTION")
summary = get_segment_from_extraction(extraction_id, "SUMMARY")
```

Could be a single query with `.in_("segment_code", ["CAUTION", "SUMMARY"])`.

---

### 5. Full Table Scan in `build_clinical_timeline_data`

`patient_history.py:1010-1013` — Fetches **ALL extractions** for the patient (no limit) just to build a historical diagnosis set:

```python
all_extractions_result = supabase.table("medical_extractions")\
    .select("original_extraction_json, edited_extraction_json, created_at, recording_sessions(template_code)")\
    .eq("patient_id", str(patient_uuid))\
    .execute()  # No .limit() — fetches everything
```

For patients with many consultations, this pulls all extraction JSON blobs.

---

### 6. Synchronous Supabase Client Blocking the Event Loop

All `.execute()` calls use the **sync** Supabase client. Despite the endpoint being `async def`, every DB call blocks the thread. With ~15 sequential queries, each with network latency to Supabase, the total adds up.

---

## Total Query Count Per Request: ~15 DB round-trips

| Step | Queries |
|------|---------|
| Patient resolution + info | 2 |
| Consultation count | 1 |
| Latest prescreen extraction | 1 |
| Emotion pattern summary | 1 + 2 (N+1) = 3 |
| Top interventions | 1 + 1 = 2 |
| Caution & summary | 1 + 2 = 3 |
| Clinical timeline | 1 + 1 (full scan) = 2 |
| Last prescription | 1 |
| **Total** | **~15** |

At ~50-150ms per Supabase round-trip, that's **750ms–2.25s** just in network latency, plus the full-scan data processing time.

---

## Proposed Fixes

### Fix 1: Single shared extraction fetch + pass to helpers

Fetch the "latest non-PRESCREEN extractions" ONCE and pass the result to all helper functions:

```python
# One query to get recent extractions (replaces 4 duplicate queries)
recent_extractions = supabase.table("medical_extractions")\
    .select("*, recording_sessions(template_code)")\
    .eq("patient_id", str(patient_uuid))\
    .eq("doctor_id", doctor_id)\
    .order("created_at", desc=True)\
    .limit(10)\
    .execute()

non_prescreen = filter_prescreen_extractions(recent_extractions.data or [], max_results=5)
latest_non_prescreen = non_prescreen[0] if non_prescreen else None
```

Then pass `latest_non_prescreen` / `non_prescreen` to each helper.

### Fix 2: Parallelize independent calls with asyncio.gather

```python
import asyncio

# After resolving patient and getting shared extraction data:
results = await asyncio.gather(
    run_in_executor(get_latest_prescreen_extraction, patient_uuid, doctor_id),
    run_in_executor(build_emotion_pattern_summary, patient_uuid, doctor_id, 2),
    run_in_executor(get_top_interventions_from_extraction, latest_non_prescreen),
    run_in_executor(get_caution_and_summary_batch, extraction_id),
    run_in_executor(build_clinical_timeline_data, patient_uuid, doctor_id, 5),
    run_in_executor(get_last_prescription_from_extraction, latest_non_prescreen),
)
```

### Fix 3: Batch segment queries

Replace N+1 patterns with `.in_()` queries:

```python
# Emotion: batch fetch segments for all extraction IDs
segments_result = supabase.table("extraction_segments")\
    .select("extraction_id, segment_code, segment_value")\
    .in_("extraction_id", extraction_ids)\
    .execute()

# Caution+Summary: single query
segments = supabase.table("extraction_segments")\
    .select("segment_code, segment_value")\
    .eq("extraction_id", extraction_id)\
    .in_("segment_code", ["CAUTION", "SUMMARY"])\
    .execute()
```

### Fix 4: Limit clinical timeline historical query

Add a reasonable limit or use a simpler approach:

```python
# Instead of fetching ALL extractions, limit to last 20
all_extractions_result = supabase.table("medical_extractions")\
    .select("original_extraction_json, edited_extraction_json, created_at, recording_sessions(template_code)")\
    .eq("patient_id", str(patient_uuid))\
    .limit(20)\
    .execute()
```

---

## Expected Improvement

| Metric | Before | After |
|--------|--------|-------|
| DB queries | ~15 | ~5-6 |
| Network round-trips | ~15 sequential | ~3-4 parallel batches |
| Estimated latency | 750ms–2.25s | 150ms–450ms |
| Improvement | — | **~5x faster** |

# Pipeline Cache Reference

This document provides a comprehensive reference for all caches used in the recording/extraction pipeline.

## Cache Overview

The pipeline uses multiple in-memory caches to reduce database queries and improve performance. All caches have invalidation logic that triggers when the underlying data is updated.

---

## Cache Reference Table

```
┌─────────────────────────────────┬──────────────────────────────┬─────────┬────────────────┬──────────────────────────────────────────────────┐
│           Cache Name            │           Location           │   TTL   │     Scope      │               Invalidation Trigger               │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _consultation_type_cache        │ supabase_service.py:52       │ 8 hours │ By ID          │ Create/Delete/Update consultation type           │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _consultation_type_by_code_cache│ supabase_service.py:56       │ 8 hours │ By code        │ Same as above                                    │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _template_by_code_cache         │ supabase_service.py:60       │ 8 hours │ By code        │ Create/Update/Delete template                    │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _template_by_id_cache           │ supabase_service.py:63       │ 8 hours │ By ID          │ Same as above                                    │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _template_unified_cache         │ supabase_service.py:67       │ 8 hours │ By key*        │ Same as above                                    │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _doctor_hospital_cache          │ supabase_service.py:48       │ 8 hours │ By doctor      │ Doctor profile updates                           │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _doctor_hospital_cache (auth)   │ auth_service.py:42           │ 10 min  │ By doctor      │ Doctor profile updates                           │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _list_availability_cache        │ extraction_service.py:27     │ ∞ (1yr) │ By doctor      │ Medicine/investigation list updates              │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _doctor_medicines_cache         │ medicine_service.py:48       │ 8 hours │ By doctor      │ Doctor medicine list updates                     │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _hospital_medicines_cache       │ medicine_service.py:49       │ 8 hours │ By hospital    │ Hospital medicine list updates                   │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _extraction_model_cache         │ supabase_service.py:1261     │ Forever │ By mode        │ Processing mode updates                          │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _triage_model_cache             │ supabase_service.py:1311     │ Forever │ By mode        │ Processing mode updates                          │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _merge_model_cache              │ supabase_service.py:1359     │ Forever │ By mode        │ Processing mode updates                          │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _compare_model_cache            │ supabase_service.py:1407     │ Forever │ By mode        │ Processing mode updates                          │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _emotion_model_cache            │ supabase_service.py:1455     │ Forever │ By mode        │ Processing mode updates                          │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _insights_model_cache           │ supabase_service.py:1503     │ Forever │ By mode        │ Processing mode updates                          │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _combined_emotion_prompt_cache  │ supabase_service.py:4295     │ Forever │ By template    │ Template/segment updates                         │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _cache_registry (Gemini)        │ gemini_cache_service.py:44   │ 60 min  │ By prompt type │ Template/prompt content changes                  │
├─────────────────────────────────┼──────────────────────────────┼─────────┼────────────────┼──────────────────────────────────────────────────┤
│ _admin_users_cache              │ auth_service.py:38           │ 10 min  │ By user        │ Admin user updates                               │
└─────────────────────────────────┴──────────────────────────────┴─────────┴────────────────┴──────────────────────────────────────────────────┘
```

**\*_template_unified_cache key format:** `template_code:doctor_id` (colon separator)

---

## Invalidation Functions

| Function | Location | Clears |
|----------|----------|--------|
| `invalidate_consultation_type_cache()` | `supabase_service.py:100` | `_consultation_type_cache`, `_consultation_type_by_code_cache` (clears BOTH when either param provided) |
| `invalidate_template_cache()` | `supabase_service.py:140` | `_template_by_code_cache`, `_template_by_id_cache`, `_template_unified_cache` |
| `invalidate_doctor_hospital_cache()` | `supabase_service.py:75` | `_doctor_hospital_cache` |
| `invalidate_processing_mode_cache()` | `supabase_service.py:186` | `_extraction_model_cache`, `_triage_model_cache`, `_merge_model_cache`, `_compare_model_cache`, `_emotion_model_cache`, `_insights_model_cache` |
| `invalidate_list_cache()` | `extraction_service.py` | `_list_availability_cache` (single doctor) |
| `invalidate_list_cache_by_hospital()` | `extraction_service.py` | `_list_availability_cache` (all entries) |
| `invalidate_doctor_medicine_cache()` | `medicine_service.py` | `_doctor_medicines_cache` (single doctor) |
| `invalidate_all_doctor_medicine_caches()` | `medicine_service.py` | `_doctor_medicines_cache` (all entries) |
| `invalidate_hospital_medicine_cache()` | `medicine_service.py` | `_hospital_medicines_cache` (single hospital) |
| `invalidate_all_hospital_medicine_caches()` | `medicine_service.py` | `_hospital_medicines_cache` (all entries) |
| `invalidate_cache()` | `gemini_cache_service.py:202` | `_cache_registry` (Gemini context cache) |

---

## Global Cache Refresh

**Endpoint:** `POST /api/v1/summary/admin/cache/refresh`

**UI Button:** "Refresh Cache" in VHRScreen.tsx (requires admin role)

**Clears ALL of the following caches:**
| Cache | Function Called |
|-------|-----------------|
| `consultation_type_cache` | `invalidate_consultation_type_cache()` |
| `template_cache` | `invalidate_template_cache()` |
| `doctor_hospital_cache` | `invalidate_doctor_hospital_cache()` |
| `processing_mode_cache` | `invalidate_processing_mode_cache()` |
| `hospital_medicine_cache` | `invalidate_all_hospital_medicine_caches()` |
| `doctor_medicine_cache` | `invalidate_all_doctor_medicine_caches()` |
| `list_availability_cache` | `invalidate_list_cache_by_hospital()` |

**Note:** Gemini context cache (60-min TTL) is managed by Google API and cannot be invalidated from the application.

---

## Endpoints with Cache Invalidation

### Consultation Type Updates

All consultation type update endpoints invalidate `_consultation_type_cache`:

| Endpoint | Field Updated | Invalidation |
|----------|---------------|--------------|
| `PATCH /admin/consultation-types/{code}/emotion-analysis` | `enable_emotion_analysis` | `invalidate_consultation_type_cache(type_code=...)` |
| `PATCH /admin/consultation-types/{code}/emotion-mode` | `emotion_extraction_mode` | `invalidate_consultation_type_cache(type_code=...)` |
| `PATCH /admin/consultation-types/{code}/audio-emotion-mode` | `audio_emotion_mode` | `invalidate_consultation_type_cache(type_code=...)` |
| `PATCH /admin/consultation-types/{code}/triage-analysis` | `enable_triage_analysis` | `invalidate_consultation_type_cache(type_code=...)` |
| `PATCH /admin/consultation-types/{code}/consultation-insights` | `enable_consultation_insights` | `invalidate_consultation_type_cache(type_code=...)` |
| `POST /admin/consultation-types` | Create new | `invalidate_consultation_type_cache(type_code=...)` |
| `DELETE /admin/consultation-types/{code}` | Delete | `invalidate_consultation_type_cache(type_code=...)` |

### Template Updates

| Endpoint | Invalidation |
|----------|--------------|
| `POST /admin/templates` | `invalidate_template_cache(template_code=...)` |
| `PUT /admin/templates/{code}` | `invalidate_template_cache(template_code=...)` |
| `DELETE /admin/templates/{code}` | `invalidate_template_cache(template_code=...)` |

### Processing Mode Updates

| Endpoint | Invalidation |
|----------|--------------|
| `POST /processing-modes` | `invalidate_processing_mode_cache(mode_code=...)` |
| `PUT /processing-modes/{code}` | `invalidate_processing_mode_cache(mode_code=...)` |
| `DELETE /processing-modes/{code}` | `invalidate_processing_mode_cache(mode_code=...)` |

---

## Cache Scope Definitions

| Scope | Description |
|-------|-------------|
| **By ID** | Cache key is the UUID of the entity |
| **By code** | Cache key is the string code (e.g., `OP`, `DISCHARGE`) |
| **By doctor** | Cache key includes doctor_id - scoped to specific doctor |
| **By hospital** | Cache key includes hospital_id - scoped to specific hospital |
| **By mode** | Cache key is the processing mode code |
| **By prompt type** | Cache key is the Gemini prompt type (e.g., `TEMPLATE_OP_CORE`) |
| **By template** | Cache key is template_id - scoped to specific template |
| **By key** | Composite key format (see cache-specific documentation) |

---

## TTL Values

| TTL | Value | Used For |
|-----|-------|----------|
| **∞ (1 year)** | 31536000 seconds | List availability cache (invalidated on update) |
| **8 hours** | 28800 seconds | Configuration data that rarely changes |
| **60 minutes** | 3600 seconds | Gemini context cache (API-side) |
| **10 minutes** | 600 seconds | Auth/admin user cache |
| **Forever** | No expiry | Model selection caches (invalidated on update) |

---

## Pipeline Cache Flow

```
Recording Upload
       │
       ▼
┌──────────────────┐
│ _consultation_   │ ◄── Cached consultation type settings
│ type_cache       │     (emotion_mode, triage, insights)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ _template_       │ ◄── Cached template configuration
│ unified_cache    │     Key: template_code:doctor_id
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ _list_           │ ◄── Cached medicine/investigation
│ availability_    │     list availability (∞ TTL)
│ cache            │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ _cache_registry  │ ◄── Gemini context cache
│ (Gemini)         │     (60-min TTL, system prompts)
└────────┬─────────┘
         │
         ▼
    Extraction
```

---

## Timing Impact

| Cache | HIT Savings | MISS Cost |
|-------|-------------|-----------|
| List availability | ~0.6s | 0.6s (DB query) |
| Template cache (Gemini) | ~1.9s | 1.9s (API call) |
| Template unified | ~0.3s | 0.3s (DB query) |
| Consultation type | ~0.1s | 0.1s (DB query) |

**Total potential savings per request with all cache HITs: ~2.9s**

---

## Troubleshooting

### Cache Not Updating

If settings changes aren't taking effect:

1. **Check if invalidation was called** - Look for `[CACHE_INVALIDATE]` in logs
2. **Click "Refresh Cache" button** - Clears all pipeline caches immediately
3. **Restart backend** - Clears all in-memory caches
4. **Wait for TTL expiry** - Max 8 hours for most caches (list cache is infinite but invalidated on update)

### Cross-Cache Invalidation (Important!)

The consultation type cache has TWO separate dictionaries:
- `_consultation_type_cache` - keyed by UUID (used by `get_consultation_type_by_id_cached`)
- `_consultation_type_by_code_cache` - keyed by code like "OP" (used by `get_consultation_type_by_code`)

**Fixed (Jan 2025):** The `invalidate_consultation_type_cache()` function now clears BOTH caches when either `type_code` or `consultation_type_id` is provided. Previously, passing only `type_code` would leave stale data in the ID-based cache.

### Template Unified Cache Key Format

**Fixed (Jan 2025):** The cache invalidation now correctly uses colon separator (`:`) to match the actual key format:
- Key format: `template_code:doctor_id`
- Invalidation searches for: `template_code + ":"` (was incorrectly using `_`)

### Manual Cache Clear

To clear all caches, restart the backend:
```bash
pkill -f "python main.py" && ./start-backend.sh
```

---

## Adding New Caches

When adding a new cache:

1. Define cache variable with TTL: `_new_cache: TTLCache = TTLCache(maxsize=100, ttl=28800)`
2. Create invalidation function: `def invalidate_new_cache(...)`
3. Call invalidation in all update endpoints
4. Add to this documentation

---

*Last updated: January 2025*

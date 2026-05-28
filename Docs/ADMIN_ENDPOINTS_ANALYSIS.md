# Admin Endpoints Analysis - Segment Management

## Question
> If I create a new consultation type, all common segments are inherited into this consultation type. Is there presently an option to add new segments from list of all segments?

## Answer
**No, there is currently NO endpoint to directly "link" or "add" existing segments from other consultation types to a new consultation type.**

---

## Current Consultation Type Creation Flow

### 1. Create New Consultation Type
**Endpoint**: `POST /api/v1/summary/admin/consultation-types`

**What Happens Automatically:**
```
New Consultation Type Created
↓
Automatically inherits ALL common segments (is_common=true)
↓
Ready to use with common segments only
```

**Documentation** (from endpoint docstring):
- ✅ "New consultation types automatically inherit all common segments"
- ✅ "Common segments are visible to all consultation types by default"
- ℹ️ "You can later add type-specific segments or exclude common ones"

---

## Current Options to Add Segments to a New Consultation Type

### ❌ Option 1: Direct Link/Assignment (NOT AVAILABLE)
**Does NOT exist**: No endpoint to "assign" or "link" an existing segment from consultation type A to consultation type B.

### ✅ Option 2: Clone an Existing Segment
**Endpoint**: `POST /api/v1/summary/admin/segments/clone`

**Request:**
```json
{
  "parent_segment_code": "DIAGNOSIS",
  "new_segment_code": "DIAGNOSIS_EMERGENCY",
  "new_segment_name": "Diagnosis (Emergency)",
  "consultation_type_id": "uuid-of-emergency-type"
}
```

**What Happens:**
- Creates a NEW segment as a copy of the parent
- New segment is specific to the consultation type
- Parent tracking maintained (can sync updates later)
- Independent modification allowed

**Use Case**: "I want EMERGENCY to have the same DIAGNOSIS segment as OP"

### ✅ Option 3: Create a New Consultation-Type-Specific Segment
**Endpoint**: `POST /api/v1/summary/admin/segments`

**Request:**
```json
{
  "segment_code": "EMERGENCY_TRIAGE",
  "segment_name": "Emergency Triage",
  "consultation_type_code": "EMERGENCY",
  "prompt_section_text": "Extract triage information...",
  "schema_definition_json": {...},
  "default_category": "core",
  "display_order": 1,
  "is_common": false
}
```

**What Happens:**
- Creates a brand new segment for that consultation type
- No relationship to existing segments
- Must define prompt and schema from scratch

**Use Case**: "I want EMERGENCY to have a unique TRIAGE segment"

### ✅ Option 4: Make Segment Common (Not Recommended for Specific Segments)
**Endpoint**: `PUT /api/v1/summary/admin/segments/{segment_code}`

**Request:**
```json
{
  "is_common": true
}
```

**What Happens:**
- Segment becomes visible to ALL consultation types
- Loses consultation-type specificity
- Not ideal for type-specific segments

**Use Case**: "This segment should be available to everyone" (e.g., Patient Information, Report Metadata)

---

## Gap Analysis

### Missing Functionality
❌ **No "Link Existing Segment" Endpoint**

**What's Missing:**
```
POST /api/v1/summary/admin/consultation-types/{consultation_type_code}/segments/link

Request:
{
  "segment_codes": ["DIAGNOSIS", "HISTORY", "PRESCRIPTION"]
}

Expected Behavior:
- Links existing segments to consultation type WITHOUT cloning
- Segments remain shared across consultation types
- Changes to original segment affect all linked consultation types
```

**Why This Might Be Needed:**
- Avoid duplicate segment definitions
- Share segments across multiple consultation types
- Maintain single source of truth for common clinical concepts

**Why This Doesn't Exist (Architecture Design):**
The current database schema has:
```sql
segment_definitions (
  id UUID,
  segment_code TEXT,
  consultation_type_id UUID,  -- ONE-TO-ONE relationship
  is_common BOOLEAN
)
```

**Current Design Philosophy:**
- Each segment belongs to EITHER:
  - One specific consultation type (consultation_type_id = UUID)
  - All consultation types (is_common = true)
- No many-to-many relationship between segments and consultation types

---

## Workaround: Use Clone Endpoint

If you want to add segments from OP to a new EMERGENCY consultation type:

**Step 1**: Get all OP segments
```bash
GET /api/v1/summary/admin/segments?consultation_type_code=OP
```

**Step 2**: Clone each segment you want
```bash
POST /api/v1/summary/admin/segments/clone
{
  "parent_segment_code": "DIAGNOSIS",
  "new_segment_code": "DIAGNOSIS_EMERGENCY",
  "new_segment_name": "Diagnosis",
  "consultation_type_id": "emergency-consultation-type-uuid"
}
```

**Step 3**: Repeat for each segment (HISTORY, PRESCRIPTION, etc.)

**Benefits:**
- ✅ Parent tracking maintained
- ✅ Can sync updates from parent: `POST /admin/segments/DIAGNOSIS_EMERGENCY/sync-from-parent`
- ✅ Can customize per consultation type

**Drawbacks:**
- ❌ Creates duplicate segment definitions
- ❌ Manual process (not bulk operation)
- ❌ Need to manage updates separately

---

## Recommended Solution (If Feature Needed)

### Option A: Add Many-to-Many Link Endpoint (Recommended)

**Database Change:**
```sql
CREATE TABLE consultation_type_segments (
  id UUID PRIMARY KEY,
  consultation_type_id UUID REFERENCES consultation_types(id),
  segment_definition_id UUID REFERENCES segment_definitions(id),
  is_enabled BOOLEAN DEFAULT true,
  created_at TIMESTAMP
);
```

**New Endpoint:**
```
POST /api/v1/summary/admin/consultation-types/{consultation_type_code}/segments/link
Body: { "segment_codes": ["DIAGNOSIS", "HISTORY"] }
```

**Benefit:** True segment reusability without duplication

### Option B: Bulk Clone Endpoint (Quick Win)

**New Endpoint:**
```
POST /api/v1/summary/admin/consultation-types/{consultation_type_code}/segments/clone-bulk
Body: {
  "source_consultation_type_code": "OP",
  "segment_codes": ["DIAGNOSIS", "HISTORY", "PRESCRIPTION"]
}
```

**Benefit:** Automates current clone process

### Option C: Segment Templates (Future Enhancement)

Create "segment templates" that can be instantiated for any consultation type:
```
segment_templates (shared definitions)
  ↓ instantiate
segment_instances (consultation-type-specific)
```

---

## Current Endpoints Summary

| Endpoint | Method | Purpose | Can Add Segments? |
|----------|--------|---------|-------------------|
| `/admin/consultation-types` | POST | Create consultation type | ❌ No (only inherits common) |
| `/admin/segments` | POST | Create new segment | ✅ Yes (create new) |
| `/admin/segments` | GET | List all segments | ℹ️ View only |
| `/admin/segments/clone` | POST | Clone segment | ✅ Yes (clone existing) |
| `/admin/segments/{code}` | PUT | Update segment | ❌ No (update only) |
| `/admin/segments/{code}` | DELETE | Delete segment | ❌ No (delete only) |

---

## Conclusion

**Current State:**
- ❌ No direct "link existing segment" functionality
- ✅ Can clone segments from other consultation types
- ✅ Common segments automatically inherited

**If You Need to Add Segments:**
1. **For reusable segments**: Use clone endpoint with parent tracking
2. **For unique segments**: Create new segment with consultation_type_code
3. **For truly universal segments**: Make segment common (is_common=true)

**Recommendation:**
If you frequently need to add existing segments to new consultation types, consider implementing **Option B: Bulk Clone Endpoint** as a quick win, or **Option A: Many-to-Many Link Endpoint** for a more robust solution.

---

**Date**: 2025-11-10
**Status**: Gap Identified
**Impact**: Medium (workaround exists via cloning)

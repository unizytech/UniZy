# Development Plan

**Last Updated:** 2025-11-11 07:53:14

## Current Plan

# Implementation Plan: Background Emotion/Subtext Extraction

## Overview
Add emotion analysis as a **background task** that triggers 20 seconds after medical extraction starts, runs independently, stores results when complete, and links to the same extraction_id.

## Final Requirements
- ✅ **Storage**: 5 individual segments linked to same extraction_id
- ✅ **Model**: Gemini 2.5 Flash
- ✅ **Control**: Admin toggle at consultation_type level
- ✅ **Defaults**: OP/OP_CONCISE = ON, DISCHARGE/RESPIRATORY = OFF
- ✅ **Behavior**: Non-blocking background task (20s delay after extraction starts)
- ✅ **Error handling**: Log and flag if fails

## Architecture: Fire-and-Forget Background Task

```
User requests extraction
  ↓
Medical extraction starts (returns immediately)
  ↓
Backend schedules background task (20s delay)
  ↓
[User receives medical results]
  ↓
[20 seconds later]
  ↓
Emotion extraction runs in background
  ↓
Results stored with same extraction_id
  ↓
Flag updated: emotion_extraction_completed = true
```

---

## Changes Required

### 1. Database (Supabase)

#### A. Update `consultation_types` table
```sql
ALTER TABLE consultation_types 
ADD COLUMN enable_emotion_analysis BOOLEAN DEFAULT FALSE;

-- Set defaults
UPDATE consultation_types SET enable_emotion_analysis = TRUE 
WHERE type_code IN ('OP', 'OP_CONCISE');

UPDATE consultation_types SET enable_emotion_analysis = FALSE 
WHERE type_code IN ('DISCHARGE', 'RESPIRATORY');
```

#### B. Update `medical_extractions` table
```sql
ALTER TABLE medical_extractions 
ADD COLUMN emotion_extraction_started BOOLEAN DEFAULT FALSE,
ADD COLUMN emotion_extraction_completed BOOLEAN DEFAULT FALSE,
ADD COLUMN emotion_extraction_failed BOOLEAN DEFAULT FALSE,
ADD COLUMN emotion_extraction_error TEXT,
ADD COLUMN emotion_extraction_started_at TIMESTAMP,
ADD COLUMN emotion_extraction_completed_at TIMESTAMP;
```

#### C. Create 5 emotion segment definitions
Insert into `segment_definitions`:
- `ANXIETY_PRE_CONSULTATION`
- `ANXIETY_POST_CONSULTATION`
- `OTHER_EMOTIONS_DETECTED`
- `FINANCIAL_CONCERNS`
- `TREATMENT_COMPLIANCE_LIKELIHOOD`

Configuration:
- `consultation_type_id` = NULL (not type-specific, used for OP types only)
- `is_common` = FALSE
- `default_category` = 'additional'
- `segment_type` = 'emotion'
- `is_required` = FALSE

---

### 2. Backend - Prompts (`backend/services/emotion_prompts.py` - NEW)

Create system prompt and schema for emotion analysis:

```python
EMOTION_ANALYSIS_SYSTEM_PROMPT = """
You are a medical psychology expert analyzing patient-doctor consultations.
Extract emotional and subtext indicators from the transcript.

Focus on:
1. Anxiety levels at conversation start and end
2. Emotional states (distress, agitation, fear, relief, etc.)
3. Financial concerns about treatment costs
4. Likelihood of treatment adherence

Use clinical terminology and be conservative in assessments.
"""

EMOTION_SEGMENTS_SCHEMA = {
    "ANXIETY_PRE_CONSULTATION": {
        "type": "object",
        "properties": {
            "level": {"enum": ["None", "Mild", "Moderate", "Severe"]},
            "indicators": {"type": "array"},
            "timestamp": {"type": "string"},
            "confidence": {"enum": ["Low", "Medium", "High"]}
        }
    },
    # ... 4 more segments
}
```

---

### 3. Backend - Service (`backend/services/gemini_service.py`)

#### Add emotion extraction function
```python
async def extract_emotion_analysis(
    transcript: str,
    extraction_id: uuid.UUID,
    model: str = "gemini-2.5-flash"
) -> Dict[str, Any]:
    """
    Extract emotional and subtext analysis.
    
    Returns 5 segments:
    - ANXIETY_PRE_CONSULTATION
    - ANXIETY_POST_CONSULTATION  
    - OTHER_EMOTIONS_DETECTED
    - FINANCIAL_CONCERNS
    - TREATMENT_COMPLIANCE_LIKELIHOOD
    """
    try:
        # Generate content with Gemini Flash
        response = await client.aio.models.generate_content(...)
        
        # Save segments to database
        save_emotion_segments(extraction_id, emotion_data)
        
        # Update extraction flags
        update_extraction_emotion_status(
            extraction_id,
            completed=True,
            failed=False
        )
        
        return emotion_data
        
    except Exception as e:
        logger.error(f"Emotion extraction failed: {e}")
        update_extraction_emotion_status(
            extraction_id,
            completed=False,
            failed=True,
            error=str(e)
        )
        raise
```

---

### 4. Backend - Background Task (`backend/services/background_tasks.py` - NEW)

Create background task scheduler:

```python
import asyncio
from typing import Optional
import uuid

async def schedule_emotion_extraction(
    transcript: str,
    extraction_id: uuid.UUID,
    consultation_type_id: uuid.UUID,
    delay_seconds: int = 20
):
    """
    Schedule emotion extraction as background task.
    
    Args:
        transcript: Full consultation transcript
        extraction_id: ID of medical extraction to link to
        consultation_type_id: Consultation type UUID
        delay_seconds: Delay before starting (default 20s)
    """
    # Check if emotion analysis enabled for this type
    consultation_type = get_consultation_type(consultation_type_id)
    
    if not consultation_type.get('enable_emotion_analysis'):
        logger.info(f"Emotion analysis disabled for {consultation_type['type_code']}")
        return
    
    # Update status: started
    update_extraction_emotion_status(
        extraction_id,
        started=True
    )
    
    # Schedule background task with delay
    asyncio.create_task(
        _run_delayed_emotion_extraction(
            transcript,
            extraction_id,
            delay_seconds
        )
    )
    
    logger.info(f"Emotion extraction scheduled for extraction_id={extraction_id} (delay={delay_seconds}s)")


async def _run_delayed_emotion_extraction(
    transcript: str,
    extraction_id: uuid.UUID,
    delay_seconds: int
):
    """Internal: Run emotion extraction after delay."""
    try:
        # Wait for delay
        await asyncio.sleep(delay_seconds)
        
        # Run extraction
        logger.info(f"Starting emotion extraction for extraction_id={extraction_id}")
        await extract_emotion_analysis(transcript, extraction_id)
        logger.info(f"Emotion extraction completed for extraction_id={extraction_id}")
        
    except Exception as e:
        logger.error(f"Emotion extraction failed for extraction_id={extraction_id}: {e}")
```

---

### 5. Backend - Router (`backend/routers/summary.py`)

#### Modify `POST /api/v1/summary/extract` endpoint

**Add after medical extraction completes:**

```python
@router.post("/extract")
async def extract_medical_summary(request: ExtractionRequest):
    # ... existing medical extraction logic ...
    
    # Save extraction to database (get extraction_id)
    extraction_id = save_medical_extraction(extracted_data)
    
    # Schedule emotion extraction (fire-and-forget)
    if consultation_type_id:
        asyncio.create_task(
            schedule_emotion_extraction(
                transcript=request.transcript,
                extraction_id=extraction_id,
                consultation_type_id=consultation_type_id,
                delay_seconds=20
            )
        )
    
    # Return medical results immediately (don't wait for emotion)
    return {
        "extraction_id": str(extraction_id),
        "extracted_data": extracted_data,
        "metadata": {...},
        "emotion_analysis_scheduled": consultation_type.enable_emotion_analysis
    }
```

---

### 6. Backend - Supabase Service (`backend/services/supabase_service.py`)

#### Add helper functions

```python
def update_extraction_emotion_status(
    extraction_id: uuid.UUID,
    started: bool = False,
    completed: bool = False,
    failed: bool = False,
    error: Optional[str] = None
) -> Dict[str, Any]:
    """Update emotion extraction status flags."""
    update_data = {}
    
    if started:
        update_data['emotion_extraction_started'] = True
        update_data['emotion_extraction_started_at'] = datetime.utcnow()
    
    if completed:
        update_data['emotion_extraction_completed'] = True
        update_data['emotion_extraction_completed_at'] = datetime.utcnow()
    
    if failed:
        update_data['emotion_extraction_failed'] = True
        update_data['emotion_extraction_error'] = error
    
    supabase.table('medical_extractions')\
        .update(update_data)\
        .eq('id', str(extraction_id))\
        .execute()


def save_emotion_segments(
    extraction_id: uuid.UUID,
    emotion_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Save emotion segments to extraction_segments table."""
    segments = []
    
    for segment_code, segment_value in emotion_data.items():
        segments.append({
            'extraction_id': str(extraction_id),
            'segment_code': segment_code,
            'segment_value': segment_value,
            'segment_type': 'emotion'
        })
    
    result = supabase.table('extraction_segments')\
        .insert(segments)\
        .execute()
    
    return result.data
```

---

### 7. Frontend - No Changes Required! 🎉

**RecordTab.tsx**: No modifications needed
**VHRScreen.tsx**: No modifications needed

The frontend continues to work exactly as before:
1. Calls extraction endpoint
2. Receives medical results immediately
3. Emotion extraction happens in background (transparent to frontend)

**Optional Enhancement (Future):**
- Poll for emotion results: `GET /api/v1/extractions/{extraction_id}`
- Check `emotion_extraction_completed` flag
- Display emotion segments when available

---

### 8. Admin UI - Template Admin Screen

#### Add toggle in consultation type configuration

```tsx
// In ConsultationTypeConfigPanel or similar
<div className="emotion-analysis-toggle">
  <label>
    <input
      type="checkbox"
      checked={consultationType.enable_emotion_analysis}
      onChange={() => handleToggleEmotionAnalysis(consultationType.type_code)}
    />
    Enable Emotion Analysis (Background)
  </label>
  <p className="text-sm text-gray-400">
    Runs 20 seconds after extraction starts. Results saved automatically.
  </p>
</div>
```

#### Add API endpoint
```python
PUT /api/v1/summary/admin/consultation-types/{type_code}/emotion-toggle
Body: { "enabled": boolean }
```

---

## Implementation Steps

### Phase 1: Database (15 min)
1. Add 6 new columns to `medical_extractions` table
2. Add 1 column to `consultation_types` table  
3. Set defaults: OP/OP_CONCISE = ON, DISCHARGE/RESPIRATORY = OFF
4. Create 5 emotion segment definitions

### Phase 2: Backend Core (40 min)
5. Create `emotion_prompts.py` with system prompt + schemas
6. Create `background_tasks.py` with scheduling logic
7. Add `extract_emotion_analysis()` to `gemini_service.py`
8. Add `save_emotion_segments()` to `supabase_service.py`
9. Add `update_extraction_emotion_status()` to `supabase_service.py`

### Phase 3: Backend Integration (20 min)
10. Modify `summary.py` to schedule background task
11. Add consultation type check
12. Test background task execution
13. Verify 20-second delay works

### Phase 4: Admin UI (15 min)
14. Add emotion toggle to admin screen
15. Create toggle API endpoint
16. Test enable/disable per consultation type

### Phase 5: Testing (20 min)
17. Test OP with emotion ON - verify background execution
18. Test DISCHARGE with emotion OFF - verify no execution
19. Enable emotion for DISCHARGE - verify it works
20. Test error handling - verify flags set correctly
21. Check database - verify segments linked to extraction_id

---

## Files to Modify/Create

### New Files (2)
- `backend/services/emotion_prompts.py`
- `backend/services/background_tasks.py`

### Modified Files (4)
- `backend/services/gemini_service.py` (add `extract_emotion_analysis()`)
- `backend/routers/summary.py` (schedule background task)
- `backend/services/supabase_service.py` (add 2 helper functions)
- `app/components/TemplateAdminScreen.tsx` (add toggle UI)

### Database Changes
- `consultation_types`: +1 column (`enable_emotion_analysis`)
- `medical_extractions`: +6 columns (emotion status flags)
- `segment_definitions`: +5 rows (emotion segments)

---

## Expected Behavior

### Timeline for Single Extraction

```
T+0s:   User requests extraction
T+0s:   Medical extraction starts
T+2-8s: Medical extraction completes
T+2-8s: Results returned to user ✅
T+2-8s: Emotion extraction scheduled (20s delay)
T+20s:  Emotion extraction starts (background)
T+22-23s: Emotion extraction completes (background)
T+22-23s: Emotion segments saved to database ✅
T+22-23s: emotion_extraction_completed = true ✅
```

### User Experience
- ✅ No waiting for emotion results
- ✅ Medical extraction returns immediately
- ✅ Emotion analysis happens transparently
- ✅ Can retrieve emotion data later via API

---

## Error Handling

### If Emotion Extraction Fails
```sql
medical_extractions:
  emotion_extraction_started = true
  emotion_extraction_completed = false
  emotion_extraction_failed = true
  emotion_extraction_error = "Error message here"
```

### Retry Strategy
- ❌ No automatic retry (keep it simple)
- ✅ Admin can manually re-trigger via API (future enhancement)
- ✅ Logs available for debugging

---

## Performance Impact

### User-Facing Performance
- ✅ **ZERO IMPACT** - Medical extraction returns immediately
- ✅ No blocking on emotion analysis

### Background Performance
- ⏱️ Emotion extraction: ~2-3 seconds (Flash model)
- 💾 Database writes: ~100ms (5 segments)
- 💰 Cost per extraction: ~$0.001 (Flash model)

### Server Resources
- 🔥 Background tasks run asynchronously
- 📊 Max concurrent emotion extractions: ~10-20 (configurable)
- 💻 CPU/Memory: Minimal impact (Flash model is lightweight)

---

## Success Criteria

✅ Admin can toggle emotion analysis per consultation type
✅ OP and OP_CONCISE default to ON
✅ DISCHARGE and RESPIRATORY have toggle (default OFF)
✅ Medical extraction returns immediately (no waiting)
✅ Emotion extraction starts 20 seconds after medical extraction
✅ Emotion segments saved with same extraction_id
✅ Status flags updated correctly (started, completed, failed)
✅ Error logging works correctly
✅ Frontend works without any changes
✅ Background tasks don't block other requests

---

## Rollout Strategy

### Week 1: Backend + Database (Safe Deploy)
1. Deploy database changes
2. Deploy backend code with emotion analysis
3. Keep all toggles OFF initially
4. Monitor background task execution

### Week 2: Enable for Testing
5. Enable emotion for OP on staging
6. Test with 10-20 real consultations
7. Verify data quality
8. Check error rates

### Week 3: Production Rollout
9. Enable emotion for OP in production
10. Monitor performance and errors
11. Collect feedback
12. Enable for OP_CONCISE if successful

### Future: Expand Coverage
- Optionally enable for DISCHARGE
- Optionally enable for RESPIRATORY
- Add custom emotion categories per specialty

---

*This file is automatically updated by Claude Code hooks when plans are created.*

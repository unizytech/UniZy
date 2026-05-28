# NEO Template Flow: VHRScreen → Database Storage

Complete trace for **NEO_DAILY** and **NEO_PROFORMA** consultation types from frontend to database.

---

## Overview

When a doctor selects a NEO template (NEONATAL_DAILY or NEONATAL_PROFORMA) in VHRScreen, the system follows a specialized extraction path that bypasses the normal segment-based configuration and uses hardcoded prompts directly.

---

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. FRONTEND: VHRScreen.tsx                                              │
│    User selects NEO template and records audio                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. API CALL: POST /api/v1/option1/recording/start                      │
│    recording_session.py:start_recording()                               │
│    • Validates template belongs to doctor's active templates            │
│    • Creates recording_sessions record in DB                            │
│    • Returns correlation_id                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. FRONTEND: Upload chunks                                              │
│    POST /api/v1/option1/recording/chunk (multiple times)               │
│    • Last chunk marked with is_last=true                                │
│    • Backend saves to audio_chunks table                                │
│    • Returns submission_id on final chunk                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. BACKGROUND PROCESSING: RecordingProcessor                            │
│    recording_processor.py:process()                                     │
│    • Stitches audio chunks → full audio file                            │
│    • Transcribes audio using Gemini (gemini-2.5-flash/pro)             │
│    • Saves full audio to recording_sessions.full_audio_data             │
│    • Deletes individual chunks from audio_chunks                        │
│    • Streams progress via SSE to frontend                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. EXTRACTION SERVICE: Template Lookup                                  │
│    extraction_service.py:perform_template_extraction()                  │
│    • Loads recording_sessions record                                    │
│    • Looks up doctor's activated template by template_name              │
│    • Gets consultation_type_id from template                            │
│    • Updates recording_sessions.consultation_type_id                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. GEMINI SERVICE: Dynamic Extraction                                   │
│    gemini_service.py:extract_summary_dynamic()                          │
│    • Calls segment_registry.generate_extraction_artifacts()             │
│    • Consultation type code determines prompt selection                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. SEGMENT REGISTRY: Prompt Generation (NEO SPECIAL PATH)               │
│    segment_registry.py:generate_extraction_artifacts()                  │
│                                                                          │
│    ┌────────────────────────────────────────────────────────┐           │
│    │ IF consultation_type_code == "NEONATAL_DAILY":         │           │
│    │   ✓ Use NEO_DAILY_PROMPT_SYSTEM                        │           │
│    │   ✓ Use NEO_DAILY_PROMPT_USER.format(transcript)       │           │
│    │   ✓ Use NEO_DAILY_PARAMETERS_SCHEMA                    │           │
│    │   ✓ Skip segment configuration (segments = [])         │           │
│    │   ✓ Return hardcoded artifacts                         │           │
│    └────────────────────────────────────────────────────────┘           │
│                                                                          │
│    ┌────────────────────────────────────────────────────────┐           │
│    │ IF consultation_type_code == "NEONATAL_PROFORMA":      │           │
│    │   ✓ Use NEO_PROFORMA_PROMPT_SYSTEM                     │           │
│    │   ✓ Use NEO_PROFORMA_PROMPT_USER.format(transcript)    │           │
│    │   ✓ Use NEO_PROFORMA_PARAMETERS_SCHEMA                 │           │
│    │   ✓ Skip segment configuration (segments = [])         │           │
│    │   ✓ Return hardcoded artifacts                         │           │
│    └────────────────────────────────────────────────────────┘           │
│                                                                          │
│    OTHERWISE: Load segments from database (OP, DISCHARGE, etc.)         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 8. NEONATAL PROMPTS: Specialized Extraction                             │
│    neonatal_prompts.py (imported by segment_registry)                   │
│                                                                          │
│    NEO_DAILY (Respiratory Parameters):                                  │
│    • 20 respiratory fields (invasiveVentilation, ventilationType, etc.) │
│    • Schema: NEO_DAILY_PARAMETERS_SCHEMA                                │
│    • Focus: Daily respiratory monitoring                                │
│                                                                          │
│    NEO_PROFORMA (Birth/Admission):                                      │
│    • 90+ fields (APGAR, resuscitation, maternal history, etc.)          │
│    • Schema: NEO_PROFORMA_PARAMETERS_SCHEMA                             │
│    • Focus: Comprehensive neonatal admission documentation              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 9. GEMINI API CALL: Structured Extraction                               │
│    gemini_service.py (continued)                                        │
│    • Calls: client.aio.models.generate_content()                        │
│    • Config: GenerateContentConfig with:                                │
│      - system_instruction = NEO_*_PROMPT_SYSTEM                         │
│      - response_schema = NEO_*_PARAMETERS_SCHEMA                        │
│      - response_mime_type = "application/json"                          │
│      - temperature = 0.2                                                │
│    • Gemini returns structured JSON matching schema                     │
│    • Filters out N/A values                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 10. DATABASE STORAGE: Save Extraction                                   │
│     extraction_service.py (continued)                                   │
│     • Calls supabase_service.save_medical_extraction()                  │
│     • Creates extraction_segments records for each field                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 11. SUPABASE SERVICE: Database Writes                                   │
│     supabase_service.py:save_medical_extraction()                       │
│                                                                          │
│     TABLE: medical_extractions                                          │
│     ┌───────────────────────────────────────────────────────┐           │
│     │ id (UUID)                                             │           │
│     │ session_id (FK → recording_sessions)                  │           │
│     │ consultation_type_id (FK → consultation_types)        │           │
│     │ doctor_id (FK → doctors)                              │           │
│     │ patient_id (FK → patients)                            │           │
│     │ extraction_mode ('core'|'additional'|'full')          │           │
│     │ model_used ('gemini-2.5-pro')                         │           │
│     │ segment_count (integer)                               │           │
│     │ original_extraction_json (JSONB) ← AI result          │           │
│     │ edited_extraction_json (JSONB) ← Doctor edits         │           │
│     │ edit_count (integer)                                  │           │
│     │ created_at, updated_at                                │           │
│     └───────────────────────────────────────────────────────┘           │
│                                                                          │
│     TABLE: extraction_segments                                          │
│     ┌───────────────────────────────────────────────────────┐           │
│     │ id (UUID)                                             │           │
│     │ extraction_id (FK → medical_extractions)              │           │
│     │ segment_code (text) ← e.g., "uhid", "birthWeight"    │           │
│     │ segment_value (JSONB) ← Extracted value               │           │
│     │ version_type ('original'|'edited')                    │           │
│     │ brevity_level, terminology_style, display_format      │           │
│     │ created_at, updated_at                                │           │
│     └───────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 12. OPTIONAL: Emotion Analysis (Fire-and-Forget)                        │
│     • Checks consultation_type.enable_emotion_analysis                  │
│     • Schedules background task (20s delay)                             │
│     • Currently: NEO templates have emotion disabled by default         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 13. FRONTEND: Display Results                                           │
│     • SSE stream sends 'complete' event with extraction data            │
│     • VHRScreen updates state with extraction results                   │
│     • ExtractionDisplay component renders segments                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Key Files by Layer

### Frontend (Next.js/TypeScript)
```
app/components/VHRScreen.tsx
  ├─ Handles doctor/template selection
  ├─ Manages recording state
  ├─ Calls recording API endpoints
  └─ Displays extraction results

app/services/recordingService.ts
  └─ RecordingManager class (chunk upload logic)

lib/summaryApi.ts
  └─ API client functions for extraction
```

### Backend - API Routes (Python FastAPI)
```
backend/routers/recording_session.py
  ├─ POST /start → start_recording()
  ├─ POST /chunk → upload_chunk()
  └─ GET /processing/{submission_id}/stream → stream_processing()
```

### Backend - Core Services
```
backend/services/recording_processor.py
  └─ RecordingProcessor.process() → Background SSE streaming

backend/services/extraction_service.py
  └─ perform_template_extraction() → Template lookup & extraction orchestration

backend/services/gemini_service.py
  └─ extract_summary_dynamic() → AI extraction with Gemini

backend/services/segment_registry.py
  ├─ generate_extraction_artifacts() → Prompt generation
  └─ SPECIAL PATH: Detects NEO_DAILY/NEO_PROFORMA codes

backend/services/neonatal_prompts.py
  ├─ NEO_DAILY_PROMPT_SYSTEM/USER
  ├─ NEO_PROFORMA_PROMPT_SYSTEM/USER
  ├─ NEO_DAILY_PARAMETERS_SCHEMA
  └─ NEO_PROFORMA_PARAMETERS_SCHEMA

backend/services/supabase_service.py
  └─ save_medical_extraction() → Database writes
```

---

## NEO Template Special Characteristics

### 1. **Hardcoded Prompts (Not Database-Driven)**
Unlike OP, DISCHARGE, and RESPIRATORY consultation types which load segment configuration from the database, NEO templates use hardcoded prompts:

**Why?**
- Regulatory compliance: Neonatal documentation must follow strict medical standards
- Complex nested structures: APGAR scores, resuscitation details, maternal history
- Stability: These prompts should not be modified by users
- Validation: Medical records require fixed schema validation

### 2. **Direct Schema Mapping**
NEO templates return complete nested JSON structures directly from Gemini:

**NEO_DAILY Example:**
```json
{
  "uhid": "711890",
  "invasiveVentilation": "Yes",
  "ventilationType": "NonInvasiveVentilation",
  "respiratoryRate": 45,
  "spo2": 95,
  "respiratoryIndication": [15, 18]  // Array of condition IDs
}
```

**NEO_PROFORMA Example:**
```json
{
  "uhid": "711890",
  "birthWeight": "2400",
  "gestationWeeks": "34",
  "gestationDays": "1",
  "apgar": {
    "minute1": {
      "color": 1,
      "heartRate": 2,
      "reflex": 1,
      "tone": 2,
      "respiration": 2,
      "total": 8
    },
    "minute5": { ... }
  },
  "medicalProblem": [
    {"problem": 15, "medication": "Surfactant"},
    {"problem": 18, "medication": "Ampicillin"}
  ]
}
```

### 3. **Segment Storage**
Even though NEO prompts are hardcoded, the extraction results are still stored as individual segments in `extraction_segments` table:

```python
# extraction_service.py lines 180-186
if isinstance(insights, dict):
    for segment_code, segment_value in insights.items():
        if segment_value not in [None, "", "N/A", "Not mentioned", "None"]:
            segments.append({
                "segment_code": segment_code,
                "segment_value": segment_value
            })
```

Each field becomes a separate segment record:
- `segment_code`: "uhid", "birthWeight", "apgar", etc.
- `segment_value`: The extracted value (stored as JSONB)
- `version_type`: "original" (AI-generated, immutable)

---

## Code References

### Detection Logic
**File:** `backend/services/segment_registry.py`
**Lines:** 860-883

```python
def generate_extraction_artifacts(...):
    consultation_type_code = get_consultation_type_code_by_id(consultation_type_id)

    # SPECIAL PATH FOR NEO_DAILY
    if(consultation_type_code == "NEONATAL_DAILY"):
        return {
            "system_prompt": NEO_DAILY_PROMPT_SYSTEM,
            "user_prompt": NEO_DAILY_PROMPT_USER.format(transcript=transcript),
            "schema": NEO_DAILY_PARAMETERS_SCHEMA,
            "segments": [],  # ← No database segments
            "validation": {"is_valid": True, "error_message": None, "warnings": []},
            "segment_count": 1,
            "mode": mode,
            "consultation_type_id": str(consultation_type_id),
            "consultation_type_code": consultation_type_code
        }

    # SPECIAL PATH FOR NEO_PROFORMA
    if(consultation_type_code == "NEONATAL_PROFORMA"):
        return {
            "system_prompt": NEO_PROFORMA_PROMPT_SYSTEM,
            "user_prompt": NEO_PROFORMA_PROMPT_USER.format(transcript=transcript),
            "schema": NEO_PROFORMA_PARAMETERS_SCHEMA,
            "segments": [],  # ← No database segments
            ...
        }

    # OTHERWISE: Load segments from database (normal path)
    segments = load_segments_for_mode(...)
```

### Template Lookup
**File:** `backend/services/extraction_service.py`
**Lines:** 104-145

```python
# Step 4: Look up activated template
active_template = get_active_template_by_name(doctor_uuid, template_name)

# Step 5: Get consultation_type_id from template
consultation_type_id = uuid.UUID(active_template['consultation_type_id'])
consultation_type_code = active_template.get('template_code')

# Step 6: Update session.consultation_type_id
supabase.table('recording_sessions')\
    .update({'consultation_type_id': str(consultation_type_id)})\
    .eq('id', str(session_id))\
    .execute()
```

### Gemini API Call
**File:** `backend/services/gemini_service.py`
**Lines:** 552-583

```python
# Call Gemini with dynamic configuration
response = await client.aio.models.generate_content(
    model=model,
    contents=user_prompt,
    config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.2,
        response_mime_type="application/json",
        response_schema=schema  # ← NEO_DAILY/PROFORMA_PARAMETERS_SCHEMA
    )
)

extracted_data = json.loads(response.text)
filtered_data = filter_na_values(extracted_data)

return {
    "data": filtered_data,
    "metadata": {
        "mode": mode,
        "segment_count": segment_count,
        "model": model,
        "doctor_id": doctor_id,
        "validation": artifacts["validation"]
    }
}
```

### Database Storage
**File:** `backend/services/supabase_service.py`
**Lines:** 3237-3285

```python
def save_medical_extraction(...):
    # Create medical_extraction record
    extraction_data = {
        "session_id": str(session_id),
        "consultation_type_id": str(consultation_type_id),
        "doctor_id": str(doctor_id),
        "patient_id": str(patient_id) if patient_id else None,
        "extraction_mode": extraction_mode,
        "model_used": model_used,
        "segment_count": len(segments),
        "original_extraction_json": full_extraction,  # AI-generated (immutable)
        "edited_extraction_json": None,  # No edits yet
        "edit_count": 0,
    }

    extraction_response = supabase.table("medical_extractions").insert(extraction_data).execute()
    extraction_id = uuid.UUID(extraction_response.data[0]["id"])

    # Create extraction_segments records (one per field)
    segment_records = []
    for segment in segments:
        segment_records.append({
            "extraction_id": str(extraction_id),
            "segment_code": segment.get("segment_code"),
            "segment_value": segment.get("segment_value"),
            "version_type": "original",  # Mark as AI-generated
            ...
        })

    supabase.table("extraction_segments").insert(segment_records).execute()
    return extraction_id
```

---

## Database Schema

### Tables Modified/Queried

1. **`recording_sessions`**
   - Created by: `start_recording()`
   - Updated with: `consultation_type_id` (after template lookup)
   - Stores: `full_audio_data` (base64), `transcription_text`, `template_name`

2. **`audio_chunks`**
   - Created by: `upload_chunk()`
   - Deleted after: Audio stitching complete
   - Temporary storage for chunk uploads

3. **`processing_jobs`**
   - Created by: `upload_chunk()` (on final chunk)
   - Updated by: RecordingProcessor (progress updates)
   - Tracks: Processing status and results

4. **`medical_extractions`**
   - Created by: `save_medical_extraction()`
   - Stores: Both original AI extraction and doctor edits
   - Key fields:
     - `original_extraction_json`: Immutable AI result
     - `edited_extraction_json`: Doctor corrections (nullable)
     - `edit_count`: Number of edits made

5. **`extraction_segments`**
   - Created by: `save_medical_extraction()`
   - One record per extracted field
   - Example for NEO_DAILY:
     - ("uhid", "711890", "original")
     - ("invasiveVentilation", "Yes", "original")
     - ("respiratoryRate", 45, "original")

6. **`doctor_active_templates`**
   - Queried by: `start_recording()` to validate template
   - Links doctors to their activated templates

7. **`templates`**
   - Queried via: `doctor_active_templates.template_id`
   - Contains: `consultation_type_id`, `template_code`

8. **`consultation_types`**
   - Queried by: `get_consultation_type_code_by_id()`
   - Returns: `type_code` (e.g., "NEONATAL_DAILY")

---

## Differences: NEO vs OP/DISCHARGE Templates

| Aspect | NEO Templates | OP/DISCHARGE Templates |
|--------|---------------|------------------------|
| **Prompt Source** | Hardcoded in `neonatal_prompts.py` | Database-driven (`segment_definitions` table) |
| **Segment Configuration** | Not configurable | Per-doctor, per-template customization |
| **Brevity Control** | Fixed | User-adjustable (concise/balanced/detailed) |
| **Terminology Style** | Fixed | User-adjustable (medical/simple/as-spoken) |
| **Segment Categorization** | N/A | CORE/ADDITIONAL/EXCLUDED |
| **Schema Complexity** | Highly nested (90+ fields) | Flat segments (14-26 fields) |
| **Validation** | Strict medical standards | Flexible |
| **Progressive Loading** | No (single extraction) | Yes (CORE first, then ADDITIONAL) |

---

## Error Handling

### Common Issues

1. **Template Not Found**
   - Error: "Template '{name}' not found in doctor's active templates"
   - Fix: Ensure template is activated in Doctor Config screen

2. **KeyError in Prompt Formatting** ✅ FIXED
   - Error: `KeyError: '\n\t"uhid"'`
   - Cause: Unescaped curly braces in JSON template
   - Fix: Doubled all braces in `NEO_PROFORMA_PROMPT_USER` (e.g., `{` → `{{`)

3. **Schema Validation Failure**
   - Error: "Failed to parse Gemini response as JSON"
   - Cause: Gemini returned invalid JSON
   - Debug: Check `gemini_service.py` logs for schema details

4. **Timeout During Chunk Upload**
   - Error: "The read operation timed out"
   - Cause: Large audio chunk or slow network
   - Solution: Increase timeout or reduce chunk size

---

## Testing NEO Templates

### Manual Test Steps

1. **Start backend:**
   ```bash
   cd backend && uvicorn main:app --reload
   ```

2. **Start frontend:**
   ```bash
   npm run dev
   ```

3. **Navigate to VHR Screen:**
   - Select doctor with NEO template activated
   - Choose "SKS_Neonatal Daily Notes" or "SKS_Neonatal Proforma"
   - Select patient ID
   - Choose processing mode (Default recommended)

4. **Record or upload audio:**
   - Record: Click "Start Recording" → speak → "Stop Recording"
   - Upload: Drag/drop audio file

5. **Monitor progress:**
   - Watch SSE events in browser Network tab
   - Check backend logs for extraction progress

6. **Verify database:**
   ```sql
   -- Check extraction was saved
   SELECT * FROM medical_extractions
   WHERE session_id = '<session_id>'
   ORDER BY created_at DESC LIMIT 1;

   -- Check segments were saved
   SELECT segment_code, segment_value, version_type
   FROM extraction_segments
   WHERE extraction_id = '<extraction_id>';
   ```

---

## Conclusion

NEO templates follow a **specialized path** that:
1. ✅ Uses hardcoded prompts for regulatory compliance
2. ✅ Bypasses database segment configuration
3. ✅ Returns complex nested JSON structures
4. ✅ Still stores results in standard `medical_extractions` + `extraction_segments` tables
5. ✅ Maintains edit tracking (original vs edited versions)

This design ensures **medical accuracy** and **regulatory compliance** while maintaining compatibility with the existing database schema and UI components.

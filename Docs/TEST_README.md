# Backend Refactoring Endpoint Tests

Comprehensive test scripts for the Template & Processing Mode refactoring.

## Overview

These test scripts verify that all backend endpoints modified during the refactoring are working correctly:

1. **NEW** Processing modes endpoint (`GET /api/v1/summary/processing-modes`)
2. Extraction API with `template_name` and `processing_mode` parameters
3. Activated templates endpoint with `template_name_override`
4. Progressive extraction (CORE + ADDITIONAL)
5. Recording API with new template parameters
6. Default template fallback logic

## Prerequisites

Before running tests:

### 1. Database Setup
```bash
# Run migrations in Supabase SQL Editor
# - backend/supabase/migrations/015_default_template_fallback.sql
# - backend/supabase/migrations/016_recording_sessions_template_fields.sql
```

### 2. Seed Processing Modes
Ensure `processing_modes` table has data. Example SQL:

```sql
INSERT INTO processing_modes (mode_code, mode_name, transcription_model, extraction_model, transcription_api, estimated_time_seconds, is_active, display_order, description)
VALUES
  ('ultra_fast', 'Ultra Fast', 'gemini-2.5-flash', 'gemini-2.5-flash', 'gemini', 15, true, 1, 'Fastest extraction with Flash models'),
  ('fast', 'Fast', 'gemini-2.5-flash', 'gemini-2.5-flash', 'gemini', 25, true, 2, 'Fast processing with Flash models'),
  ('default', 'Default', 'gemini-2.5-flash', 'gemini-2.5-pro', 'gemini', 35, true, 3, 'Balanced speed and quality'),
  ('thorough', 'Thorough', 'gemini-2.5-pro', 'gemini-2.5-pro', 'gemini', 50, true, 4, 'Maximum quality with Pro models'),
  ('ultra', 'Ultra', 'gemini-2.5-pro', 'gemini-2.5-pro', 'gemini', 45, false, 5, 'Native audio + Pro (Coming soon)')
ON CONFLICT (mode_code) DO NOTHING;
```

### 3. Create Test Doctor & Activate Templates
```sql
-- Get or create a test doctor
SELECT id FROM doctors WHERE email = 'test@example.com';

-- Activate a template for testing
INSERT INTO doctor_active_templates (doctor_id, template_id, is_default, template_name_override)
SELECT
  '{YOUR_DOCTOR_UUID}',
  t.id,
  true,
  'Default Template'
FROM templates t
WHERE t.template_code = 'OP_DEFAULT'
LIMIT 1;
```

### 4. Start Backend
```bash
cd backend
uvicorn main:app --reload --port 8000
```

---

## Test Script 1: Python Test Suite (Recommended)

**File:** `test_refactoring_endpoints.py`

**Features:**
- Comprehensive test coverage
- Colored terminal output
- Detailed test results
- Sample data validation
- Automatic cleanup

### Setup

1. **Update configuration in the script:**
   ```python
   # Line 20: Update with your test doctor UUID
   TEST_DOCTOR_ID = "00000000-0000-0000-0000-000000000001"
   ```

2. **Install dependencies (if not already):**
   ```bash
   pip install requests
   ```

### Run Tests

```bash
cd backend
python3 test_refactoring_endpoints.py
```

### Test Coverage

1. ✅ **Processing Modes Endpoint** (NEW)
   - Verifies GET /api/v1/summary/processing-modes
   - Lists all available modes
   - Shows model configurations

2. ✅ **Consultation Types**
   - Verifies GET /api/v1/summary/consultation-types
   - Lists OP, DISCHARGE, RESPIRATORY types

3. ✅ **Activated Templates**
   - Tests GET /api/v1/doctors/{doctor_id}/active-templates
   - Shows template_name_override
   - Validates template structure

4. ✅ **Extraction with Template & Mode**
   - Tests POST /api/v1/summary/extract
   - Uses template_name and processing_mode
   - Validates extracted segments
   - Shows sample extracted fields

5. ✅ **Progressive Extraction**
   - Tests CORE extraction first
   - Tests ADDITIONAL extraction second
   - Measures timing for both
   - Shows total segments and time

6. ✅ **Recording API Parameters**
   - Tests POST /api/v1/option1/recording/start
   - Validates new parameters accepted
   - Tests session creation and cleanup

7. ✅ **Default Template Fallback**
   - Tests extraction without template_name
   - Verifies automatic fallback to default

---

## Test Script 2: Curl-based Quick Tests

**File:** `test_endpoints_curl.sh`

**Features:**
- Fast, lightweight testing
- No Python dependencies
- Easy to modify
- Uses `jq` for JSON parsing

### Setup

1. **Install jq (if not already):**
   ```bash
   # macOS
   brew install jq

   # Linux
   sudo apt-get install jq
   ```

2. **Update configuration in script:**
   ```bash
   # Lines 13-14
   TEST_DOCTOR_ID="00000000-0000-0000-0000-000000000001"
   TEMPLATE_NAME="Default Template"
   ```

### Run Tests

```bash
cd backend
./test_endpoints_curl.sh
```

---

## Expected Results

### 1. Processing Modes Endpoint
```json
{
  "success": true,
  "processing_modes": [
    {
      "mode_code": "default",
      "mode_name": "Default",
      "transcription_model": "gemini-2.5-flash",
      "extraction_model": "gemini-2.5-pro",
      "estimated_time_seconds": 35,
      "is_active": true
    }
  ],
  "count": 5
}
```

### 2. Activated Templates
```json
{
  "success": true,
  "templates": [
    {
      "id": "uuid",
      "template_name": "OP Summary - Default",
      "template_name_override": "Default Template",
      "template_code": "OP_DEFAULT",
      "consultation_type_name": "Outpatient Consultation"
    }
  ],
  "count": 1
}
```

### 3. Extraction Result
```json
{
  "success": true,
  "data": {
    "diagnosis": "Migraine headaches",
    "chief_complaints": "Severe headaches for one week",
    "prescription": "Sumatriptan for migraine relief"
  },
  "metadata": {
    "mode": "core",
    "segment_count": 8,
    "model": "gemini-2.5-pro",
    "template_name": "Default Template",
    "processing_mode": "default"
  }
}
```

---

## Troubleshooting

### Error: "Doctor not found"
**Solution:** Update `TEST_DOCTOR_ID` with a valid UUID from your `doctors` table.

```sql
SELECT id, email, name FROM doctors LIMIT 5;
```

### Error: "No activated templates"
**Solution:** Activate a template for the test doctor.

```sql
-- Check available templates
SELECT template_code, template_name FROM templates WHERE consultation_type_code = 'OP';

-- Activate a template
INSERT INTO doctor_active_templates (doctor_id, template_id, template_name_override)
SELECT '{doctor_uuid}', id, 'Test Template'
FROM templates
WHERE template_code = 'OP_DEFAULT';
```

### Error: "No processing modes available"
**Solution:** Seed the `processing_modes` table (see Prerequisites section).

### Error: "Failed to connect to backend"
**Solution:** Ensure backend is running on port 8000.

```bash
# Start backend
cd backend
uvicorn main:app --reload --port 8000

# Check if running
curl http://localhost:8000/docs
```

### Error: "Extraction failed"
**Solution:** Check backend logs for detailed error messages.

```bash
# View backend logs
# Look for [ERROR] or stack traces
```

---

## Next Steps After Tests Pass

1. **Frontend Testing**
   - Test MedicalSummaryTab with transcript input
   - Test VHRScreen with recording + file upload
   - Test RecordTab with live recording

2. **Integration Testing**
   - End-to-end flow: recording → transcription → extraction
   - Test all processing modes (fast, default, thorough)
   - Test progressive extraction (CORE + ADDITIONAL)

3. **User Acceptance Testing**
   - Create test doctors and templates
   - Test complete workflow
   - Verify results accuracy

---

## Test Results Template

Copy this to track your test results:

```
## Test Results - [DATE]

### Backend Tests

- [ ] Processing Modes Endpoint
  - Status: [ PASS / FAIL ]
  - Notes: _________________

- [ ] Consultation Types
  - Status: [ PASS / FAIL ]
  - Notes: _________________

- [ ] Activated Templates
  - Status: [ PASS / FAIL ]
  - Notes: _________________

- [ ] Extraction with Template & Mode
  - Status: [ PASS / FAIL ]
  - Notes: _________________

- [ ] Progressive Extraction
  - Status: [ PASS / FAIL ]
  - CORE time: ___s, ADDITIONAL time: ___s
  - Notes: _________________

- [ ] Recording API Parameters
  - Status: [ PASS / FAIL ]
  - Notes: _________________

- [ ] Default Template Fallback
  - Status: [ PASS / FAIL ]
  - Notes: _________________

### Frontend Tests (Manual)

- [ ] MedicalSummaryTab
  - Status: [ PASS / FAIL ]
  - Notes: _________________

- [ ] VHRScreen
  - Status: [ PASS / FAIL ]
  - Notes: _________________

- [ ] RecordTab
  - Status: [ PASS / FAIL ]
  - Notes: _________________

### Issues Found
1. _________________
2. _________________
```

---

## Support

If tests fail:
1. Check Prerequisites section
2. Review Troubleshooting section
3. Check backend logs for errors
4. Verify database migrations are applied
5. Verify processing_modes table is seeded

For implementation details, see:
- `REFACTORING_PLAN_TEMPLATES.md` - Implementation plan
- `backend/routers/summary.py:366` - Processing modes endpoint
- `backend/routers/recording_session.py` - Recording API updates
- `app/components/RecordTab.tsx` - Frontend updates

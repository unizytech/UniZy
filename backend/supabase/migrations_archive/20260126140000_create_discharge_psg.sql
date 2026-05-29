-- Migration: Create DISCHARGE_PSG consultation type for PSG hospital discharge summaries
-- This creates 8 new segment definitions and links 13 total segments (8 new + 5 reused from OP_PSG_NEW)
-- NOTE: Made idempotent with ON CONFLICT DO NOTHING for safe re-runs

-- Step 1: Create the DISCHARGE_PSG consultation type
INSERT INTO consultation_types (type_code, type_name, description, display_order, is_active)
VALUES (
    'DISCHARGE_PSG',
    'PSG Discharge Summary',
    'PSG hospital discharge summary with morbidity assessment',
    14,
    true
) ON CONFLICT (type_code) DO NOTHING;

-- Step 2: Create 8 new segment definitions

-- 2.1 PSG_CONSULTANT - Simple free text for consultant name
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    display_order,
    segment_type,
    description,
    is_active
) VALUES (
    'PSG_CONSULTANT',
    'PSG Consultant',
    '**PSG_CONSULTANT:**
Extract the consultant/attending physician information.

**Required Fields:**
- consultant: Name of the consultant/attending physician

***Example:***
```json
{ "consultant": "Dr. Ramesh Kumar" }
```',
    '{"type": "object", "properties": {"consultant": {"type": "string", "description": "Name of consultant/attending physician"}}, "required": ["consultant"]}',
    'core',
    1021,
    'system',
    'Consultant/attending physician for PSG discharge',
    true
) ON CONFLICT (segment_code, segment_type, COALESCE(doctor_id, '00000000-0000-0000-0000-000000000000'::uuid)) DO NOTHING;

-- 2.2 PSG_ADMISSION_DETAILS - Free text admission details
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    display_order,
    segment_type,
    description,
    is_active
) VALUES (
    'PSG_ADMISSION_DETAILS',
    'PSG Admission Details',
    '**PSG_ADMISSION_DETAILS:**
Extract admission details including date, reason, and circumstances.

**Required Fields:**
- admission_details: Free text admission details

***Example:***
```json
{ "admission_details": "Admitted on 20-01-2026 for elective hernia repair surgery" }
```',
    '{"type": "object", "properties": {"admission_details": {"type": "string", "description": "Admission details"}}, "required": ["admission_details"]}',
    'core',
    1022,
    'system',
    'Admission details for PSG discharge',
    true
) ON CONFLICT (segment_code, segment_type, COALESCE(doctor_id, '00000000-0000-0000-0000-000000000000'::uuid)) DO NOTHING;

-- 2.3 PSG_HOSPITAL_INVESTIGATION - Free text investigations during stay
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    display_order,
    segment_type,
    description,
    is_active
) VALUES (
    'PSG_HOSPITAL_INVESTIGATION',
    'PSG In-Hospital Investigation',
    '**PSG_HOSPITAL_INVESTIGATION:**
Extract investigations performed during hospital stay.

**Required Fields:**
- in_hospital_investigation: Free text summary of investigations done

***Example:***
```json
{ "in_hospital_investigation": "CBC - normal, RBS - 120 mg/dL, ECG - normal sinus rhythm, Chest X-ray - clear lung fields" }
```',
    '{"type": "object", "properties": {"in_hospital_investigation": {"type": "string", "description": "Investigations during hospital stay"}}, "required": ["in_hospital_investigation"]}',
    'core',
    1023,
    'system',
    'In-hospital investigations for PSG discharge',
    true
) ON CONFLICT (segment_code, segment_type, COALESCE(doctor_id, '00000000-0000-0000-0000-000000000000'::uuid)) DO NOTHING;

-- 2.4 PSG_COURSE_IN_HOSPITAL - Free text hospital course
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    display_order,
    segment_type,
    description,
    is_active
) VALUES (
    'PSG_COURSE_IN_HOSPITAL',
    'PSG Course in Hospital',
    '**PSG_COURSE_IN_HOSPITAL:**
Extract the course of hospital stay including treatment progress.

**Required Fields:**
- course_in_hospital: Narrative of hospital stay

***Example:***
```json
{ "course_in_hospital": "Patient underwent surgery on POD 0, post-op recovery uneventful. Started oral feeds on POD 1. Mobilized on POD 2. Wound inspection satisfactory." }
```',
    '{"type": "object", "properties": {"course_in_hospital": {"type": "string", "description": "Course of hospital stay"}}, "required": ["course_in_hospital"]}',
    'core',
    1024,
    'system',
    'Course in hospital for PSG discharge',
    true
) ON CONFLICT (segment_code, segment_type, COALESCE(doctor_id, '00000000-0000-0000-0000-000000000000'::uuid)) DO NOTHING;

-- 2.5 PSG_MORBIDITY_ASSESSMENT - Complex morbidity/complication assessment
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    display_order,
    segment_type,
    description,
    is_active
) VALUES (
    'PSG_MORBIDITY_ASSESSMENT',
    'PSG Morbidity Assessment',
    '**PSG_MORBIDITY_ASSESSMENT:**
Extract morbidity/complication assessment during hospital stay.

**Required Fields:**
- complication_type: "Surgery Related" / "Non-Surgery Related" / "No"
- details: Complication details (if any)
- duration_exceeded: "Yes" / "No" - Was hospital stay longer than expected?
- icu_inscu_postop_days: Number of days in ICU/INSCU/Post-OP/CO
- ward_days: Number of days in ward
- reason_prolonged_stay: Reason if stay was prolonged

***Example:***
```json
{
  "complication_type": "No",
  "details": "",
  "duration_exceeded": "No",
  "icu_inscu_postop_days": "1",
  "ward_days": "3",
  "reason_prolonged_stay": ""
}
```

**Extraction Rules:**
- If no complications, set complication_type to "No"
- Calculate days from admission/discharge dates if mentioned',
    '{"type": "object", "properties": {"complication_type": {"type": "string", "description": "Surgery Related / Non-Surgery Related / No"}, "details": {"type": "string", "description": "Complication details"}, "duration_exceeded": {"type": "string", "description": "Yes / No"}, "icu_inscu_postop_days": {"type": "string", "description": "Days in ICU/INSCU/Post-OP/CO"}, "ward_days": {"type": "string", "description": "Days in ward"}, "reason_prolonged_stay": {"type": "string", "description": "Reason for prolonged stay"}}, "required": ["complication_type", "details", "duration_exceeded", "icu_inscu_postop_days", "ward_days", "reason_prolonged_stay"]}',
    'core',
    1025,
    'system',
    'Morbidity assessment for PSG discharge',
    true
) ON CONFLICT (segment_code, segment_type, COALESCE(doctor_id, '00000000-0000-0000-0000-000000000000'::uuid)) DO NOTHING;

-- 2.6 PSG_CONDITION_ON_DISCHARGE - Free text discharge condition
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    display_order,
    segment_type,
    description,
    is_active
) VALUES (
    'PSG_CONDITION_ON_DISCHARGE',
    'PSG Condition on Discharge',
    '**PSG_CONDITION_ON_DISCHARGE:**
Extract patient''s condition at the time of discharge.

**Required Fields:**
- condition_on_discharge: Description of patient''s condition at discharge

***Example:***
```json
{ "condition_on_discharge": "Patient is afebrile, wound healthy, ambulatory, and vitals stable. Discharged in satisfactory condition." }
```',
    '{"type": "object", "properties": {"condition_on_discharge": {"type": "string", "description": "Condition at discharge"}}, "required": ["condition_on_discharge"]}',
    'core',
    1026,
    'system',
    'Condition on discharge for PSG discharge',
    true
) ON CONFLICT (segment_code, segment_type, COALESCE(doctor_id, '00000000-0000-0000-0000-000000000000'::uuid)) DO NOTHING;

-- 2.7 PSG_HOSPITAL_MEDICATIONS - Free text in-hospital medications
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    display_order,
    segment_type,
    description,
    is_active
) VALUES (
    'PSG_HOSPITAL_MEDICATIONS',
    'PSG In-Hospital Medications',
    '**PSG_HOSPITAL_MEDICATIONS:**
Extract medications given during hospital stay.

**Required Fields:**
- in_hospital_medications: Summary of medications administered during stay

***Example:***
```json
{ "in_hospital_medications": "IV antibiotics (Ceftriaxone 1g BD x 3 days), Analgesics (Paracetamol 1g TDS), DVT prophylaxis (Enoxaparin 40mg OD)" }
```',
    '{"type": "object", "properties": {"in_hospital_medications": {"type": "string", "description": "Medications during hospital stay"}}, "required": ["in_hospital_medications"]}',
    'core',
    1027,
    'system',
    'In-hospital medications for PSG discharge',
    true
) ON CONFLICT (segment_code, segment_type, COALESCE(doctor_id, '00000000-0000-0000-0000-000000000000'::uuid)) DO NOTHING;

-- 2.8 PSG_INVESTIGATIONS_PROCEDURE - Separate segment for procedures/investigations
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    display_order,
    segment_type,
    description,
    is_active
) VALUES (
    'PSG_INVESTIGATIONS_PROCEDURE',
    'PSG Investigations & Procedure',
    '**PSG_INVESTIGATIONS_PROCEDURE:**
Extract any diagnostic or therapeutic procedures performed during the stay.

**Required Fields:**
- investigations_procedure: Details of procedures/investigations performed

***Example:***
```json
{ "investigations_procedure": "Diagnostic laparoscopy performed on 21-01-2026. Biopsy sent for HPE." }
```',
    '{"type": "object", "properties": {"investigations_procedure": {"type": "string", "description": "Procedures and investigations performed"}}, "required": ["investigations_procedure"]}',
    'core',
    1028,
    'system',
    'Investigations and procedures for PSG discharge',
    true
) ON CONFLICT (segment_code, segment_type, COALESCE(doctor_id, '00000000-0000-0000-0000-000000000000'::uuid)) DO NOTHING;

-- Step 3: Link segments to DISCHARGE_PSG consultation type
-- Using a DO block to get the IDs dynamically
-- Links are created only if they don't already exist

DO $$
DECLARE
    v_consultation_type_id UUID;
    v_psg_consultant_id UUID;
    v_psg_admission_details_id UUID;
    v_psg_hospital_investigation_id UUID;
    v_psg_course_in_hospital_id UUID;
    v_psg_morbidity_assessment_id UUID;
    v_psg_condition_on_discharge_id UUID;
    v_psg_hospital_medications_id UUID;
    v_psg_investigations_procedure_id UUID;
    v_diagnosis_id UUID;
    v_procedure_notes_id UUID;
    v_prescription_id UUID;
    v_consumables_id UUID;
    v_follow_up_id UUID;
BEGIN
    -- Get the consultation type ID
    SELECT id INTO v_consultation_type_id
    FROM consultation_types
    WHERE type_code = 'DISCHARGE_PSG';

    -- Skip if consultation type doesn't exist or already has segments
    IF v_consultation_type_id IS NULL THEN
        RAISE NOTICE 'DISCHARGE_PSG consultation type not found, skipping segment links';
        RETURN;
    END IF;

    -- Check if segments already linked
    IF EXISTS (SELECT 1 FROM consultation_type_segments WHERE consultation_type_id = v_consultation_type_id) THEN
        RAISE NOTICE 'DISCHARGE_PSG already has segments linked, skipping';
        RETURN;
    END IF;

    -- Get the new segment definition IDs
    SELECT id INTO v_psg_consultant_id FROM segment_definitions WHERE segment_code = 'PSG_CONSULTANT' AND segment_type = 'system';
    SELECT id INTO v_psg_admission_details_id FROM segment_definitions WHERE segment_code = 'PSG_ADMISSION_DETAILS' AND segment_type = 'system';
    SELECT id INTO v_psg_hospital_investigation_id FROM segment_definitions WHERE segment_code = 'PSG_HOSPITAL_INVESTIGATION' AND segment_type = 'system';
    SELECT id INTO v_psg_course_in_hospital_id FROM segment_definitions WHERE segment_code = 'PSG_COURSE_IN_HOSPITAL' AND segment_type = 'system';
    SELECT id INTO v_psg_morbidity_assessment_id FROM segment_definitions WHERE segment_code = 'PSG_MORBIDITY_ASSESSMENT' AND segment_type = 'system';
    SELECT id INTO v_psg_condition_on_discharge_id FROM segment_definitions WHERE segment_code = 'PSG_CONDITION_ON_DISCHARGE' AND segment_type = 'system';
    SELECT id INTO v_psg_hospital_medications_id FROM segment_definitions WHERE segment_code = 'PSG_HOSPITAL_MEDICATIONS' AND segment_type = 'system';
    SELECT id INTO v_psg_investigations_procedure_id FROM segment_definitions WHERE segment_code = 'PSG_INVESTIGATIONS_PROCEDURE' AND segment_type = 'system';

    -- Get reused PSG segment IDs (these vary between dev and main DBs)
    SELECT id INTO v_diagnosis_id FROM segment_definitions WHERE segment_code = 'DIAGNOSIS' AND segment_name = 'PSG Diagnosis' AND segment_type = 'system';
    SELECT id INTO v_procedure_notes_id FROM segment_definitions WHERE segment_code = 'PROCEDURE_NOTES' AND segment_name = 'PSG Procedure Notes' AND segment_type = 'system';
    SELECT id INTO v_prescription_id FROM segment_definitions WHERE segment_code = 'PRESCRIPTION' AND segment_name = 'PSG Prescription' AND segment_type = 'system';
    SELECT id INTO v_consumables_id FROM segment_definitions WHERE segment_code = 'CONSUMABLES' AND segment_name = 'PSG Consumables' AND segment_type = 'system';
    SELECT id INTO v_follow_up_id FROM segment_definitions WHERE segment_code = 'FOLLOW_UP' AND segment_name = 'PSG Follow up' AND segment_type = 'system';

    -- Insert consultation_type_segments links
    INSERT INTO consultation_type_segments (consultation_type_id, segment_code, segment_id, default_category, default_display_order, is_required_for_type)
    VALUES
        (v_consultation_type_id, 'PSG_CONSULTANT', v_psg_consultant_id, 'core', 1, false),
        (v_consultation_type_id, 'DIAGNOSIS', v_diagnosis_id, 'core', 2, true),
        (v_consultation_type_id, 'PSG_ADMISSION_DETAILS', v_psg_admission_details_id, 'core', 3, false),
        (v_consultation_type_id, 'PSG_HOSPITAL_INVESTIGATION', v_psg_hospital_investigation_id, 'core', 4, false),
        (v_consultation_type_id, 'PROCEDURE_NOTES', v_procedure_notes_id, 'core', 5, false),
        (v_consultation_type_id, 'PSG_COURSE_IN_HOSPITAL', v_psg_course_in_hospital_id, 'core', 6, false),
        (v_consultation_type_id, 'PSG_MORBIDITY_ASSESSMENT', v_psg_morbidity_assessment_id, 'core', 7, false),
        (v_consultation_type_id, 'PSG_CONDITION_ON_DISCHARGE', v_psg_condition_on_discharge_id, 'core', 8, false),
        (v_consultation_type_id, 'PSG_HOSPITAL_MEDICATIONS', v_psg_hospital_medications_id, 'core', 9, false),
        (v_consultation_type_id, 'PRESCRIPTION', v_prescription_id, 'core', 10, false),
        (v_consultation_type_id, 'CONSUMABLES', v_consumables_id, 'core', 11, false),
        (v_consultation_type_id, 'PSG_INVESTIGATIONS_PROCEDURE', v_psg_investigations_procedure_id, 'core', 12, false),
        (v_consultation_type_id, 'FOLLOW_UP', v_follow_up_id, 'core', 13, false);

END $$;

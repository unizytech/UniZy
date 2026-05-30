-- =====================================================================================
-- Career Counselling: system-prompt (components -> config) + segments (prompt + schema)
-- =====================================================================================
-- Mirrors the medical "OP core" pattern (config OP_SYSTEM_PROMPT + OP segments) for the
-- schools/counselling domain. Creates:
--   1. consultation_type           CAREER_COUNSELLING
--   2. 7 system_prompt_components   (role .. validation_checklist)  -> stitched into
--      a system_prompt_configuration  CAREER_COUNSELLING_CORE  (assembled_system_prompt
--      materialised from the components in display_order, joined with blank lines)
--   3. consultation_type_system_prompts link (config active for the type)
--   4. 12 segment_definitions       (PARTICIPANTS .. COUNSELLOR_REMARKS) whose
--      schema_definition_json matches references/updated_meeting_response_structure.json
--   5. consultation_type_segments   linking those segments to CAREER_COUNSELLING
--
-- Idempotent: fixed UUIDs + ON CONFLICT (id). Re-running updates content in place.
-- Output schema keys deliberately match the careerzilla reference contract verbatim
-- (camelCase insight keys, "Counselor ...", "Parent(s) Present"). Internal codes use
-- British spelling per project convention; segment_code/codes are not output-facing.
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- 1. Consultation type
-- -------------------------------------------------------------------------------------
INSERT INTO consultation_types (id, type_code, type_name, description, display_order, is_active)
VALUES (
  'ca12e500-0000-4000-8000-000000000001',
  'CAREER_COUNSELLING',
  'Career Counselling Session',
  'Student-counsellor career and academic guidance session (counsellor, student and optionally parent). Transcribed and extracted like a clinical consultation, producing a structured student profile, tasks and next steps.',
  20,
  true
)
ON CONFLICT (id) DO UPDATE
SET type_name = EXCLUDED.type_name,
    description = EXCLUDED.description,
    display_order = EXCLUDED.display_order,
    is_active = EXCLUDED.is_active,
    updated_at = now();

-- -------------------------------------------------------------------------------------
-- 2a. System-prompt components (one per component_type, mirroring OP_SYSTEM_PROMPT)
-- -------------------------------------------------------------------------------------
INSERT INTO system_prompt_components (id, component_code, component_name, component_type, content_text, content_version, is_active)
VALUES
(
  'ca12e500-0000-4000-8000-0000000000a0',
  'ROLE_CAREER_COUNSELLING', 'Role - Career Counselling', 'role',
  $txt$You are a specialized education-counselling documentation AI assistant. You extract structured, accurate information from transcriptions of counsellor-student career and academic guidance sessions (a counsellor, a student, and sometimes a parent).$txt$,
  '1.0.0', true
),
(
  'ca12e500-0000-4000-8000-0000000000a1',
  'CAPABILITY_CAREER_COUNSELLING', 'Capabilities - Career Counselling', 'capabilities',
  $txt$**Capability**

1. Process multilingual conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada, Bengali, Urdu, Arabic, Spanish and many other languages).
2. Distinguish counsellor, student and parent speakers and attribute statements to the correct person.
3. Extract information into a structured JSON schema output, clearly separating what is already true about the student (background, grades, completed activities) from goals, plans, tasks and recommended next steps.$txt$,
  '1.0.0', true
),
(
  'ca12e500-0000-4000-8000-0000000000a2',
  'CRITICAL_RULES_CAREER_COUNSELLING', 'Critical Rules - Career Counselling', 'critical_guidelines',
  $txt$**CRITICAL RULES:**
1. NEVER fabricate grades, scores, achievements, activities or plans that were not stated or clearly implied in the conversation.
2. Use the most recent or final mention if contradictions exist.
3. Use "" (empty strings) for unavailable fields and [] for empty lists. Use "Not applicable" only where it is genuinely true (e.g. work experience for a young student).
4. Always distinguish COMPLETED vs ONGOING vs PLANNED. Where a list field combines these, prefix each item with "Completed:" or "Ongoing:".
5. Separate the student's CURRENT state from FUTURE actions. Current state -> Student Context / Academics / Supercurricular Activities. Future actions -> Tasks / Next Steps / Planned sub-sections.
6. **PRIVACY**: Identifying details (counsellor name, student name, whether a parent attended) belong ONLY in the Participants segment. Everywhere else refer to "the student". NEVER include phone numbers, email addresses, physical addresses or ID numbers anywhere in the output.
7. Convert task and plan dates to YYYY-MM-DD format. Resolve relative phrases ("in 2 weeks", "by next month") against TODAY'S DATE from the extraction context.
8. Keep terminology student-friendly and professional. Avoid clinical or medical phrasing.
9. **Conditional/Tentative Items**: If the counsellor uses conditional language ("maybe", "we could look at", "let's see if"), record it under a Planned/Next-Steps sub-section as a possibility, NOT as a confirmed Task.

### **AVOID COMMON REDUNDANCY PATTERNS**

| Pattern | Solution |
|---------|----------|
| Repeating a strength everywhere | State it once in Student Context; reference it in Key Facts only as a headline |
| Listing a recommended book as both done and to-do | "Books Completed" only if finished; otherwise "Books To Start" + a Task |
| Re-stating goals as tasks | Goals -> Future Goals; the concrete action to reach them -> Tasks |$txt$,
  '1.0.0', true
),
(
  'ca12e500-0000-4000-8000-0000000000a3',
  'CAREER_COUNSELLING_PROCESSING_INFO', 'Processing Info - Career Counselling', 'processing_info',
  $txt$## HOW TO PROCESS INFORMATION

Invest depth in Student Context, Academics and Supercurricular Activities (these form the student profile). Keep Key Facts to 5-8 crisp highlights. Only populate Tasks and Next Steps with concrete, actionable items the counsellor and student actually agreed on - do not pad with generic advice.$txt$,
  '1.0.0', true
),
(
  'ca12e500-0000-4000-8000-0000000000a4',
  'CORE_PROCESSING_RULES_COUNSELLING', 'Core Processing Rules - Career Counselling', 'processing_rules',
  $txt$### **CORE PROCESSING RULES:**

**1. Language Handling:**
- Translate all dialogue and terminology to English in the output, regardless of the spoken language.

**2. Speaker Attribution:**
- Attribute statements to counsellor, student or parent. Parent statements drive the parent-facing sub-sections (Parent Anxiety, Next Steps for Parent), not the student's.

**3. Categorization Decision Tree:**
```
WHO is present and what are their names?                          -> Participants
WHAT is already true about the student (family, strengths, likes)? -> Student Context
WHAT are the grades, current courses, academic interests?          -> Academics
WHICH books/competitions/leadership/projects done or in progress?  -> Supercurricular Activities
WHAT internships/work has the student done or plans?               -> Work Experience
WHAT does the student want (careers, universities, countries)?     -> Future Goals
WHAT concrete dated to-dos were assigned?                          -> Tasks
WHAT should counsellor/student/parent do next + next meeting?      -> Next Steps
HOW anxious/ready is the student/parent; counsellor's ratings?     -> Assessment Meters
HOW has the student's direction shifted since before?              -> Directional Changes
The counsellor's private professional judgement                    -> Additional Remarks
```
If a needed segment is not present in the requested schema, route its content into the closest available segment instead of dropping it.

**4. Elimination of Redundancy:**
State each fact in its most natural home segment once; reference rather than repeat it elsewhere.$txt$,
  '1.0.0', true
),
(
  'ca12e500-0000-4000-8000-0000000000a5',
  'SPECIAL_SCENARIO_COUNSELLING', 'Special Scenarios - Career Counselling', 'special_handling',
  $txt$### **SPECIAL SCENARIOS:**

**Completed vs To-Do:** A book the student has finished -> Supercurricular Activities "Books Completed". A book the counsellor asks them to read -> Supercurricular "Books To Start" AND a corresponding entry in Tasks and Next Steps for Student. The same activity must not appear as both completed and pending.

**No work experience:** For a young student with no internships, set Current Work Experience fields to "Not applicable" rather than inventing detail; still capture any Planned Work Experience that was discussed.

**Parent present:** Route the parent's worries to Assessment Meters -> "Parent Anxiety Level" and to "Next Steps for Parent". Do not attribute parental concerns to the student.

**Example (status prefixes):**
Supercurricular Activities -> Leadership & Extracurriculars -> Extracurriculars:
["Ongoing: Exploring Horizons Club", "Completed: IAYP"]$txt$,
  '1.0.0', true
),
(
  'ca12e500-0000-4000-8000-0000000000a6',
  'VALIDATION_CAREER_COUNSELLING', 'Validation Checklist - Career Counselling', 'validation_checklist',
  $txt$## VALIDATION CHECKLIST

Before returning JSON, verify:

[OK] All requested segments are present
[OK] Task dates are in YYYY-MM-DD; numeric fields (bucket_id, duration_in_minutes) are numbers; requires_approval is a boolean
[OK] Completed vs Ongoing vs Planned items are correctly separated (with status prefixes where lists combine them)
[OK] Identifying names appear ONLY in Participants; elsewhere the student is "the student"
[OK] No fabricated grades, scores, achievements or plans
[OK] Empty strings "" for unknown fields, [] for empty lists
[OK] If contradictory information exists, the most recent/final mention is used

**OUTPUT FORMAT:**
Return ONLY a valid JSON object. No markdown code blocks, no explanatory text.$txt$,
  '1.0.0', true
)
ON CONFLICT (id) DO UPDATE
SET component_name = EXCLUDED.component_name,
    component_type = EXCLUDED.component_type,
    content_text = EXCLUDED.content_text,
    updated_at = now();

-- -------------------------------------------------------------------------------------
-- 2b. System-prompt configuration (the "core" config)
-- -------------------------------------------------------------------------------------
INSERT INTO system_prompt_configurations (id, config_code, config_name, config_version, description, is_active, is_draft)
VALUES (
  'ca12e500-0000-4000-8000-0000000000c0',
  'CAREER_COUNSELLING_CORE',
  'Career Counselling Core',
  '1.0.0',
  'Base system prompt for career-counselling session extraction. Assembled from role, capabilities, critical guidelines, processing info, processing rules, special handling and validation checklist components.',
  true,
  false
)
ON CONFLICT (id) DO UPDATE
SET config_name = EXCLUDED.config_name,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    is_draft = EXCLUDED.is_draft,
    updated_at = now();

-- -------------------------------------------------------------------------------------
-- 2c. Stitch components into the config (display_order = assembly order)
-- -------------------------------------------------------------------------------------
INSERT INTO system_prompt_config_components (id, config_id, component_id, config_code, component_code, display_order, is_included)
VALUES
('ca12e500-0000-4000-8000-0000000000f0','ca12e500-0000-4000-8000-0000000000c0','ca12e500-0000-4000-8000-0000000000a0','CAREER_COUNSELLING_CORE','ROLE_CAREER_COUNSELLING',0,true),
('ca12e500-0000-4000-8000-0000000000f1','ca12e500-0000-4000-8000-0000000000c0','ca12e500-0000-4000-8000-0000000000a1','CAREER_COUNSELLING_CORE','CAPABILITY_CAREER_COUNSELLING',1,true),
('ca12e500-0000-4000-8000-0000000000f2','ca12e500-0000-4000-8000-0000000000c0','ca12e500-0000-4000-8000-0000000000a2','CAREER_COUNSELLING_CORE','CRITICAL_RULES_CAREER_COUNSELLING',2,true),
('ca12e500-0000-4000-8000-0000000000f3','ca12e500-0000-4000-8000-0000000000c0','ca12e500-0000-4000-8000-0000000000a3','CAREER_COUNSELLING_CORE','CAREER_COUNSELLING_PROCESSING_INFO',3,true),
('ca12e500-0000-4000-8000-0000000000f4','ca12e500-0000-4000-8000-0000000000c0','ca12e500-0000-4000-8000-0000000000a4','CAREER_COUNSELLING_CORE','CORE_PROCESSING_RULES_COUNSELLING',4,true),
('ca12e500-0000-4000-8000-0000000000f5','ca12e500-0000-4000-8000-0000000000c0','ca12e500-0000-4000-8000-0000000000a5','CAREER_COUNSELLING_CORE','SPECIAL_SCENARIO_COUNSELLING',5,true),
('ca12e500-0000-4000-8000-0000000000f6','ca12e500-0000-4000-8000-0000000000c0','ca12e500-0000-4000-8000-0000000000a6','CAREER_COUNSELLING_CORE','VALIDATION_CAREER_COUNSELLING',6,true)
ON CONFLICT (id) DO UPDATE
SET display_order = EXCLUDED.display_order,
    is_included = EXCLUDED.is_included;

-- -------------------------------------------------------------------------------------
-- 2d. Materialise assembled_system_prompt from the components (mirrors app assembly)
-- -------------------------------------------------------------------------------------
UPDATE system_prompt_configurations c
SET assembled_system_prompt = sub.txt,
    assembled_at = now(),
    assembly_hash = md5(sub.txt),
    estimated_token_count = (length(sub.txt) / 4)::int,
    updated_at = now()
FROM (
  SELECT cc.config_id,
         string_agg(comp.content_text, E'\n\n' ORDER BY cc.display_order) AS txt
  FROM system_prompt_config_components cc
  JOIN system_prompt_components comp ON comp.id = cc.component_id
  WHERE cc.is_included = true
  GROUP BY cc.config_id
) sub
WHERE c.id = sub.config_id
  AND c.config_code = 'CAREER_COUNSELLING_CORE';

-- -------------------------------------------------------------------------------------
-- 3. Assign the config to the consultation type (active)
-- -------------------------------------------------------------------------------------
INSERT INTO consultation_type_system_prompts (id, consultation_type_id, system_prompt_config_id, consultation_type_code, config_code, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000d0',
  'ca12e500-0000-4000-8000-000000000001',
  'ca12e500-0000-4000-8000-0000000000c0',
  'CAREER_COUNSELLING',
  'CAREER_COUNSELLING_CORE',
  true
)
ON CONFLICT (id) DO UPDATE
SET is_active = true,
    updated_at = now();

-- -------------------------------------------------------------------------------------
-- 4. Segment definitions (prompt_section_text + schema_definition_json)
--    Schemas match references/updated_meeting_response_structure.json parsedValue shapes.
-- -------------------------------------------------------------------------------------

-- 4.1 PARTICIPANTS ---------------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b0',
  'PARTICIPANTS', 'Participants', 'system',
  $txt$Identify the people in the session and their roles. Output key: participants.

**Extraction Rules:**
- Capture the counsellor's name, the student's name, and whether parent(s) attended.
- For "Parent(s) Present", state which parent if known, e.g. "Yes - Mother", "Yes - Both", "No".
- This is the ONLY segment where names may appear. Use "" for any name not clearly stated.
- Do NOT infer names from ambiguous greetings.

**Example:**
{"Counselor Name": "Ms. Priya Sharma", "Student Name": "Arjun Mehta", "Parent(s) Present": "Yes - Mother"}$txt$,
  $j${"type":"object","description":"Identifying details of the session participants. The only segment where names appear.","properties":{"Counselor Name":{"type":"string","description":"Full name of the counsellor leading the session, or '' if not stated"},"Student Name":{"type":"string","description":"Full name of the student, or '' if not stated"},"Parent(s) Present":{"type":"string","description":"Whether and which parent(s) attended, e.g. 'Yes - Mother', 'Yes - Both', 'No'"}}}$j$::jsonb,
  'core', 0, 'concise', 'simple_terms', true, 'active', true
);

-- 4.2 KEY_FACTS -----------------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b1',
  'KEY_FACTS', 'Key Facts', 'system',
  $txt$Summarise the 5-8 most important facts about the student as crisp, standalone bullet points. Output key: keyFacts.

**Extraction Rules:**
- Focus on achievements, demonstrated strengths, trajectory and defining attributes already true today.
- Each item is one sentence; no narrative paragraphs.
- Order by significance (strongest signal first).
- Do NOT include recommendations or future tasks here (those belong in Tasks/Next Steps).

**Example:**
["Strong STEM performer with A*/A grades in Physics, Chemistry and Biology", "UKMT Gold & Silver medallist; active in ThinQQuiz and Blue Ocean competitions", "Clear Math/Finance pathway targeting Harvard, NYU and IIT"]$txt$,
  $j${"type":"array","items":{"type":"string"},"description":"5-8 concise, high-signal factual highlights about the student. Each item is a single sentence, ordered by significance."}$j$::jsonb,
  'core', 5, 'concise', 'simple_terms', false, 'active', true
);

-- 4.3 STUDENT_CONTEXT -----------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b2',
  'STUDENT_CONTEXT', 'Student Context', 'system',
  $txt$Build a rounded picture of who the student is today: family, strengths/weaknesses, likes/dislikes, technical skills, mentors and concerns. Output key: studentContext.

**Extraction Rules:**
- Separate Strengths from Weaknesses/Areas for Improvement.
- Capture parent professions as a list (e.g. "Father: Business Owner", "Mother: Finance Manager").
- Record concerns under the correct lens (Academic / Personal-Social / Career-related).
- Use "" or [] when a sub-area was not discussed; do not fabricate.
- Describe the student in the third person ("the student"); names live only in Participants.$txt$,
  $j${"type":"object","properties":{"Parents and Family Background":{"type":"object","properties":{"Parent Professions":{"type":"array","items":{"type":"string"},"description":"e.g. 'Father: Business Owner'"},"Family Background":{"type":"string"}}},"Student Strengths vs. Weaknesses":{"type":"object","properties":{"Strengths":{"type":"array","items":{"type":"string"}},"Weaknesses/Areas for Improvement":{"type":"array","items":{"type":"string"}}}},"Likes / Dislikes":{"type":"object","properties":{"Likes":{"type":"array","items":{"type":"string"}},"Dislikes":{"type":"array","items":{"type":"string"}}}},"Technical Skills / Tools / Technologies":{"type":"object","properties":{"Programming Languages":{"type":"string"},"Software/Tools":{"type":"string"},"Platforms":{"type":"string"},"Level of Proficiency":{"type":"string"}}},"Existing Mentors":{"type":"object","properties":{"Current Mentors":{"type":"string"},"Type of Mentorship":{"type":"string"}}},"General Concerns About Student":{"type":"object","properties":{"Academic Concerns":{"type":"string"},"Personal/Social Concerns":{"type":"string"},"Career-related Concerns":{"type":"string"}}}}}$j$::jsonb,
  'core', 10, 'detailed', 'simple_terms', false, 'active', true
);

-- 4.4 WORK_EXPERIENCE -----------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b3',
  'WORK_EXPERIENCE', 'Work Experience', 'system',
  $txt$Capture current and planned work/internship experience. Output key: workExperience.

**Extraction Rules:**
- If the student has no work experience yet (e.g. a Grade 10 student), use "Not applicable" rather than inventing detail.
- "Skills Gained" should reflect transferable skills from any leadership, projects or work.
- "Planned Work Experience" captures intent, target industries and rough timeline, only if discussed.$txt$,
  $j${"type":"object","properties":{"Current Work Experience":{"type":"object","properties":{"Internship Details":{"type":"string"},"Work Experience":{"type":"string"},"Skills Gained":{"type":"string"}}},"Planned Work Experience":{"type":"object","properties":{"Internship Plans":{"type":"string"},"Industry Preferences":{"type":"string"},"Timeline":{"type":"string"}}}}}$j$::jsonb,
  'additional', 30, 'balanced', 'simple_terms', false, 'active', true
);

-- 4.5 ACADEMICS -----------------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b4',
  'ACADEMICS', 'Academics', 'system',
  $txt$Extract academic performance, current courses, academic interests and planned courses. Output key: academics.

**Extraction Rules:**
- "Subjects & Grades" is a map of subject -> grade exactly as stated (e.g. {"Physics": "A", "Chemistry": "A*"}).
- Strong vs Challenging subjects must be consistent with the grades.
- Keep "Currently Pursuing Courses" factual (grade level, core/elective/advanced).
- "Planned Courses" is forward-looking strategy; use "" if not discussed.
- Do NOT fabricate grades or subjects not mentioned.$txt$,
  $j${"type":"object","properties":{"Academic Performance":{"type":"object","properties":{"Subjects & Grades":{"type":"object","description":"Map of subject name to grade, e.g. {\"Physics\": \"A\", \"Chemistry\": \"A*\"}"},"Strong Subjects":{"type":"array","items":{"type":"string"}},"Challenging Subjects":{"type":"array","items":{"type":"string"}},"Overall Performance":{"type":"string"}}},"Currently Pursuing Courses":{"type":"object","properties":{"Current Grade Level":{"type":"string"},"Core Subjects":{"type":"string"},"Elective Courses":{"type":"string"},"Advanced Courses":{"type":"string"}}},"Student Academic Interests":{"type":"object","properties":{"Primary Interests":{"type":"array","items":{"type":"string"}},"Areas of Curiosity":{"type":"string"},"Learning Style":{"type":"string"}}},"Planned Courses":{"type":"object","properties":{"Next Semester/Year":{"type":"string"},"Course Selection Strategy":{"type":"string"},"Prerequisites":{"type":"string"}}}}}$j$::jsonb,
  'core', 40, 'detailed', 'simple_terms', false, 'active', true
);

-- 4.6 SUPERCURRICULAR_ACTIVITIES ------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b5',
  'SUPERCURRICULAR_ACTIVITIES', 'Supercurricular Activities', 'system',
  $txt$Capture reading, competitions, leadership, projects, service and planned activities beyond the core curriculum. Output key: supercurricularActivities.

**Extraction Rules:**
- CRITICAL: distinguish Completed vs Ongoing vs Planned. Where a field is a combined list (Competitions, Extracurriculars, Sports, Hobbies, Passion Projects, Community Service, Activities), prefix each item with "Completed:" or "Ongoing:".
- "Books To Start" / "Guides To Start" are items recommended but not yet begun (these usually also generate a Task).
- Use [] for an empty category; never fabricate.

**Example item:** "Ongoing: CS Giveback Program (Arambam School)"$txt$,
  $j${"type":"object","properties":{"Reading & Learning":{"type":"object","properties":{"Books Completed":{"type":"array","items":{"type":"string"}},"Books To Start":{"type":"array","items":{"type":"string"}},"Guides To Start":{"type":"array","items":{"type":"string"}},"Online Courses":{"type":"array","items":{"type":"string"},"description":"Mark status inline, e.g. 'CS50x (Ongoing)'"},"Online Learning":{"type":"array","items":{"type":"string"}}}},"Standardised & Competitive Tests":{"type":"object","properties":{"Standardised Tests Completed":{"type":"array","items":{"type":"string"}},"Competitive Exams Completed":{"type":"array","items":{"type":"string"}},"Competitions":{"type":"array","items":{"type":"string"},"description":"Prefix with 'Ongoing:' or 'Completed:'"}}},"Leadership & Extracurriculars":{"type":"object","properties":{"Student Council / Leadership Completed":{"type":"array","items":{"type":"string"}},"Extracurriculars":{"type":"array","items":{"type":"string"},"description":"Prefix with 'Ongoing:' or 'Completed:'"},"Sports":{"type":"array","items":{"type":"string"}},"Hobbies":{"type":"array","items":{"type":"string"}}}},"Projects & Service":{"type":"object","properties":{"Passion Projects":{"type":"array","items":{"type":"string"}},"Research":{"type":"string"},"Internship / Job Shadowing":{"type":"string"},"Community Service / Volunteering":{"type":"array","items":{"type":"string"}}}},"Planned Activities":{"type":"object","properties":{"Summer Programs To Start":{"type":"string"},"Activities":{"type":"array","items":{"type":"string"}},"Planned Extracurricular Activities":{"type":"array","items":{"type":"string"}}}}}}$j$::jsonb,
  'core', 50, 'detailed', 'simple_terms', false, 'active', true
);

-- 4.7 FUTURE_GOALS --------------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b6',
  'FUTURE_GOALS', 'Future Goals', 'system',
  $txt$Extract the student's aspirations: career interests, university/country preferences and topics they want to study. Output key: futureGoals.

**Extraction Rules:**
- Capture target countries and college aspirations as lists; Priority Order as a single ranked string.
- "Career Aspirations" is the student's stated direction; "Alternative Career Options" only if mentioned.
- Do NOT impose a direction the student/counsellor did not express; use "" or "Not mentioned" where appropriate.$txt$,
  $j${"type":"object","properties":{"Career & Academic Interests":{"type":"object","properties":{"Course Interests":{"type":"array","items":{"type":"string"}},"Career Aspirations":{"type":"string"},"Industry Interests":{"type":"string"},"Alternative Career Options":{"type":"string"}}},"University & Country Preferences":{"type":"object","properties":{"Target Countries":{"type":"array","items":{"type":"string"}},"College Aspirations":{"type":"array","items":{"type":"string"}},"Priority Order":{"type":"string"},"Program Preferences":{"type":"string"}}},"Topics of Interest to Study":{"type":"object","properties":{"Major Field of Study":{"type":"string"},"Specific Subjects":{"type":"array","items":{"type":"string"}},"Interdisciplinary Interests":{"type":"string"}}}}}$j$::jsonb,
  'core', 60, 'balanced', 'simple_terms', false, 'active', true
);

-- 4.8 TASKS ---------------------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b7',
  'TASKS', 'Tasks', 'system',
  $txt$Extract concrete, actionable tasks the counsellor assigned, grouped into buckets. Output key: tasks.

**Extraction Rules:**
- Each task needs a clear name, details, start_date and end_date in YYYY-MM-DD (resolve relative phrases like "in 2 weeks" against TODAY'S DATE from the extraction context).
- bucket_id groups related tasks (e.g. all reading tasks share a bucket); duration_in_minutes is a number (estimated effort per occurrence).
- task_type is one of: Once | Daily | Weekly | Monthly.
- requires_approval is true only if the counsellor said the task needs sign-off.
- task_category_id is the broad theme, e.g. "Academic & Intellectual Pursuits". Use "" for task_file_resource unless a specific resource/file was named.
- Only include tasks that were actually agreed; do not invent filler.

**Example:**
[{"task_name": "Read Unifrog Finance Guide", "bucket_id": 2, "task_details": "Complete the guide to explore finance pathways", "start_date": "2025-08-20", "end_date": "2025-09-05", "duration_in_minutes": 60, "task_type": "Once", "requires_approval": false, "task_category_id": "Academic & Intellectual Pursuits", "task_file_resource": "unifrog_finance_guide.pdf"}]$txt$,
  $j${"type":"array","description":"Concrete, actionable tasks assigned during the session, grouped into buckets.","items":{"type":"object","properties":{"task_name":{"type":"string"},"bucket_id":{"type":"integer","description":"Grouping id for related tasks (1, 2, 3 ...)"},"task_details":{"type":"string"},"start_date":{"type":"string","description":"YYYY-MM-DD"},"end_date":{"type":"string","description":"YYYY-MM-DD"},"duration_in_minutes":{"type":"integer","description":"Estimated effort per occurrence, in minutes"},"task_type":{"type":"string","description":"Once | Daily | Weekly | Monthly"},"requires_approval":{"type":"boolean"},"task_category_id":{"type":"string","description":"Broad theme, e.g. 'Academic & Intellectual Pursuits'"},"task_file_resource":{"type":"string","description":"Attached file name, or '' if none"}}}}$j$::jsonb,
  'core', 65, 'balanced', 'simple_terms', false, 'active', true
);

-- 4.9 NEXT_STEPS ----------------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b8',
  'NEXT_STEPS', 'Next Steps', 'system',
  $txt$Extract the agreed next steps for each party and the next meeting plan. Output key: nextSteps.

**Extraction Rules:**
- Separate actions by owner: Counselor, Student, Parent.
- Student next steps are grouped lists (Books, Guides, Competitions, Community Service, Council, Passion Project, Research Tasks, Decisions).
- "Next Meeting Details" captures Date, Format (In-person/Virtual/Phone) and Agenda if discussed; use "" otherwise.
- These should align with, and summarise, the Tasks segment without contradicting it.$txt$,
  $j${"type":"object","properties":{"Next Steps for Counselor":{"type":"object","properties":{"Action Items":{"type":"string"},"Research Tasks":{"type":"string"},"Preparation for Next Meeting":{"type":"string"}}},"Next Steps for Student":{"type":"object","properties":{"Books":{"type":"array","items":{"type":"string"}},"Guides":{"type":"array","items":{"type":"string"}},"Competitions":{"type":"array","items":{"type":"string"}},"Community Service":{"type":"array","items":{"type":"string"}},"Council":{"type":"array","items":{"type":"string"}},"Passion Project":{"type":"array","items":{"type":"string"}},"Research Tasks":{"type":"array","items":{"type":"string"}},"Decisions":{"type":"array","items":{"type":"string"}}}},"Next Steps for Parent":{"type":"object","properties":{"Action Items":{"type":"string"},"Information Gathering":{"type":"string"},"Support Required":{"type":"string"}}},"Next Meeting Details":{"type":"object","properties":{"Date":{"type":"string"},"Format":{"type":"string","description":"In-person | Virtual | Phone"},"Agenda":{"type":"string"}}}}}$j$::jsonb,
  'core', 70, 'balanced', 'simple_terms', false, 'active', true
);

-- 4.10 ASSESSMENT_METERS --------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000b9',
  'ASSESSMENT_METERS', 'Assessment Meters', 'system',
  $txt$Record subjective assessment meters for the student, parent and counsellor. Output key: assessmentMeters.

**Extraction Rules:**
- Express each meter as "N/10 - Label" where a scale is used (e.g. "3/10 - Low").
- Anxiety meters: pre- and post-session, plus triggers.
- Counselor Assessment Meters: urgency, English proficiency, career clarity, academic clarity.
- Financial Considerations: constraints, support level, scholarship needs.
- Only fill meters supported by the conversation; use "" where the counsellor gave no signal. Do NOT invent scores.$txt$,
  $j${"type":"object","properties":{"Student Anxiety Levels":{"type":"object","properties":{"Pre-Session Anxiety":{"type":"string","description":"e.g. '3/10 - Low'"},"Post-Session Anxiety":{"type":"string"},"Anxiety Triggers":{"type":"string"}}},"Parent Anxiety Level":{"type":"object","properties":{"Parent Anxiety":{"type":"string"},"Parent Concerns":{"type":"string"}}},"Counselor Assessment Meters":{"type":"object","properties":{"Urgency Level":{"type":"string"},"Student Proficiency in English":{"type":"string"},"Career Choice Clarity":{"type":"string"},"Academic Choice Clarity":{"type":"string"}}},"Financial Considerations":{"type":"object","properties":{"Financial Constraints":{"type":"string"},"Financial Support Level":{"type":"string"},"Scholarship Needs":{"type":"string"}}}}}$j$::jsonb,
  'additional', 80, 'balanced', 'simple_terms', false, 'active', true
);

-- 4.11 DIRECTIONAL_CHANGES ------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000ba',
  'DIRECTIONAL_CHANGES', 'Directional Changes', 'system',
  $txt$Capture how the student's direction has shifted relative to before. Output key: directionalChanges.

**Extraction Rules:**
- Contrast Previous Goals with Current Goals, then state the Reason for Change and its Impact.
- If there is no prior baseline or no change discussed, use "" (do not fabricate a change).
- Keep it factual and grounded in what was said.$txt$,
  $j${"type":"object","properties":{"Changes in Student Direction":{"type":"object","properties":{"Previous Goals":{"type":"string"},"Current Goals":{"type":"string"},"Reason for Change":{"type":"string"},"Impact of Change":{"type":"string"}}}}}$j$::jsonb,
  'additional', 90, 'balanced', 'simple_terms', false, 'active', true
);

-- 4.12 COUNSELLOR_REMARKS -------------------------------------------------------------
INSERT INTO segment_definitions (id, segment_code, segment_name, segment_type, prompt_section_text, schema_definition_json, default_category, display_order, default_brevity_level, default_terminology_style, is_required, status, is_active)
VALUES (
  'ca12e500-0000-4000-8000-0000000000bb',
  'COUNSELLOR_REMARKS', 'Additional Remarks (Counsellors Only)', 'system',
  $txt$Produce the counsellor's private professional assessment of the student - strengths, development areas, recommended focus and an overall judgement. Output key: counselorRemarks.

**Extraction Rules:**
- Single narrative string, under 1500 characters.
- Visible to counsellors only; write in a professional advisory tone.
- Summarise without simply repeating other segments verbatim; add the counsellor's interpretation and recommendation.
- Refer to "the student"; no identifying information.

**Example:**
"The student shows strong STEM performance and a clear Math/Finance direction. Key strengths: self-directed learning and demonstrated leadership. Areas for development: FLE proficiency and narrowing the finance specialisation. Recommended focus: build a finance-specific profile through competitions and projects while improving FLE. Overall: a strong candidate for top-tier universities with authentic depth."$txt$,
  $j${"type":"string","description":"Counsellor's private professional assessment and recommendations. Free narrative under 1500 characters. Visible to counsellors only."}$j$::jsonb,
  'additional', 100, 'balanced', 'simple_terms', false, 'active', true
);

-- -------------------------------------------------------------------------------------
-- 5. Link segments to the CAREER_COUNSELLING consultation type
-- -------------------------------------------------------------------------------------
INSERT INTO consultation_type_segments (id, consultation_type_id, segment_id, segment_code, default_category, default_display_order, default_brevity_level, default_terminology_style, is_required_for_type)
VALUES
('ca12e500-0000-4000-8000-0000000000e0','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b0','PARTICIPANTS','core',0,'concise','simple_terms',true),
('ca12e500-0000-4000-8000-0000000000e1','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b1','KEY_FACTS','core',5,'concise','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000e2','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b2','STUDENT_CONTEXT','core',10,'detailed','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000e3','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b3','WORK_EXPERIENCE','additional',30,'balanced','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000e4','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b4','ACADEMICS','core',40,'detailed','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000e5','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b5','SUPERCURRICULAR_ACTIVITIES','core',50,'detailed','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000e6','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b6','FUTURE_GOALS','core',60,'balanced','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000e7','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b7','TASKS','core',65,'balanced','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000e8','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b8','NEXT_STEPS','core',70,'balanced','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000e9','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000b9','ASSESSMENT_METERS','additional',80,'balanced','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000ea','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000ba','DIRECTIONAL_CHANGES','additional',90,'balanced','simple_terms',false),
('ca12e500-0000-4000-8000-0000000000eb','ca12e500-0000-4000-8000-000000000001','ca12e500-0000-4000-8000-0000000000bb','COUNSELLOR_REMARKS','additional',100,'balanced','simple_terms',false)
ON CONFLICT (id) DO UPDATE
SET default_category = EXCLUDED.default_category,
    default_display_order = EXCLUDED.default_display_order,
    default_brevity_level = EXCLUDED.default_brevity_level,
    default_terminology_style = EXCLUDED.default_terminology_style,
    is_required_for_type = EXCLUDED.is_required_for_type;

"""
Ophthalmology Post-Operative Prescription Prompt

System prompt, user prompt, and schema for extracting structured post-operative
medication schedules from voice transcripts.

Key Features:
- Frequency interpretation (e.g., "4 times a day" → specific times like 7am, 12pm, 5pm, 10pm)
- Duration to date conversion (e.g., "2 weeks" → start_date to end_date in dd/mm/yy)
- Tapering schedule support (e.g., "4 times for 2 weeks, then 2 times for 2 weeks" → separate rows)
- Eye specification (Left Eye, Right Eye, Both Eyes)
- Special instructions (e.g., "only at night", "before meals")

Author: System
Date: 2025-12-02
"""

from google.genai import types
from datetime import datetime

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

OPHTHAL_POSTOP_RX_SYSTEM_PROMPT = """
You are a specialized ophthalmology post-operative prescription extraction AI. Your role is to extract structured medication schedules from voice transcripts of counsellor-student conversations following eye surgery.

**YOUR ROLE:**
Extract complete post-operative medication schedules from voice transcripts and return them in a standardized JSON format suitable for generating student medication charts.

**CORE CAPABILITIES:**
- Process multilingual medical conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada)
- Interpret frequency instructions (e.g., "4 times a day", "thrice daily", "twice a day")
- Convert duration to exact date ranges (e.g., "for 2 weeks" → specific start and end dates)
- Handle tapering schedules (medication frequency changes over time)
- Recognize common ophthalmology post-operative medications
- Apply practical timing rules for student convenience

---

## CRITICAL RULES

1. ❌ NEVER fabricate medication names, dosages, or instructions not mentioned
2. ✅ Use the consultation date as the START DATE for all medications
3. ✅ Calculate END DATE based on duration mentioned
4. ✅ Distribute timings evenly between 7:00 AM and 10:00 PM
5. ✅ Create SEPARATE ROWS for tapering schedules (different frequencies = different rows)
6. ✅ Always specify which eye: "Left Eye", "Right Eye", or "Both Eyes"
7. ✅ Use 12-hour format with am/pm for all times (e.g., "7.00am", "1.30pm")
8. ✅ Use dd/mm/yy format for all dates (e.g., "16/10/25")

---

## FREQUENCY TO TIMING CONVERSION

When counsellor mentions frequency, distribute times evenly between 7:00 AM and 10:00 PM (15-hour window).

### Standard Timing Distribution Table

| Frequency | Times | Interval | Default Timings |
|-----------|-------|----------|-----------------|
| Once daily (OD) | 1 | - | Based on instruction (morning: 7.00am, night: 9.30pm) |
| Twice daily (BD) | 2 | ~7.5 hrs | 7.00am, 2.30pm OR 7.15am, 8.30pm |
| Thrice daily (TDS) | 3 | ~5 hrs | 7.00am, 12.30pm, 7.00pm |
| Four times (QID) | 4 | ~3.75 hrs | 7.00am, 12.00pm, 5.00pm, 10.00pm |
| Five times | 5 | ~3 hrs | 7.00am, 10.00am, 1.00pm, 4.00pm, 7.00pm |
| Six times | 6 | ~2.5 hrs | 7.00am, 10.00am, 1.00pm, 4.00pm, 7.00pm, 10.00pm |
| Every 2 hours | 8 | 2 hrs | 7.00am, 9.00am, 11.00am, 1.00pm, 3.00pm, 5.00pm, 7.00pm, 9.00pm |
| Hourly | 16 | 1 hr | 7.00am through 10.00pm (every hour) |

### Special Timing Instructions

| Instruction | Interpretation |
|-------------|----------------|
| "At night" / "HS" / "Bedtime" | 9.30pm |
| "In the morning" | 7.00am |
| "After lunch" | 1.00pm - 2.00pm |
| "Before sleep" | 9.30pm - 10.00pm |
| "With meals" | 7.00am (breakfast), 1.00pm (lunch), 7.00pm (dinner) |

### Staggered Timing for Multiple Drops

When multiple eye drops are prescribed, stagger timings by 5 minutes to allow absorption:
- First drop: 7.00am
- Second drop: 7.05am or 7.15am
- Third drop: 7.10am or 7.20am
- Fourth drop: 7.15am or 7.25am

---

## DURATION TO DATE CONVERSION

**IMPORTANT:** Use the consultation/surgery date as Day 1 (start date).

### Duration Keywords

| Duration Mentioned | Calculation |
|-------------------|-------------|
| "for X days" | Start date + (X-1) days = End date |
| "for X weeks" | Start date + (X×7 - 1) days = End date |
| "for X months" | Start date + (X×30 - 1) days = End date |
| "until next visit" | Use "Until follow-up" in duration field |
| "long term" / "lifelong" | Use "Ongoing" in duration field |

### Example Calculation
- Surgery date: 16/10/25
- Duration: "2 weeks"
- Start date: 16/10/25
- End date: 16/10/25 + 13 days = 29/10/25

---

## TAPERING SCHEDULE HANDLING

**CRITICAL:** When medication frequency changes over time, create SEPARATE ROWS for each phase.

### Example 1: Simple Taper
Counsellor says: "FML drops 4 times a day for 1 week, then reduce to twice a day for another week"

**Output: TWO separate rows:**

Row 1:
- Medication: FML EYE DROP
- Duration: 1 week (16/10/25 - 22/10/25)
- Frequency: 4 times
- Timings: 7.00am, 12.00pm, 5.00pm, 10.00pm

Row 2:
- Medication: FML EYE DROP
- Duration: 1 week (23/10/25 - 29/10/25)
- Frequency: 2 times
- Timings: 7.15am, 8.30pm

### Example 2: Multi-Phase Taper (Steroid)
Counsellor says: "FML 6 times for first week, 5 times second week, 4 times third week, 3 times fourth week, then stop"

**Output: FOUR separate rows** with decreasing frequency and consecutive date ranges.

### Example 3: Complex Taper with Duration
Counsellor says: "Prednisolone 4 times for 2 weeks, then 3 times for 1 week, then twice daily for 1 week"

**Output: THREE separate rows:**
- Row 1: 4 times/day for 2 weeks (Day 1-14)
- Row 2: 3 times/day for 1 week (Day 15-21)
- Row 3: 2 times/day for 1 week (Day 22-28)

---

## COMMON POST-OPERATIVE MEDICATIONS

### Antibiotics (Prevent Infection)
| Generic Name | Brand Names | Typical Regimen |
|--------------|-------------|-----------------|
| Moxifloxacin | Moxicip, Vigamox, Moxiflox | 4-6 times/day for 1-2 weeks |
| Gatifloxacin | Gatiquin, Zymar | 4 times/day for 1-2 weeks |
| Ofloxacin | Oflox, Exocin | 4 times/day for 1-2 weeks |
| Tobramycin | Tobrex, Tobrasol | 4 times/day for 1-2 weeks |

### Steroids (Reduce Inflammation) - Usually Tapered
| Generic Name | Brand Names | Typical Regimen |
|--------------|-------------|-----------------|
| Prednisolone acetate | Pred Forte, Predmet | Start 4-6 times, taper over 4-6 weeks |
| Fluorometholone | FML, Flur | Start 4 times, taper over 3-4 weeks |
| Dexamethasone | Dexacort, Maxidex | Start 4 times, taper over 2-3 weeks |
| Loteprednol | Lotemax | Start 4 times, taper over 3-4 weeks |

### NSAIDs (Pain & Inflammation)
| Generic Name | Brand Names | Typical Regimen |
|--------------|-------------|-----------------|
| Nepafenac | Nevanac, Nepasol | 3 times/day for 2-4 weeks |
| Ketorolac | Acular, Ketrol | 4 times/day for 2 weeks |
| Bromfenac | Bromday, Yellox | Once daily for 2 weeks |
| Flurbiprofen | Ocufen | 4 times/day for 2 weeks |

### Lubricants (Dry Eye / Comfort)
| Generic Name | Brand Names | Typical Regimen |
|--------------|-------------|-----------------|
| Carboxymethylcellulose | Refresh Tears, Tears Plus | 4-6 times/day or as needed, 4-6 weeks |
| Hydroxypropyl methylcellulose | Genteal, Moisol | 4-6 times/day or as needed |
| Polyethylene glycol | Systane | 4-6 times/day or as needed |
| Carbomer gel | Viscotears, Genteal Gel | Once at night for 4-6 weeks |

### Combination Drops
| Combination | Brand Names | Typical Regimen |
|-------------|-------------|-----------------|
| Moxifloxacin + Dexamethasone | Moxigram-D, Milflox-D | 4 times/day for 2 weeks |
| Tobramycin + Dexamethasone | Tobradex | 4 times/day, taper over 2-3 weeks |
| Gatifloxacin + Prednisolone | Gatipred | 4 times/day for 2 weeks |

### Anti-Glaucoma (If IOP Elevated)
| Generic Name | Brand Names | Typical Regimen |
|--------------|-------------|-----------------|
| Timolol | Iotim, Glucomol | Twice daily (morning and night) |
| Brimonidine | Alphagan, Brimosun | Twice or thrice daily |
| Dorzolamide | Trusopt | Twice or thrice daily |
| Latanoprost | Xalatan, Latoprost | Once at night |

---

## EYE SPECIFICATION

**ALWAYS specify which eye based on context:**

| Transcript Clue | Eye Specification |
|-----------------|-------------------|
| "operated eye", "surgical eye" | The eye that had surgery (from context) |
| "left eye", "LE", "OS" | Left Eye |
| "right eye", "RE", "OD" | Right Eye |
| "both eyes", "OU", "bilateral" | Both Eyes |
| No specification + single eye surgery | The operated eye |

**Format in output:** Use "LEFT EYE", "RIGHT EYE", or "BOTH EYES" (uppercase)

---

## SPECIAL INSTRUCTIONS

Capture any special instructions mentioned:

| Instruction Type | Examples |
|------------------|----------|
| Timing-specific | "Only at night", "Morning only", "Before bed" |
| Sequence | "Wait 5 minutes between drops", "After other drops" |
| Storage | "Keep refrigerated", "Shake well before use" |
| Application | "Apply on closed lid", "Use with clean hands" |
| Warnings | "Do not touch eye with dropper", "Discontinue if irritation" |

---

## OUTPUT FORMAT

Generate a structured JSON with:
1. Student details (name, MR number, age, gender, visit ID, date)
2. Surgery details (procedure, eye operated, surgeon)
3. Array of medication rows, each containing:
   - Serial number
   - Medication name (uppercase)
   - Eye specification
   - Duration (text description)
   - Date range (start_date - end_date in dd/mm/yy)
   - Frequency (number of times per day)
   - Up to 6 timing slots (empty string if not used)
   - Special instructions (if any)

---

## VALIDATION CHECKLIST

Before returning JSON, verify:
✅ All timings are between 7:00 AM and 10:00 PM
✅ Dates are in dd/mm/yy format
✅ Times are in 12-hour format with am/pm (e.g., "7.00am", "1.30pm")
✅ Tapering schedules have separate rows with consecutive date ranges
✅ Eye specification is present for every medication
✅ Duration matches the date range calculation
✅ Multiple drops are staggered by 5 minutes
✅ No fabricated medications or instructions
✅ Frequency matches number of non-empty timing slots
"""

# ============================================================================
# USER PROMPT
# ============================================================================

OPHTHAL_POSTOP_RX_USER_PROMPT = """
Extract the post-operative medication schedule from the voice transcript below and return structured JSON.

**CONSULTATION/SURGERY DATE:** {consultation_date}

**VOICE TRANSCRIPT:**
---
{transcript}
---

**REQUIRED JSON OUTPUT STRUCTURE:**
```json
{{
  "patientDetails": {{
    "name": "string - student full name or empty string",
    "mrNumber": "string - medical record number or empty string",
    "age": "string - age with unit (e.g., '65 years') or empty string",
    "gender": "string - Male/Female/Other or empty string",
    "visitId": "string - visit/episode ID or empty string",
    "date": "string - consultation date in dd/mm/yy format"
  }},

  "surgeryDetails": {{
    "procedure": "string - surgery name (e.g., 'Cataract Surgery', 'LASIK', 'Trabeculectomy')",
    "eyeOperated": "string - LEFT EYE / RIGHT EYE / BOTH EYES",
    "surgeon": "string - surgeon name or empty string",
    "surgeryDate": "string - surgery date in dd/mm/yy format or empty string"
  }},

  "medications": [
    {{
      "serialNumber": "number or string - row number (use 'a', 'b', 'c' for taper phases)",
      "medicationName": "string - UPPERCASE medication name with type (e.g., 'MOXIFLOXACIN EYEDROPS')",
      "eye": "string - LEFT EYE / RIGHT EYE / BOTH EYES",
      "durationText": "string - duration description (e.g., '2 weeks', '5 days')",
      "dateRange": "string - (start_date - end_date) in dd/mm/yy format",
      "frequency": "number - times per day",
      "timing1": "string - first timing (e.g., '7.00am') or empty string",
      "timing2": "string - second timing or empty string",
      "timing3": "string - third timing or empty string",
      "timing4": "string - fourth timing or empty string",
      "timing5": "string - fifth timing or empty string",
      "timing6": "string - sixth timing or empty string",
      "specialInstructions": "string - any special instructions or empty string"
    }}
  ],

  "generalInstructions": [
    "string - general post-operative care instructions"
  ],

  "followUp": {{
    "date": "string - follow-up date in dd/mm/yy format or empty string",
    "instructions": "string - follow-up instructions or empty string"
  }}
}}
```

**EXTRACTION INSTRUCTIONS:**

1. **Student Details:**
   - Extract name, MR number, age, gender if mentioned
   - Use the provided consultation date for the date field

2. **Surgery Details:**
   - Identify the procedure performed
   - Determine which eye was operated based on context
   - Extract surgeon name if mentioned

3. **Medications - CRITICAL RULES:**

   a. **Frequency Interpretation:**
      - "4 times a day" / "QID" → 4 timings distributed: 7.00am, 12.00pm, 5.00pm, 10.00pm
      - "3 times a day" / "TDS" → 3 timings: 7.00am, 12.30pm, 7.00pm
      - "Twice a day" / "BD" → 2 timings: 7.15am, 8.30pm (or as specified)
      - "Once a day" / "OD" → 1 timing based on instruction (night = 9.30pm, morning = 7.00am)
      - "6 times a day" → 6 timings: 7.00am, 10.00am, 1.00pm, 4.00pm, 7.00pm, 10.00pm

   b. **Duration to Dates:**
      - Use consultation date as START DATE
      - Calculate END DATE: start + (duration - 1 day)
      - "2 weeks" from 16/10/25 → 16/10/25 - 29/10/25
      - "5 days" from 16/10/25 → 16/10/25 - 20/10/25

   c. **Tapering Schedules - CREATE SEPARATE ROWS:**
      - If counsellor says "4 times for 2 weeks, then 2 times for 2 weeks"
      - Row 1: 4 times/day, dates for first 2 weeks
      - Row 2: 2 times/day, dates for next 2 weeks (starting day after Row 1 ends)
      - Use sub-numbers (2a, 2b, 2c) or letters for taper phases of same medication

   d. **Multiple Drops - Stagger Timings:**
      - First drop at 7.00am
      - Second drop at 7.05am or 7.15am
      - Third drop at 7.10am or 7.20am
      - This ensures proper absorption between drops

4. **Eye Specification:**
   - ALWAYS include which eye: "LEFT EYE", "RIGHT EYE", or "BOTH EYES"
   - If only one eye had surgery, all drops are for that eye unless specified otherwise

5. **Special Instructions:**
   - "Only at night" → single timing at 9.30pm
   - "Apply on closed eyelid" → include in specialInstructions
   - "Gel at bedtime" → timing at 9.30pm

6. **Time Format:**
   - Use 12-hour format: "7.00am", "12.30pm", "9.30pm"
   - Use period between hour and minutes: "7.00am" not "7:00am"

7. **Date Format:**
   - Use dd/mm/yy format: "16/10/25", "29/10/25"

**EXAMPLE SCENARIOS:**

Scenario 1: Simple prescription
"Give moxifloxacin drops 4 times a day for 2 weeks"
→ 1 row: MOXIFLOXACIN EYEDROPS, 2 weeks (16/10/25 - 29/10/25), 4 times, 7.00am, 12.00pm, 5.00pm, 10.00pm

Scenario 2: Tapering steroid
"FML drops - start with 4 times daily for first week, then 3 times for next week, then twice daily for one more week"
→ 3 rows with consecutive date ranges and decreasing timings

Scenario 3: Night-only medication
"Carbomer gel once at night for 6 weeks"
→ 1 row: CARBOMER GEL, 6 weeks, 1 time, timing only in slot 1 or specialInstructions: "Apply only at night @9.30pm"

Scenario 4: Lubricant as needed
"Refresh tears 6 times a day or whenever you feel dryness, for 6 weeks"
→ 1 row: REFRESH TEARS, 6 weeks, 6 times, with all 6 timing slots filled

**VALIDATION:**
✅ All timings between 7.00am and 10.00pm
✅ Tapering schedules have separate consecutive rows
✅ Date ranges are correct (end = start + duration - 1)
✅ Eye specified for every medication
✅ Time format: "7.00am" not "7:00 AM"
✅ Date format: "dd/mm/yy"

Return ONLY the JSON object. No markdown, no explanations, no additional text.

Begin extraction now.
"""

# ============================================================================
# SCHEMA DEFINITION
# ============================================================================

OPHTHAL_POSTOP_RX_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Student Details
        "patientDetails": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "name": types.Schema(type=types.Type.STRING, description="Student full name or empty string"),
                "mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
                "age": types.Schema(type=types.Type.STRING, description="Age with unit (e.g., '65 years') or empty string"),
                "gender": types.Schema(type=types.Type.STRING, description="Male/Female/Other or empty string"),
                "visitId": types.Schema(type=types.Type.STRING, description="Visit/episode ID or empty string"),
                "date": types.Schema(type=types.Type.STRING, description="Consultation date in dd/mm/yy format"),
            },
            description="Student identification details"
        ),

        # Surgery Details
        "surgeryDetails": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "procedure": types.Schema(type=types.Type.STRING, description="Surgery name (e.g., 'Cataract Surgery', 'LASIK')"),
                "eyeOperated": types.Schema(type=types.Type.STRING, description="LEFT EYE / RIGHT EYE / BOTH EYES"),
                "surgeon": types.Schema(type=types.Type.STRING, description="Surgeon name or empty string"),
                "surgeryDate": types.Schema(type=types.Type.STRING, description="Surgery date in dd/mm/yy format or empty string"),
            },
            description="Surgery procedure details"
        ),

        # Medications Array
        "medications": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "serialNumber": types.Schema(type=types.Type.STRING, description="Row number (e.g., '1', '2', '2a', '2b' for taper phases)"),
                    "medicationName": types.Schema(type=types.Type.STRING, description="UPPERCASE medication name with type (e.g., 'MOXIFLOXACIN EYEDROPS')"),
                    "eye": types.Schema(type=types.Type.STRING, description="LEFT EYE / RIGHT EYE / BOTH EYES"),
                    "durationText": types.Schema(type=types.Type.STRING, description="Duration description (e.g., '2 weeks', '5 days')"),
                    "dateRange": types.Schema(type=types.Type.STRING, description="Date range in format (dd/mm/yy - dd/mm/yy)"),
                    "frequency": types.Schema(type=types.Type.INTEGER, description="Times per day (1-8)"),
                    "timing1": types.Schema(type=types.Type.STRING, description="First timing (e.g., '7.00am') or empty string"),
                    "timing2": types.Schema(type=types.Type.STRING, description="Second timing or empty string"),
                    "timing3": types.Schema(type=types.Type.STRING, description="Third timing or empty string"),
                    "timing4": types.Schema(type=types.Type.STRING, description="Fourth timing or empty string"),
                    "timing5": types.Schema(type=types.Type.STRING, description="Fifth timing or empty string"),
                    "timing6": types.Schema(type=types.Type.STRING, description="Sixth timing or empty string"),
                    "specialInstructions": types.Schema(type=types.Type.STRING, description="Special instructions or empty string"),
                },
                description="Single medication row"
            ),
            description="Array of medication entries"
        ),

        # General Instructions
        "generalInstructions": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="General post-operative care instructions"
        ),

        # Follow-up
        "followUp": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "date": types.Schema(type=types.Type.STRING, description="Follow-up date in dd/mm/yy format or empty string"),
                "instructions": types.Schema(type=types.Type.STRING, description="Follow-up instructions or empty string"),
            },
            description="Follow-up appointment details"
        ),
    },
    description="Post-operative medication schedule"
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_default_timings(frequency: int) -> list:
    """
    Get default timing distribution based on frequency.
    Times are distributed between 7:00 AM and 10:00 PM.

    Args:
        frequency: Number of times per day (1-8)

    Returns:
        List of timing strings (e.g., ["7.00am", "12.00pm", "5.00pm", "10.00pm"])
    """
    timing_map = {
        1: ["9.30pm"],  # Default to night for once daily
        2: ["7.15am", "8.30pm"],
        3: ["7.00am", "12.30pm", "7.00pm"],
        4: ["7.00am", "12.00pm", "5.00pm", "10.00pm"],
        5: ["7.00am", "10.00am", "1.00pm", "4.00pm", "7.00pm"],
        6: ["7.00am", "10.00am", "1.00pm", "4.00pm", "7.00pm", "10.00pm"],
        7: ["7.00am", "9.00am", "11.00am", "1.00pm", "3.00pm", "5.00pm", "7.00pm"],
        8: ["7.00am", "9.00am", "11.00am", "1.00pm", "3.00pm", "5.00pm", "7.00pm", "9.00pm"],
    }
    return timing_map.get(frequency, ["7.00am"])


def calculate_end_date(start_date_str: str, duration_text: str) -> str:
    """
    Calculate end date based on start date and duration text.

    Args:
        start_date_str: Start date in dd/mm/yy format
        duration_text: Duration like "2 weeks", "5 days", "1 month"

    Returns:
        End date string in dd/mm/yy format
    """
    from datetime import datetime, timedelta
    import re

    # Parse start date
    start_date = datetime.strptime(start_date_str, "%d/%m/%y")

    # Parse duration
    duration_text = duration_text.lower()

    # Extract number and unit
    match = re.search(r'(\d+)\s*(day|week|month|year)s?', duration_text)
    if not match:
        return start_date_str  # Return start date if can't parse

    number = int(match.group(1))
    unit = match.group(2)

    # Calculate days to add
    if unit == 'day':
        days = number - 1
    elif unit == 'week':
        days = (number * 7) - 1
    elif unit == 'month':
        days = (number * 30) - 1
    elif unit == 'year':
        days = (number * 365) - 1
    else:
        days = 0

    end_date = start_date + timedelta(days=days)
    return end_date.strftime("%d/%m/%y")


def stagger_timings(base_time: str, num_drops: int, interval_minutes: int = 5) -> list:
    """
    Generate staggered timings for multiple drops.

    Args:
        base_time: Base time string (e.g., "7.00am")
        num_drops: Number of drops to stagger
        interval_minutes: Minutes between drops (default 5)

    Returns:
        List of staggered timing strings
    """
    from datetime import datetime, timedelta

    # Parse base time
    base_time = base_time.lower().replace('.', ':')

    # Handle am/pm
    if 'am' in base_time:
        time_str = base_time.replace('am', '')
        is_pm = False
    elif 'pm' in base_time:
        time_str = base_time.replace('pm', '')
        is_pm = True
    else:
        return [base_time]

    # Parse hours and minutes
    parts = time_str.strip().split(':')
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0

    # Convert to 24-hour for calculation
    if is_pm and hours != 12:
        hours += 12
    elif not is_pm and hours == 12:
        hours = 0

    base_dt = datetime(2000, 1, 1, hours, minutes)

    results = []
    for i in range(num_drops):
        current_dt = base_dt + timedelta(minutes=i * interval_minutes)
        hour = current_dt.hour
        minute = current_dt.minute

        # Convert back to 12-hour format
        if hour >= 12:
            suffix = 'pm'
            if hour > 12:
                hour -= 12
        else:
            suffix = 'am'
            if hour == 0:
                hour = 12

        results.append(f"{hour}.{minute:02d}{suffix}")

    return results


# ============================================================================
# CACHE KEY FOR CONTEXT CACHING
# ============================================================================

CACHE_KEY_OPHTHAL_POSTOP_RX = "ophthal_postop_rx"

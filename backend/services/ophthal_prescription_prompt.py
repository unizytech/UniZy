"""
Ophthalmology Prescription Prompt

System prompt, user prompt, and schema for extracting structured prescription
data from voice transcripts for general ophthalmology consultations.

This is different from post-operative prescriptions - it handles:
- Oral medications (capsules, tablets)
- Eye drops with frequency
- Ongoing/continuing medications
- Long-term prescriptions (months duration)
- Anti-glaucoma medications
- Lubricants and supplements

Author: System
Date: 2025-12-02
"""

from google.genai import types
from datetime import datetime

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

OPHTHAL_PRESCRIPTION_SYSTEM_PROMPT = """
You are a specialized ophthalmology prescription extraction AI. Your role is to extract structured prescription data from voice transcripts of doctor-patient consultations.

**YOUR ROLE:**
Extract complete prescription information from voice transcripts and return them in a standardized JSON format suitable for generating patient prescription forms.

**CORE CAPABILITIES:**
- Process multilingual medical conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada)
- Identify oral medications (capsules, tablets, syrups)
- Identify topical medications (eye drops, eye ointments, gels)
- Recognize frequency instructions (e.g., "4 times a day", "at night", "thrice daily")
- Handle long-term prescriptions (months, ongoing, lifelong)
- Identify continuing medications from previous prescriptions
- Recognize anti-glaucoma medication regimens

---

## CRITICAL RULES

1. ❌ NEVER fabricate medication names, dosages, or instructions not mentioned
2. ✅ Extract EXACT medication names as spoken (brand names or generic)
3. ✅ Identify medication type: CAPSULE, TABLET, EYE DROP, EYE OINTMENT, GEL, SYRUP
4. ✅ Specify eye: "LEFT EYE", "RIGHT EYE", "BOTH EYES" for topical medications
5. ✅ Extract frequency: number of times per day or specific timing
6. ✅ Extract duration: days, weeks, months, or "ongoing"/"continue"
7. ✅ Capture special instructions: "after food", "before sleep", "with meals"
8. ✅ Identify continuing medications from previous visits

---

## MEDICATION TYPES

### Oral Medications
| Type | Format | Examples |
|------|--------|----------|
| CAPSULE | Cap. [Name] | Cap. Ogareds, Cap. Omega-3 |
| TABLET | Tab. [Name] | Tab. Acetazolamide, Tab. Vitamin C |
| SYRUP | Syr. [Name] | Syr. Multivitamin |

### Topical Medications (Eye)
| Type | Format | Examples |
|------|--------|----------|
| EYE DROP | [Name] e/d | Latanoprost e/d, Refresh tears, Timolol e/d |
| EYE OINTMENT | [Name] e/o | Lacrilube e/o, Gentamicin e/o |
| GEL | [Name] gel | Carbomer gel, Genteal gel |

---

## FREQUENCY INTERPRETATION

### Standard Frequencies
| Spoken | Interpretation |
|--------|----------------|
| "Once a day" / "OD" / "1x" | 1 time per day |
| "Twice a day" / "BD" / "2x" | 2 times per day |
| "Thrice daily" / "TDS" / "3x" | 3 times per day |
| "Four times" / "QID" / "4x" | 4 times per day |
| "Six times" / "6x" | 6 times per day |
| "At night" / "HS" / "bedtime" | Once at night |
| "In the morning" | Once in morning |
| "After food" / "PC" | After meals |
| "Before food" / "AC" | Before meals |
| "As needed" / "PRN" / "SOS" | When required |

### Timing-Specific Instructions
| Instruction | Meaning |
|-------------|---------|
| "1x at night" | Once daily at bedtime |
| "3x" | Three times a day |
| "After food" | Take/apply after eating |
| "Before sleep" | Apply at bedtime |

---

## DURATION HANDLING

### Duration Keywords
| Spoken | Duration Value |
|--------|----------------|
| "for X days" | "X days" |
| "for X weeks" | "X weeks" |
| "for X months" | "X months" |
| "for 6 months" | "6 months" |
| "long term" / "lifelong" | "Ongoing" |
| "continue" / "継続" | "Continue" (from previous) |
| "until next visit" | "Until follow-up" |
| No duration mentioned | "As directed" |

---

## CONTINUING MEDICATIONS

When doctor says "continue [medication]" or mentions ongoing medications:
- Set `isContinuing: true`
- Set duration to "Continue" or "Ongoing"
- These are medications from previous prescriptions that should be maintained

**Example:**
Doctor: "Continue Latanoprost at night, Dorzox three times, and Brimonidine three times"

Output: 3 medications with `isContinuing: true`

---

## COMMON OPHTHALMOLOGY MEDICATIONS

### Anti-Glaucoma Drops (Usually Long-term/Ongoing)
| Generic | Brand Names | Typical Regimen |
|---------|-------------|-----------------|
| Latanoprost | Xalatan, Latoprost, 9PM | Once at night |
| Timolol | Iotim, Glucomol | Twice daily |
| Brimonidine | Alphagan, Brimosun | 2-3 times daily |
| Dorzolamide | Trusopt, Dorzox | 2-3 times daily |
| Brinzolamide | Azopt | 2-3 times daily |
| Travoprost | Travatan | Once at night |
| Bimatoprost | Lumigan | Once at night |

### Combination Anti-Glaucoma
| Combination | Brand Names |
|-------------|-------------|
| Dorzolamide + Timolol | Dorzox-T, Cosopt |
| Brimonidine + Timolol | Combigan |
| Latanoprost + Timolol | Xalacom |

### Lubricants / Artificial Tears
| Generic | Brand Names | Typical Regimen |
|---------|-------------|-----------------|
| Carboxymethylcellulose | Refresh Tears, Tears Plus | 4-6 times or PRN |
| Hydroxypropyl methylcellulose | Genteal, Moisol | 4-6 times or PRN |
| Polyethylene glycol | Systane | 4-6 times or PRN |
| Carbomer gel | Viscotears, Genteal Gel | Once at night |

### Oral Supplements (Ophthalmology)
| Generic | Brand Names | Typical Regimen |
|---------|-------------|-----------------|
| Omega-3 fatty acids | Ogareds, I-Caps, Ocuvite | Once daily after food |
| Lutein + Zeaxanthin | Ocupower, Lutenol | Once daily |
| Bilberry extract | Bilberry Plus | Once daily |
| Vitamin A | A-Vit | Once daily |

### Oral Medications
| Generic | Brand Names | Use |
|---------|-------------|-----|
| Acetazolamide | Diamox | Reduce IOP (glaucoma) |
| Glycerol | Glycerol oral | Acute IOP reduction |

---

## EYE SPECIFICATION

| Transcript Clue | Eye Value |
|-----------------|-----------|
| "left eye", "LE", "OS" | LEFT EYE |
| "right eye", "RE", "OD" | RIGHT EYE |
| "both eyes", "OU", "bilateral" | BOTH EYES |
| No specification for drops | BOTH EYES (default) |
| Oral medications | N/A (not applicable) |

---

## OUTPUT FORMAT

Generate a structured JSON with:
1. Patient details (name, age, gender, MR number, NIN, address, visit ID, date)
2. Array of prescription items, each containing:
   - Serial number
   - Medication name with type prefix (e.g., "Cap. Ogareds", "Refresh tears e/d")
   - Medication type (CAPSULE, TABLET, EYE DROP, etc.)
   - Eye specification (for topical only)
   - Dosage/quantity per application
   - Frequency (times per day or specific instruction)
   - Duration
   - Special instructions
   - Whether it's a continuing medication
3. Additional notes/instructions
4. Doctor details
5. Follow-up information

---

## VALIDATION CHECKLIST

Before returning JSON, verify:
✅ All medications have correct type prefix (Cap., Tab., e/d, e/o, gel)
✅ Eye specification present for all topical medications
✅ Frequency is clear (number or specific timing)
✅ Duration is specified or marked as "As directed"
✅ Continuing medications are flagged with isContinuing: true
✅ No fabricated medications
✅ Oral medications have N/A for eye field
"""

# ============================================================================
# USER PROMPT
# ============================================================================

OPHTHAL_PRESCRIPTION_USER_PROMPT = """
Extract the prescription data from the voice transcript below and return structured JSON.

**CONSULTATION DATE:** {consultation_date}

**VOICE TRANSCRIPT:**
---
{transcript}
---

**REQUIRED JSON OUTPUT STRUCTURE:**
```json
{{
  "patientDetails": {{
    "name": "string - patient full name or empty string",
    "age": "string - age in format 'X Y M D' (years, months, days) or simple format",
    "gender": "string - Male/Female/Other or empty string",
    "mrNumber": "string - medical record number or empty string",
    "nin": "string - national identification number or empty string",
    "address": "string - patient address or empty string",
    "visitId": "string - visit/episode ID or empty string",
    "date": "string - consultation date"
  }},

  "prescriptionItems": [
    {{
      "serialNumber": "number - item number (1, 2, 3...)",
      "medicationName": "string - full medication name with prefix (e.g., 'Cap. Ogareds', 'Refresh tears')",
      "medicationType": "string - CAPSULE/TABLET/SYRUP/EYE_DROP/EYE_OINTMENT/GEL",
      "eye": "string - LEFT EYE/RIGHT EYE/BOTH EYES/N/A (N/A for oral meds)",
      "dosage": "string - quantity per dose (e.g., '1 capsule', '1 drop', '2 tablets')",
      "frequency": "string - times per day or specific timing (e.g., '4x a day', '1x at night', '3x')",
      "duration": "string - duration (e.g., '6 months', '2 weeks', 'Ongoing', 'Continue')",
      "specialInstructions": "string - additional instructions (e.g., 'after food', 'before sleep')",
      "isContinuing": "boolean - true if continuing from previous prescription"
    }}
  ],

  "continuingMedications": [
    {{
      "medicationName": "string - medication name",
      "eye": "string - LEFT EYE/RIGHT EYE/BOTH EYES",
      "frequency": "string - frequency",
      "notes": "string - any additional notes"
    }}
  ],

  "additionalNotes": "string - any other instructions or notes from doctor",

  "doctorDetails": {{
    "name": "string - doctor name or empty string",
    "signature": "string - empty (for physical signature)",
    "stamp": "string - empty (for physical stamp)"
  }},

  "followUp": {{
    "date": "string - follow-up date or empty string",
    "instructions": "string - follow-up instructions or empty string"
  }},

  "pharmacyNote": "string - note to pharmacy (e.g., 'If medications unavailable, please call')"
}}
```

**EXTRACTION INSTRUCTIONS:**

1. **Patient Details:**
   - Extract all available patient information
   - Age format can be "59 Y 8 M 29 D" (years, months, days) or simple "59 years"
   - NIN = National Identification Number (if mentioned)

2. **Prescription Items:**
   - Number items sequentially (1, 2, 3...)
   - Add type prefix to medication name:
     - Capsules: "Cap. [Name]"
     - Tablets: "Tab. [Name]"
     - Eye drops: "[Name]" (e/d notation in instructions)
     - Ointments: "[Name]" (e/o notation in instructions)

3. **Medication Type Values:**
   - CAPSULE - for oral capsules
   - TABLET - for oral tablets
   - SYRUP - for oral liquids
   - EYE_DROP - for eye drops
   - EYE_OINTMENT - for eye ointments
   - GEL - for eye gels

4. **Eye Specification:**
   - For topical medications: "LEFT EYE", "RIGHT EYE", or "BOTH EYES"
   - For oral medications: "N/A"
   - Default to "BOTH EYES" if not specified for eye drops

5. **Frequency Format:**
   - "1x at night" - once at night
   - "4x a day" - four times daily
   - "3x" - three times daily
   - "2x (morning and night)" - twice daily with timing
   - "As needed" - PRN/SOS medications

6. **Duration:**
   - Specify exact duration: "6 months", "2 weeks", "1 month"
   - For ongoing: "Ongoing" or "Continue"
   - If not mentioned: "As directed"

7. **Continuing Medications:**
   - When doctor says "continue [medication]..."
   - Extract into BOTH prescriptionItems (with isContinuing: true) AND continuingMedications array
   - Continuing meds are usually anti-glaucoma drops

8. **Special Instructions:**
   - "after food" - take after meals
   - "before sleep" - at bedtime
   - "with meals" - during meals
   - Empty string if no special instruction

**EXAMPLE SCENARIOS:**

Scenario 1: New prescription with oral supplement
"Give Ogareds capsule one at night after food for 6 months"
→ {{
    "medicationName": "Cap. Ogareds",
    "medicationType": "CAPSULE",
    "eye": "N/A",
    "dosage": "1 capsule",
    "frequency": "1x at night",
    "duration": "6 months",
    "specialInstructions": "after food",
    "isContinuing": false
  }}

Scenario 2: Eye drops for both eyes
"Refresh tears 4 times a day to both eyes for 6 months"
→ {{
    "medicationName": "Refresh tears",
    "medicationType": "EYE_DROP",
    "eye": "BOTH EYES",
    "dosage": "1 drop",
    "frequency": "4x a day",
    "duration": "6 months",
    "specialInstructions": "",
    "isContinuing": false
  }}

Scenario 3: Continuing anti-glaucoma medications
"Continue Latanoprost at night, Dorzox 3 times, Brimonidine 3 times - all to both eyes"
→ 3 items with isContinuing: true, duration: "Continue"

Scenario 4: Single eye prescription
"Apply Moxifloxacin drops to left eye 4 times daily for 1 week"
→ eye: "LEFT EYE", duration: "1 week"

**VALIDATION:**
✅ All medications have correct type (CAPSULE, TABLET, EYE_DROP, etc.)
✅ Eye specified for topical medications, N/A for oral
✅ Frequency is clear and consistent
✅ Continuing medications flagged appropriately
✅ Duration specified for all items

Return ONLY the JSON object. No markdown, no explanations, no additional text.

Begin extraction now.
"""

# ============================================================================
# SCHEMA DEFINITION
# ============================================================================

OPHTHAL_PRESCRIPTION_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Patient Details
        "patientDetails": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "name": types.Schema(type=types.Type.STRING, description="Patient full name or empty string"),
                "age": types.Schema(type=types.Type.STRING, description="Age (e.g., '59 Y 8 M 29 D' or '59 years')"),
                "gender": types.Schema(type=types.Type.STRING, description="Male/Female/Other or empty string"),
                "mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
                "nin": types.Schema(type=types.Type.STRING, description="National ID number or empty string"),
                "address": types.Schema(type=types.Type.STRING, description="Patient address or empty string"),
                "visitId": types.Schema(type=types.Type.STRING, description="Visit/episode ID or empty string"),
                "date": types.Schema(type=types.Type.STRING, description="Consultation date"),
            },
            description="Patient identification and demographics"
        ),

        # Prescription Items Array
        "prescriptionItems": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "serialNumber": types.Schema(type=types.Type.INTEGER, description="Item number (1, 2, 3...)"),
                    "medicationName": types.Schema(type=types.Type.STRING, description="Full medication name with prefix (e.g., 'Cap. Ogareds')"),
                    "medicationType": types.Schema(type=types.Type.STRING, description="CAPSULE/TABLET/SYRUP/EYE_DROP/EYE_OINTMENT/GEL"),
                    "eye": types.Schema(type=types.Type.STRING, description="LEFT EYE/RIGHT EYE/BOTH EYES/N/A"),
                    "dosage": types.Schema(type=types.Type.STRING, description="Quantity per dose (e.g., '1 capsule', '1 drop')"),
                    "frequency": types.Schema(type=types.Type.STRING, description="Times per day or timing (e.g., '4x a day', '1x at night')"),
                    "duration": types.Schema(type=types.Type.STRING, description="Duration (e.g., '6 months', 'Ongoing', 'Continue')"),
                    "specialInstructions": types.Schema(type=types.Type.STRING, description="Additional instructions or empty string"),
                    "isContinuing": types.Schema(type=types.Type.BOOLEAN, description="True if continuing from previous prescription"),
                },
                description="Single prescription item"
            ),
            description="Array of prescription items"
        ),

        # Continuing Medications (separate section for clarity)
        "continuingMedications": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "medicationName": types.Schema(type=types.Type.STRING, description="Medication name"),
                    "eye": types.Schema(type=types.Type.STRING, description="LEFT EYE/RIGHT EYE/BOTH EYES"),
                    "frequency": types.Schema(type=types.Type.STRING, description="Frequency"),
                    "notes": types.Schema(type=types.Type.STRING, description="Additional notes"),
                },
                description="Continuing medication from previous prescription"
            ),
            description="List of continuing medications"
        ),

        # Additional Notes
        "additionalNotes": types.Schema(
            type=types.Type.STRING,
            description="Any other instructions or notes from doctor"
        ),

        # Doctor Details
        "doctorDetails": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "name": types.Schema(type=types.Type.STRING, description="Doctor name or empty string"),
                "signature": types.Schema(type=types.Type.STRING, description="Empty (for physical signature)"),
                "stamp": types.Schema(type=types.Type.STRING, description="Empty (for physical stamp)"),
            },
            description="Doctor information"
        ),

        # Follow-up
        "followUp": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "date": types.Schema(type=types.Type.STRING, description="Follow-up date or empty string"),
                "instructions": types.Schema(type=types.Type.STRING, description="Follow-up instructions or empty string"),
            },
            description="Follow-up appointment details"
        ),

        # Pharmacy Note
        "pharmacyNote": types.Schema(
            type=types.Type.STRING,
            description="Note to pharmacy (e.g., 'If medications unavailable, please call')"
        ),
    },
    description="Ophthalmology prescription form data"
)


# ============================================================================
# CACHE KEY FOR CONTEXT CACHING
# ============================================================================

CACHE_KEY_OPHTHAL_PRESCRIPTION = "OPHTHAL_PRESCRIPTION"

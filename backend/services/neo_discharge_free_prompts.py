"""
NEO_DISCHARGE_FREE Prompts and Schema

NICU Discharge Free Text extraction — flat, free-text format (~21 fields).
Includes medications array with structured drug objects.

Output is a flat JSON object that maps directly to the Raster API endpoint:
  /store-nicu-discharge-free-text

No formatter or split extraction needed — single Gemini call with 21 fields.
"""

from google import genai
from google.genai import types

# ============================================================================
# SCHEMA: 21 flat fields for free-text NICU discharge
# ============================================================================

NEO_DISCHARGE_FREE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== PATIENT IDENTIFICATION (1 field) ==========
        "uhid": types.Schema(
            type=types.Type.STRING,
            description="Patient unique hospital ID (UHID) or empty string if not mentioned"
        ),

        # ========== SEEN BY (1 field) ==========
        "seenBy": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of doctor IDs who reviewed this record. Default to [7] if none mentioned."
        ),

        # ========== DISCHARGE STATUS FIELDS (6 fields) ==========
        "status": types.Schema(
            type=types.Type.STRING,
            description="Discharge status: Discharged, Absconded, LAMA, Transferred, or Expired. Empty string if not mentioned."
        ),
        "dischargeDate": types.Schema(
            type=types.Type.STRING,
            description="Date of discharge in YYYY-MM-DD format. Empty string if not mentioned."
        ),
        "dischargeTime": types.Schema(
            type=types.Type.INTEGER,
            description="Hour of discharge (1-12). 0 if not mentioned."
        ),
        "dischargeTimeMinutes": types.Schema(
            type=types.Type.INTEGER,
            description="Minutes of discharge (0-59). 0 if not mentioned."
        ),
        "dischargeTimeSession": types.Schema(
            type=types.Type.STRING,
            description="AM or PM. Empty string if not mentioned."
        ),
        "dolAtDischarge": types.Schema(
            type=types.Type.INTEGER,
            description="Day of life at discharge. 0 if not mentioned."
        ),

        # ========== MEASUREMENTS (5 fields) ==========
        "correctedGestationWeeks": types.Schema(
            type=types.Type.INTEGER,
            description="Corrected gestational age in weeks at discharge. 0 if not mentioned."
        ),
        "correctedGestationDays": types.Schema(
            type=types.Type.INTEGER,
            description="Corrected gestational age in days (0-6). 0 if not mentioned."
        ),
        "dischargeWeight": types.Schema(
            type=types.Type.NUMBER,
            description="Weight at discharge in kg (decimal). 0 if not mentioned."
        ),
        "dischargeOfc": types.Schema(
            type=types.Type.NUMBER,
            description="Head circumference at discharge in cm (decimal). 0 if not mentioned."
        ),
        "dischargeLength": types.Schema(
            type=types.Type.NUMBER,
            description="Length at discharge in cm (decimal). 0 if not mentioned."
        ),

        # ========== FREE-TEXT CLINICAL FIELDS (6 fields) ==========
        "immunization": types.Schema(
            type=types.Type.STRING,
            description="Immunization status: vaccines given (BCG, Hepatitis B, OPV, etc.), pending vaccines, next due dates. Empty string if not mentioned."
        ),
        "dischargeExamination": types.Schema(
            type=types.Type.STRING,
            description="Discharge physical examination findings: general appearance, vitals, systemic examination (CVS, RS, GI, CNS), skin, any residual issues. Empty string if not mentioned."
        ),
        "dischargeBloodInvestigations": types.Schema(
            type=types.Type.STRING,
            description="Recent blood investigations: CBC, CRP, cultures, metabolic parameters, specific tests as applicable. Empty string if not mentioned."
        ),
        "additionalInformation": types.Schema(
            type=types.Type.STRING,
            description="NICU course summary: reason for admission, major problems encountered, interventions required (ventilation, lines, blood products), complications, peak oxygen requirement, feeding progression. Empty string if not mentioned."
        ),
        "advice": types.Schema(
            type=types.Type.STRING,
            description="Discharge advice: home care instructions, feeding guidelines (type, frequency, volume), medication instructions, warning signs to watch for, when to seek medical help. Empty string if not mentioned."
        ),
        "planForFollowup": types.Schema(
            type=types.Type.STRING,
            description="Follow-up plan: required specialist appointments (pediatrician, ophthalmology for ROP screening, audiology for hearing assessment, neurology, cardiology, etc.). Empty string if not mentioned."
        ),
        "nextFollowupDetails": types.Schema(
            type=types.Type.STRING,
            description="Next scheduled follow-up: date, time, department/clinic, doctor name, tests to bring. Empty string if not mentioned."
        ),

        # ========== MEDICATIONS (1 field — array of objects) ==========
        "medications": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "drugName": types.Schema(
                        type=types.Type.STRING,
                        description="Drug/medication name"
                    ),
                    "genericName": types.Schema(
                        type=types.Type.STRING,
                        description="Generic/chemical name"
                    ),
                    "formulation": types.Schema(
                        type=types.Type.STRING,
                        description="Formulation (e.g., Syrup, Tablet, Drops, IM injection)"
                    ),
                    "dose": types.Schema(
                        type=types.Type.STRING,
                        description="Dose amount with unit (e.g., '5ml', '1mg')"
                    ),
                    "frequency": types.Schema(
                        type=types.Type.STRING,
                        description="Dosing frequency (e.g., 'Once daily', 'Twice daily', 'Every 8 hours')"
                    ),
                    "duration": types.Schema(
                        type=types.Type.STRING,
                        description="Duration of treatment (e.g., '30 days', 'Continue', 'Until follow-up')"
                    ),
                    "additionalInstruction": types.Schema(
                        type=types.Type.STRING,
                        description="Additional instructions (e.g., 'Give in the morning', 'Take with food')"
                    ),
                },
            ),
            description="Discharge medications array. Empty array if no medications mentioned."
        ),
    }
)

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

NEO_DISCHARGE_FREE_SYSTEM_PROMPT = """You are a specialized clinical data extraction AI for NICU discharge records.

**YOUR ROLE:**
Extract NICU discharge data from transcribed clinical notes and return structured JSON with FREE-TEXT clinical fields.

**CRITICAL RULES:**
1. NEVER fabricate clinical information or assume data not explicitly stated
2. Use empty string "" for text fields and 0 for numeric fields where no information is mentioned
3. If a value is corrected during dictation, use the LATEST/FINAL value
4. Capture clinical details VERBATIM as described by the clinician
5. Include ALL relevant details within each field
6. For medications, extract each drug as a separate object with all available details

**FIELD GUIDELINES:**

- **uhid**: Extract patient UHID if mentioned. Empty string if not.
- **seenBy**: Array of doctor IDs (integers). Default to [7] if none mentioned.
- **status**: Discharge status — Discharged/Absconded/LAMA/Transferred/Expired.
- **dischargeDate**: Date in YYYY-MM-DD format.
- **dischargeTime/dischargeTimeMinutes/dischargeTimeSession**: Time components (hour, minutes, AM/PM).
- **dolAtDischarge**: Day of life at discharge.
- **correctedGestationWeeks/correctedGestationDays**: Corrected GA at discharge.
- **dischargeWeight/dischargeOfc/dischargeLength**: Measurements at discharge.
- **immunization**: ALL vaccination details — given, pending, next due dates.
- **dischargeExamination**: Complete discharge exam — vitals, systemic exam.
- **dischargeBloodInvestigations**: Recent lab results.
- **additionalInformation**: NICU course summary — reason, interventions, complications.
- **advice**: Discharge advice — feeding, home care, warning signs.
- **planForFollowup**: Follow-up appointments and specialist referrals.
- **nextFollowupDetails**: Next appointment details.
- **medications**: Array of medication objects with drugName, genericName, formulation, dose, frequency, duration, additionalInstruction.

**CLINICAL ABBREVIATION AWARENESS:**
Recognize and correctly extract common NICU abbreviations:
- Conditions: RDS, BPD, NEC, PDA, ROP, NNJ, IVH, PPHN
- Labs: CBC, CRP, TSB, TSH, ABG
- Vaccines: BCG, OPV, DPT, Hib, PCV, Rota
- Treatments: CPAP, SIMV, HFOV, TPN, PRBC, FFP
- Others: BERA, OAE, PICC, UVC, UAC

**OUTPUT FORMAT:**
Return ONLY valid JSON matching the schema. No markdown, no explanations."""

# ============================================================================
# USER PROMPT
# ============================================================================

NEO_DISCHARGE_FREE_USER_PROMPT = """Extract NICU discharge data from this transcript into the free-text format:

---
{transcript}
---

**EXTRACTION INSTRUCTIONS:**

1. **uhid**: Patient hospital ID if stated. Empty string otherwise.
2. **seenBy**: Doctor IDs as integers array. Default to [7] if none mentioned.
3. **status**: Discharge status (Discharged/Absconded/LAMA/Transferred/Expired).
4. **dischargeDate**: Date in YYYY-MM-DD format. Empty string if not stated.
5. **dischargeTime**: Hour (1-12). 0 if not stated.
6. **dischargeTimeMinutes**: Minutes (0-59). 0 if not stated.
7. **dischargeTimeSession**: AM or PM. Empty string if not stated.
8. **dolAtDischarge**: Day of life (integer). 0 if not stated.
9. **correctedGestationWeeks**: Weeks (integer). 0 if not stated.
10. **correctedGestationDays**: Days 0-6 (integer). 0 if not stated.
11. **dischargeWeight**: Weight in kg (decimal). 0 if not stated.
12. **dischargeOfc**: Head circumference in cm (decimal). 0 if not stated.
13. **dischargeLength**: Length in cm (decimal). 0 if not stated.
14. **immunization**: Vaccination details as free text.
15. **dischargeExamination**: Discharge exam findings as free text.
16. **dischargeBloodInvestigations**: Lab results as free text.
17. **additionalInformation**: NICU course summary as free text.
18. **advice**: Discharge advice as free text.
19. **planForFollowup**: Follow-up plan as free text.
20. **nextFollowupDetails**: Next appointment details as free text.
21. **medications**: Array of medication objects. Each with: drugName, genericName, formulation, dose, frequency, duration, additionalInstruction.

**IMPORTANT:**
- Capture ALL clinical details within the appropriate field
- For medications, create a separate object for EACH drug mentioned
- If a topic is not discussed, use empty string "" for text, 0 for numbers, [] for arrays
{medicine_list_section}
{investigation_list_section}

Return ONLY the JSON object. No markdown, no explanations."""

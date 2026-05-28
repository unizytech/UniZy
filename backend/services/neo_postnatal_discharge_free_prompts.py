"""
NEO_POSTNATAL_DISCHARGE_FREE Prompts and Schema

Postnatal Discharge Free Text extraction — flat, free-text format (~15 fields).
For babies discharging from postnatal ward. Includes medications array.

Output is a flat JSON object that maps directly to the Raster API endpoint:
  /store-postnatal-discharge-free-text

No formatter or split extraction needed — single Gemini call with 15 fields.
"""

from google import genai
from google.genai import types

# ============================================================================
# SCHEMA: 15 flat fields for free-text postnatal discharge
# ============================================================================

NEO_POSTNATAL_DISCHARGE_FREE_SCHEMA = types.Schema(
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

        # ========== DISCHARGE STATUS (2 fields) ==========
        "status": types.Schema(
            type=types.Type.STRING,
            description="Discharge status: Discharged, LAMA, or Referred. Empty string if not mentioned."
        ),
        "dischargeDate": types.Schema(
            type=types.Type.STRING,
            description="Date of discharge in YYYY-MM-DD format. Empty string if not mentioned."
        ),

        # ========== MEASUREMENTS (5 fields) ==========
        "dolAtDischarge": types.Schema(
            type=types.Type.INTEGER,
            description="Day of life at discharge. 0 if not mentioned."
        ),
        "correctedGestationWeeks": types.Schema(
            type=types.Type.INTEGER,
            description="Corrected gestational age in weeks. 0 if not mentioned."
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

        # ========== FREE-TEXT CLINICAL FIELDS (4 fields) ==========
        "immunization": types.Schema(
            type=types.Type.STRING,
            description="Immunization status and schedule: vaccines given, pending, next due. Empty string if not mentioned."
        ),
        "diagnosis": types.Schema(
            type=types.Type.STRING,
            description="Discharge diagnosis (if any issues identified). Empty string if not mentioned."
        ),
        "dischargeExamination": types.Schema(
            type=types.Type.STRING,
            description="Final examination findings before discharge: general, vitals, systemic exam, skin. Empty string if not mentioned."
        ),
        "postnatalCourse": types.Schema(
            type=types.Type.STRING,
            description="Postnatal course summary: birth details, any issues during stay, feeding establishment, maternal health, bonding. Empty string if not mentioned."
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
                        description="Formulation (e.g., Oral drops, Tablet, IM injection)"
                    ),
                    "dose": types.Schema(
                        type=types.Type.STRING,
                        description="Dose amount with unit (e.g., '1 drop', '400 IU')"
                    ),
                    "frequency": types.Schema(
                        type=types.Type.STRING,
                        description="Dosing frequency (e.g., 'Once daily', 'Single dose')"
                    ),
                    "duration": types.Schema(
                        type=types.Type.STRING,
                        description="Duration of treatment (e.g., 'Continue until 1 year', 'Given at birth')"
                    ),
                    "additionalInstruction": types.Schema(
                        type=types.Type.STRING,
                        description="Additional instructions (e.g., 'Start from Day 7', 'Give directly into mouth')"
                    ),
                },
            ),
            description="Discharge medications array. Usually minimal for healthy newborns. Empty array if no medications mentioned."
        ),
    }
)

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

NEO_POSTNATAL_DISCHARGE_FREE_SYSTEM_PROMPT = """You are a specialized clinical data extraction AI for postnatal discharge records.

**YOUR ROLE:**
Extract postnatal discharge data from transcribed clinical notes and return structured JSON with FREE-TEXT clinical fields.

This template covers babies discharging from postnatal ward (not NICU). Typically healthier babies with shorter stays.

**CRITICAL RULES:**
1. NEVER fabricate clinical information or assume data not explicitly stated
2. Use empty string "" for text fields and 0 for numeric fields where no information is mentioned
3. If a value is corrected during dictation, use the LATEST/FINAL value
4. Capture clinical details VERBATIM as described by the clinician
5. For medications, extract each drug as a separate object with all available details

**FIELD GUIDELINES:**

- **uhid**: Extract patient UHID if mentioned. Empty string if not.
- **seenBy**: Array of doctor IDs (integers). Default to [7] if none mentioned.
- **status**: Discharge status — Discharged/LAMA/Referred.
- **dischargeDate**: Date in YYYY-MM-DD format.
- **dolAtDischarge**: Day of life at discharge (integer).
- **correctedGestationWeeks/correctedGestationDays**: Corrected GA at discharge.
- **dischargeWeight/dischargeOfc/dischargeLength**: Measurements at discharge.
- **immunization**: ALL vaccination details — given, pending, next due dates.
- **diagnosis**: Discharge diagnosis — typically "Healthy term AGA baby" or specific issues.
- **dischargeExamination**: Final exam — vitals, systemic exam, any residual issues.
- **postnatalCourse**: Complete stay summary — birth details, hospital stay, feeding, maternal health.
- **medications**: Array of medication objects (usually minimal — Vitamin K, Vitamin D3).

**CLINICAL ABBREVIATION AWARENESS:**
Recognize common neonatal abbreviations:
- NNJ (neonatal jaundice), TSB (total serum bilirubin), AGA (appropriate for gestational age)
- NVD (normal vaginal delivery), LSCS (lower segment caesarean section)
- BCG, OPV, DPT, Hib, PCV (vaccines)
- SpO2, HR, RR, CVS, RS, CNS, OFC

**OUTPUT FORMAT:**
Return ONLY valid JSON matching the schema. No markdown, no explanations."""

# ============================================================================
# USER PROMPT
# ============================================================================

NEO_POSTNATAL_DISCHARGE_FREE_USER_PROMPT = """Extract postnatal discharge data from this transcript into the free-text format:

---
{transcript}
---

**EXTRACTION INSTRUCTIONS:**

1. **uhid**: Patient hospital ID if stated. Empty string otherwise.
2. **seenBy**: Doctor IDs as integers array. Default to [7] if none mentioned.
3. **status**: Discharge status (Discharged/LAMA/Referred). Empty string if not stated.
4. **dischargeDate**: Date in YYYY-MM-DD format. Empty string if not stated.
5. **dolAtDischarge**: Day of life (integer). 0 if not stated.
6. **correctedGestationWeeks**: Weeks (integer). 0 if not stated.
7. **correctedGestationDays**: Days 0-6 (integer). 0 if not stated.
8. **dischargeWeight**: Weight in kg (decimal). 0 if not stated.
9. **dischargeOfc**: Head circumference in cm (decimal). 0 if not stated.
10. **dischargeLength**: Length in cm (decimal). 0 if not stated.
11. **immunization**: Vaccination details as free text.
12. **diagnosis**: Discharge diagnosis as free text.
13. **dischargeExamination**: Final exam findings as free text.
14. **postnatalCourse**: Complete stay summary as free text.
15. **medications**: Array of medication objects. Each with: drugName, genericName, formulation, dose, frequency, duration, additionalInstruction.

**IMPORTANT:**
- Capture ALL clinical details within the appropriate field
- For medications, create a separate object for EACH drug mentioned
- If a topic is not discussed, use empty string "" for text, 0 for numbers, [] for arrays
{medicine_list_section}
{investigation_list_section}

Return ONLY the JSON object. No markdown, no explanations."""

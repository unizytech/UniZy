"""
NEO_POSTNATAL_DAY_FREE Prompts and Schema

Postnatal Daycare Free Text extraction — flat, free-text format (~9 fields).
Lightweight template for mother-baby daycare records.

Output is a flat JSON object that maps directly to the Raster API endpoint:
  /store-postnatal-daycare-free-text

No formatter or split extraction needed — single Gemini call with 9 fields.
"""

from google import genai
from google.genai import types

# ============================================================================
# SCHEMA: 9 flat fields for free-text postnatal daycare
# ============================================================================

NEO_POSTNATAL_DAY_FREE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== PATIENT IDENTIFICATION (1 field) ==========
        "uhid": types.Schema(
            type=types.Type.STRING,
            description="Patient unique hospital ID (UHID) or empty string if not mentioned"
        ),

        # ========== DATE/TIME (3 fields) ==========
        "dateOfEntry": types.Schema(
            type=types.Type.STRING,
            description="Date of daycare entry in YYYY-MM-DD format. Empty string if not mentioned."
        ),
        "timeOfEntry": types.Schema(
            type=types.Type.STRING,
            description="Time of entry in HH:mm:ss format (24-hour). Empty string if not mentioned."
        ),
        "dol": types.Schema(
            type=types.Type.INTEGER,
            description="Day of life. 0 if not mentioned."
        ),

        # ========== SEEN BY (1 field) ==========
        "seenBy": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of doctor IDs who reviewed the patient. Default to [7] if none mentioned."
        ),

        # ========== FREE-TEXT CLINICAL FIELDS (4 fields) ==========
        "background": types.Schema(
            type=types.Type.STRING,
            description="Background/reason for daycare: birth details, any perinatal issues, current concerns. Empty string if not mentioned."
        ),
        "diagnosis": types.Schema(
            type=types.Type.STRING,
            description="Current diagnosis or identified issues. Empty string if not mentioned."
        ),
        "notes": types.Schema(
            type=types.Type.STRING,
            description="Clinical notes: assessment findings, vital signs, examination details, observations, baby's feeding and behavior, mother's concerns. Empty string if not mentioned."
        ),
        "plan": types.Schema(
            type=types.Type.STRING,
            description="Management plan: interventions, advice given, follow-up plan, discharge planning. Empty string if not mentioned."
        ),
    }
)

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

NEO_POSTNATAL_DAY_FREE_SYSTEM_PROMPT = """You are a specialized clinical data extraction AI for postnatal daycare records.

**YOUR ROLE:**
Extract postnatal daycare data from transcribed clinical notes and return structured JSON with FREE-TEXT clinical fields.

This is a lightweight template (~9 fields) for mother-baby daycare records (postnatal ward reviews).

**CRITICAL RULES:**
1. NEVER fabricate clinical information or assume data not explicitly stated
2. Use empty string "" for text fields and 0 for numeric fields where no information is mentioned
3. If a value is corrected during dictation, use the LATEST/FINAL value
4. Capture clinical details VERBATIM as described by the clinician
5. Include ALL relevant details within each field

**FIELD GUIDELINES:**

- **uhid**: Extract patient UHID if mentioned. Empty string if not.
- **dateOfEntry**: Date in YYYY-MM-DD format.
- **timeOfEntry**: Time in HH:mm:ss 24-hour format (e.g., "14:30:00").
- **dol**: Day of life (integer).
- **seenBy**: Array of doctor IDs (integers). Default to [7] if none mentioned.
- **background**: Birth details, perinatal issues, reason for review.
- **diagnosis**: Current diagnosis or issues identified.
- **notes**: ALL clinical assessment — vitals, examination, feeding, behavior, mother's concerns, investigations.
- **plan**: Complete management plan — interventions, advice, monitoring, follow-up, discharge criteria.

**CLINICAL ABBREVIATION AWARENESS:**
Recognize common neonatal abbreviations:
- NNJ (neonatal jaundice), TSB (total serum bilirubin), EBM (expressed breast milk)
- NVD (normal vaginal delivery), LSCS (lower segment caesarean section)
- SpO2, HR, RR, CVS, RS, CNS, GI

**OUTPUT FORMAT:**
Return ONLY valid JSON matching the schema. No markdown, no explanations."""

# ============================================================================
# USER PROMPT
# ============================================================================

NEO_POSTNATAL_DAY_FREE_USER_PROMPT = """Extract postnatal daycare data from this transcript into the free-text format:

---
{transcript}
---

**EXTRACTION INSTRUCTIONS:**

1. **uhid**: Patient hospital ID if stated. Empty string otherwise.
2. **dateOfEntry**: Date in YYYY-MM-DD format. Empty string if not stated.
3. **timeOfEntry**: Time in HH:mm:ss format (24-hour). Empty string if not stated.
4. **dol**: Day of life (integer). 0 if not stated.
5. **seenBy**: Doctor IDs as integers array. Default to [7] if none mentioned.
6. **background**: Background/reason for daycare visit as free text.
7. **diagnosis**: Current diagnosis as free text.
8. **notes**: Clinical assessment and observations as free text.
9. **plan**: Management plan as free text.

**IMPORTANT:**
- Capture ALL clinical details within the appropriate field
- If a topic is not discussed, use empty string "" for text and 0 for numbers
{medicine_list_section}
{investigation_list_section}

Return ONLY the JSON object. No markdown, no explanations."""

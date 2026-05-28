"""
NEO_DAILY_FREE Prompts and Schema

Simplified neonatal daily progress note extraction — flat, free-text format (~17 fields).
This is a lighter alternative to NEO_DAILY (~125 structured fields with two-part split extraction).

Output is a flat JSON object that maps directly to the Raster API endpoint:
  /store-doctor-daily-entry-transcribed-data

No formatter or split extraction needed — single Gemini call with 17 fields.
"""

from google import genai
from google.genai import types

# ============================================================================
# SCHEMA: 17 flat fields for free-text neonatal daily progress notes
# ============================================================================

NEO_DAILY_FREE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== PATIENT IDENTIFICATION (1 field) ==========
        "uhid": types.Schema(
            type=types.Type.STRING,
            description="Patient unique hospital ID (UHID) or empty string if not mentioned"
        ),

        # ========== DATE/TIME (4 fields) ==========
        "entryDate": types.Schema(
            type=types.Type.STRING,
            description="Entry date in YYYY-MM-DD format. Extract from transcript or use empty string."
        ),
        "dayTime": types.Schema(
            type=types.Type.STRING,
            description="Hour of entry in 01-12 format (e.g., '10', '02'). Extract from transcript or use empty string."
        ),
        "dayTimeMins": types.Schema(
            type=types.Type.STRING,
            description="Minutes of entry in 00-59 format (e.g., '15', '00'). Extract from transcript or use empty string."
        ),
        "dayTimeAm": types.Schema(
            type=types.Type.STRING,
            description="AM or PM. Extract from transcript or use empty string."
        ),

        # ========== SEEN BY (1 field) ==========
        "seenBy": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of doctor IDs who reviewed the patient. Extract numeric IDs if mentioned (e.g., doctor 1, doctor 2). If doctor names are mentioned, extract the names as strings. If NO doctor IDs or names are mentioned at all, return [7] as default."
        ),

        # ========== CLINICAL FREE-TEXT FIELDS (10 fields) ==========
        "currentProblems": types.Schema(
            type=types.Type.STRING,
            description="Current active problems. Capture ALL current clinical issues mentioned: diagnoses, symptoms, ongoing concerns. Use free text exactly as described by the clinician. Empty string if not mentioned."
        ),
        "previousProblems": types.Schema(
            type=types.Type.STRING,
            description="Previous or resolved problems. Capture any resolved issues, improving conditions, or historical context mentioned. Empty string if not mentioned."
        ),
        "respiratorySystem": types.Schema(
            type=types.Type.STRING,
            description="Respiratory system findings. Include ALL respiratory details: ventilation mode/settings (CPAP, SIMV, HFOV, room air), FiO2, PEEP, PIP, flow rates, SpO2, air entry, breath sounds, retractions, blood gas values (pH, pCO2, pO2, HCO3, BE, lactate), chest X-ray findings, surfactant doses, ET tube details. Capture everything respiratory-related as free text. Empty string if not mentioned."
        ),
        "cardiovascularSystem": types.Schema(
            type=types.Type.STRING,
            description="Cardiovascular system findings. Include ALL CVS details: heart rate, blood pressure, heart sounds (S1/S2), murmurs, capillary refill time, perfusion, peripheral pulses, central/peripheral temperature, echo findings, PDA status and treatment, PAH status, inotrope details (drug names, doses). Capture everything cardiovascular-related as free text. Empty string if not mentioned."
        ),
        "giSystem": types.Schema(
            type=types.Type.STRING,
            description="Gastrointestinal system findings. Include ALL GI details: abdomen examination (soft/distended), bowel sounds, feeding type and details (breastfeeding/EBM/formula/NPO), feed volume and frequency, tolerance, aspirate details, stools, liver/spleen palpation, umbilicus status, NNJ/jaundice (TSB values, phototherapy), TPN details, IV fluids and rates, nutritional supplements. Capture everything GI-related as free text. Empty string if not mentioned."
        ),
        "cns": types.Schema(
            type=types.Type.STRING,
            description="Central nervous system findings. Include ALL CNS details: activity level, tone, cry, fontanelle, reflexes, seizures (type, treatment), pupils, head circumference, neurosonogram/MRI/CT findings, EEG/CFM results, sedation/paralysis drugs. Capture everything neurological as free text. Empty string if not mentioned."
        ),
        "sepsis": types.Schema(
            type=types.Type.STRING,
            description="Sepsis and infection details. Include ALL sepsis details: clinical stability, CRP values, blood culture results, organisms isolated, antibiotic names with doses and routes and duration/day, lumbar puncture results, procalcitonin, WBC counts, sepsis screening results. Capture everything infection-related as free text. Empty string if not mentioned."
        ),
        "fluidsElectrolytes": types.Schema(
            type=types.Type.STRING,
            description="Fluids, electrolytes, and renal details. Include ALL details: IV fluid type and rate (TFI ml/kg/day), GIR, urine output, weight (current, previous, birth weight), serum electrolytes (Na, K, Ca, Mg), blood sugar, renal function, fluid balance, TPN composition (protein, fat, carbs, calories). Capture everything fluid/electrolyte/renal-related as free text. Empty string if not mentioned."
        ),
        "invasiveLines": types.Schema(
            type=types.Type.STRING,
            description="Invasive lines and access details. Include ALL line details: PVC (site, day, complications), PICC (site, day, tip position), UVC (position, day), UAC (position, day), peripheral arterial lines, central lines. Include site status (healthy, phlebitis, etc.) and any line changes. Capture everything line-related as free text. Empty string if not mentioned."
        ),
        "managementPlan": types.Schema(
            type=types.Type.STRING,
            description="Management plan and next steps. Include ALL planned actions: ventilation changes, medication changes, investigation plans, feeding advancement plans, monitoring instructions, consult requests, discharge planning. Capture the complete plan as free text. Empty string if not mentioned."
        ),
        "notes": types.Schema(
            type=types.Type.STRING,
            description="Additional notes. Any other clinical information not fitting the above categories: parent counselling, ROP screening status/findings, skin findings, immunizations, metabolic screening, transfusion details (blood products, volumes), miscellaneous observations. Empty string if not mentioned."
        ),
    }
)

# ============================================================================
# SYSTEM PROMPT - Reuses core clinical extraction rules from NEO_DAILY
# ============================================================================

NEO_DAILY_FREE_SYSTEM_PROMPT = """You are a specialized clinical data extraction AI for neonatal daily progress notes.

**YOUR ROLE:**
Extract daily neonatal monitoring parameters from transcribed clinical notes and return structured JSON with FREE-TEXT clinical fields.

Unlike the structured NEO_DAILY format with ~125 individual fields, this format uses ~17 fields where most clinical data is captured as descriptive free text within system-specific fields.

**CRITICAL RULES:**
1. NEVER fabricate clinical information or assume data not explicitly stated
2. Use empty string "" for fields where no information is mentioned in the transcript
3. If a value is corrected during dictation, use the LATEST/FINAL value
4. Capture clinical details VERBATIM as described by the clinician — do not paraphrase or summarize excessively
5. Include ALL relevant details within each system field — do not omit values, measurements, or drug details
6. For numeric values (vitals, lab results, drug doses), include the exact numbers with units as stated

**FIELD GUIDELINES:**

- **uhid**: Extract patient UHID/hospital ID if mentioned. Empty string if not.
- **entryDate**: Date in YYYY-MM-DD format. Empty string if not mentioned.
- **dayTime/dayTimeMins/dayTimeAm**: Extract time components (hour, minutes, AM/PM). Empty strings if not mentioned.
- **seenBy**: Array of doctor IDs (integers) or doctor names (strings). If specific doctor IDs are mentioned (e.g., "seen by doctor 7"), return those IDs. If doctor names are mentioned (e.g., "seen by Dr Ramakrishnan"), return the names as strings. If NO doctor IDs or names are mentioned at all, default to [7].
- **currentProblems**: ALL active clinical problems — diagnoses, symptoms, ongoing issues.
- **previousProblems**: Resolved or improving issues from prior days.
- **respiratorySystem**: Everything respiratory — ventilation mode/settings, FiO2, SpO2, blood gas, breath sounds, chest findings, surfactant.
- **cardiovascularSystem**: Everything CVS — heart rate, BP, heart sounds, perfusion, echo, PDA, PAH, inotropes with doses.
- **giSystem**: Everything GI — abdomen exam, feeds (type/volume/frequency), tolerance, jaundice/TSB, TPN, IV fluids, nutrition.
- **cns**: Everything neurological — tone, activity, seizures, fontanelle, imaging, sedation.
- **sepsis**: Everything infection — CRP, cultures, antibiotics (name/dose/route/duration), organisms.
- **fluidsElectrolytes**: Everything fluid/renal — IV fluids, electrolytes, weight, urine output, GIR, fluid balance.
- **invasiveLines**: All vascular access — PVC, PICC, UVC, UAC, sites, days, complications.
- **managementPlan**: The complete plan — what to continue, change, start, stop, investigate, monitor.
- **notes**: Everything else — parent counselling, ROP, skin, transfusions, immunizations, miscellaneous.

**CLINICAL ABBREVIATION AWARENESS:**
Recognize and correctly extract common NICU abbreviations:
- Ventilation: CPAP, SIMV, HFOV, PSV, PRVC, CMV, NIV
- Medications: Amp (Ampicillin), Genta (Gentamicin), Vanco (Vancomycin), Mero (Meropenem)
- Labs: CRP, TSB, ABG, RBS, GIR, TFI
- Lines: PVC, PICC, UVC, UAC, PAC
- Others: EBM, NPO, TPN, FFP, PRBC, ROP, NEC, PDA, PAH

**OUTPUT FORMAT:**
Return ONLY valid JSON matching the schema. No markdown, no explanations."""

# ============================================================================
# USER PROMPT
# ============================================================================

NEO_DAILY_FREE_USER_PROMPT = """Extract neonatal daily progress note data from this transcript into the free-text format:

---
{transcript}
---

**EXTRACTION INSTRUCTIONS:**

1. **uhid**: Patient hospital ID if stated. Empty string otherwise.
2. **entryDate**: Date in YYYY-MM-DD format. Empty string if not stated.
3. **dayTime**: Hour (01-12). Empty string if not stated.
4. **dayTimeMins**: Minutes (00-59). Empty string if not stated.
5. **dayTimeAm**: AM or PM. Empty string if not stated.
6. **seenBy**: Doctor IDs as integers array. Default to [1] if none mentioned.
7. **currentProblems**: All current active problems as free text.
8. **previousProblems**: All previous/resolved problems as free text.
9. **respiratorySystem**: All respiratory findings, ventilation details, blood gas values as free text.
10. **cardiovascularSystem**: All CVS findings, hemodynamics, echo, PDA/PAH as free text.
11. **giSystem**: All GI findings, feeds, nutrition, jaundice as free text.
12. **cns**: All CNS findings, tone, seizures, imaging as free text.
13. **sepsis**: All sepsis details, antibiotics with doses, cultures as free text.
14. **fluidsElectrolytes**: All fluid, electrolyte, weight, renal details as free text.
15. **invasiveLines**: All line details — type, site, day, status as free text.
16. **managementPlan**: Complete management plan as free text.
17. **notes**: Any additional information not covered above as free text.

**IMPORTANT:**
- Capture ALL clinical details within the appropriate field — include exact numbers, drug doses, and measurements
- If a system is not discussed in the transcript, use empty string ""
- For seenBy: only default to [1] if absolutely NO doctor IDs are mentioned anywhere in the transcript
{medicine_list_section}
{investigation_list_section}

Return ONLY the JSON object. No markdown, no explanations."""

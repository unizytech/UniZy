"""
NEO_PROFORMA_FREE Prompts and Schema

Neonatal Proforma Free Text extraction — flat, free-text format (~21 fields).
This is a lighter alternative to NEO_PROFORMA (~185 structured fields with two-part split extraction).

Output is a flat JSON object that maps directly to the Raster API endpoint:
  /store-neonatal-proforma-free-text

No formatter or split extraction needed — single Gemini call with 21 fields.
"""

from google import genai
from google.genai import types

# ============================================================================
# SCHEMA: 21 flat fields for free-text neonatal proforma
# ============================================================================

NEO_PROFORMA_FREE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== PATIENT IDENTIFICATION (1 field) ==========
        "uhid": types.Schema(
            type=types.Type.STRING,
            description="Patient unique hospital ID (UHID) or empty string if not mentioned"
        ),

        # ========== DATE (1 field) ==========
        "entryDate": types.Schema(
            type=types.Type.STRING,
            description="Entry date in YYYY-MM-DD format. Extract from transcript or use empty string."
        ),

        # ========== SEEN BY (1 field) ==========
        "seenBy": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of doctor IDs who reviewed this record. If doctor names are mentioned, extract the names as strings. If NO doctor IDs or names are mentioned at all, return [7] as default."
        ),

        # ========== FREE-TEXT CLINICAL FIELDS (13 fields) ==========
        "obstetricHistory": types.Schema(
            type=types.Type.STRING,
            description="Maternal obstetric history including gravida, para, live births, abortions, blood group, antenatal care, complications. Empty string if not mentioned."
        ),
        "pregnancy": types.Schema(
            type=types.Type.STRING,
            description="Pregnancy details including consanguinity, LMP, EDD (by USG and dates), booking status, supervision, antenatal steroids, MgSO4, thyroid status, HIV, Hepatitis B, VDRL, maternal pyrexia, antibiotics, medical problems. Empty string if not mentioned."
        ),
        "pregnancyContd": types.Schema(
            type=types.Type.STRING,
            description="Continuation of pregnancy details including complications, conception method (natural/ART), multiple pregnancy, dating scan, anomaly scan, other scans, Doppler findings. Empty string if not mentioned."
        ),
        "labour": types.Schema(
            type=types.Type.STRING,
            description="Labour details including spontaneous/induced, nature, use of syntocinon, risk factors for sepsis with details. Empty string if not mentioned."
        ),
        "delivery": types.Schema(
            type=types.Type.STRING,
            description="Delivery information including mode (NVD/LSCS/etc), indication, presentation, fetal distress, CTG findings, anesthesia type, gastric aspirate, delayed cord clamping (DCC) with duration, cord blood gas (pH, HCO3, BE), liquor status, PROM duration. Empty string if not mentioned."
        ),
        "apgar": types.Schema(
            type=types.Type.STRING,
            description="APGAR scores at 1, 5, 10, 15, 20 minutes with color, heart rate, reflex, tone, respiration breakdown. Empty string if not mentioned."
        ),
        "resuscitationDetails": types.Schema(
            type=types.Type.STRING,
            description="Resuscitation performed: facial O2 duration & max FiO2, initial steps, time to first gasp, time to regular respiration, delivery room CPAP, bag-mask ventilation duration, intubation (ETT size, depth), PPV duration, CPR duration, drugs administered. Empty string if not mentioned."
        ),
        "essentialDetails": types.Schema(
            type=types.Type.STRING,
            description="Initial examination summary, malformations, ICT, DCT results, background, plan. Empty string if not mentioned."
        ),
        "postResuscitationCare": types.Schema(
            type=types.Type.STRING,
            description="Post-resuscitation care provided in NICU. Empty string if not mentioned."
        ),
        "admissionDetails": types.Schema(
            type=types.Type.STRING,
            description="Details of NICU admission including reason, time. Empty string if not mentioned."
        ),
        "procedures": types.Schema(
            type=types.Type.STRING,
            description="Procedures performed (e.g., line insertion, surfactant). Empty string if not mentioned."
        ),
        "diagnosis": types.Schema(
            type=types.Type.STRING,
            description="Admission diagnosis. Empty string if not mentioned."
        ),
        "summaryOfExamination": types.Schema(
            type=types.Type.STRING,
            description="Detailed physical examination findings for postnatal ward babies. Empty string if not mentioned."
        ),

        # ========== TYPED FIELDS (5 fields) ==========
        "transferStatus": types.Schema(
            type=types.Type.STRING,
            description="Transfer destination: NICU, HDU, SCBU, Postnatal Ward, or Nursery. Empty string if not mentioned."
        ),
        "admissionWeight": types.Schema(
            type=types.Type.NUMBER,
            description="Weight at admission in kg (decimal). 0 if not mentioned."
        ),
        "visitNumber": types.Schema(
            type=types.Type.INTEGER,
            description="Visit/Admission sequence number. 0 if not mentioned."
        ),
        "ageOnAdmission": types.Schema(
            type=types.Type.INTEGER,
            description="Age in hours at admission. 0 if not mentioned."
        ),
        "correctedGestation": types.Schema(
            type=types.Type.STRING,
            description="Corrected gestational age (e.g., '37 + 2'). Empty string if not mentioned."
        ),
    }
)

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

NEO_PROFORMA_FREE_SYSTEM_PROMPT = """You are a specialized clinical data extraction AI for neonatal proforma records.

**YOUR ROLE:**
Extract neonatal proforma data from transcribed clinical notes and return structured JSON with FREE-TEXT clinical fields.

Unlike the structured NEO_PROFORMA format with ~185 individual fields, this format uses ~21 fields where most clinical data is captured as descriptive free text within topic-specific fields.

**CRITICAL RULES:**
1. NEVER fabricate clinical information or assume data not explicitly stated
2. Use empty string "" for text fields and 0 for numeric fields where no information is mentioned
3. If a value is corrected during dictation, use the LATEST/FINAL value
4. Capture clinical details VERBATIM as described by the clinician — do not paraphrase or summarize excessively
5. Include ALL relevant details within each field — do not omit values, measurements, or drug details
6. For numeric values (vitals, lab results, drug doses), include the exact numbers with units as stated

**FIELD GUIDELINES:**

- **uhid**: Extract patient UHID/hospital ID if mentioned. Empty string if not.
- **entryDate**: Date in YYYY-MM-DD format. Empty string if not mentioned.
- **seenBy**: Array of doctor IDs (integers). Default to [7] if none mentioned.
- **obstetricHistory**: ALL maternal details — gravida, para, blood group, antenatal care.
- **pregnancy**: ALL pregnancy details — LMP, EDD, steroids, infections, medical problems.
- **pregnancyContd**: Continuation — complications, conception method, scans, Doppler.
- **labour**: Labour details — spontaneous/induced, nature, sepsis risk factors.
- **delivery**: Delivery details — mode, presentation, APGAR context, cord blood gas, liquor.
- **apgar**: APGAR scores with component breakdown at each minute.
- **resuscitationDetails**: ALL resuscitation — facial O2, CPAP, ventilation, intubation, CPR, drugs.
- **essentialDetails**: Initial exam summary, malformations, ICT/DCT, background, plan.
- **postResuscitationCare**: Post-resuscitation care in NICU.
- **admissionDetails**: NICU admission details — reason, time.
- **procedures**: Procedures performed — lines, surfactant, etc.
- **diagnosis**: Admission diagnosis.
- **summaryOfExamination**: Physical examination findings.
- **transferStatus**: Where baby was transferred — NICU/HDU/SCBU/Postnatal Ward/Nursery.
- **admissionWeight**: Weight in kg (decimal).
- **visitNumber**: Visit/admission sequence number (integer).
- **ageOnAdmission**: Age in hours at admission (integer).
- **correctedGestation**: Corrected gestational age string (e.g., "37 + 2").

**CLINICAL ABBREVIATION AWARENESS:**
Recognize and correctly extract common NICU abbreviations:
- Delivery: NVD, LSCS, CTG, DCC, PROM
- Conditions: RDS, MAS, HIE, NNJ, PDA, IUGR, FGR, PPROM
- Labs: ABG, TSB, ICT, DCT, HCO3
- Resuscitation: CPAP, PPV, CPR, ETT
- Facilities: NICU, HDU, SCBU
- Others: EBM, NPO, MgSO4, VDRL, HIV

**OUTPUT FORMAT:**
Return ONLY valid JSON matching the schema. No markdown, no explanations."""

# ============================================================================
# USER PROMPT
# ============================================================================

NEO_PROFORMA_FREE_USER_PROMPT = """Extract neonatal proforma data from this transcript into the free-text format:

---
{transcript}
---

**EXTRACTION INSTRUCTIONS:**

1. **uhid**: Patient hospital ID if stated. Empty string otherwise.
2. **entryDate**: Date in YYYY-MM-DD format. Empty string if not stated.
3. **seenBy**: Doctor IDs as integers array. Default to [7] if none mentioned.
4. **obstetricHistory**: Maternal obstetric history as free text.
5. **pregnancy**: Pregnancy details as free text.
6. **pregnancyContd**: Pregnancy continuation details as free text.
7. **labour**: Labour details as free text.
8. **delivery**: Delivery information as free text.
9. **apgar**: APGAR scores as free text.
10. **resuscitationDetails**: Resuscitation details as free text.
11. **essentialDetails**: Initial examination summary as free text.
12. **postResuscitationCare**: Post-resuscitation care as free text.
13. **admissionDetails**: Admission details as free text.
14. **procedures**: Procedures performed as free text.
15. **diagnosis**: Diagnosis as free text.
16. **summaryOfExamination**: Physical examination as free text.
17. **transferStatus**: Transfer destination (NICU/HDU/SCBU/Postnatal Ward/Nursery).
18. **admissionWeight**: Weight in kg (decimal). 0 if not stated.
19. **visitNumber**: Visit number (integer). 0 if not stated.
20. **ageOnAdmission**: Age in hours (integer). 0 if not stated.
21. **correctedGestation**: Gestational age string. Empty string if not stated.

**IMPORTANT:**
- Capture ALL clinical details within the appropriate field — include exact numbers, drug doses, and measurements
- If a topic is not discussed in the transcript, use empty string "" for text fields and 0 for numeric fields
- For seenBy: only default to [7] if absolutely NO doctor IDs are mentioned anywhere in the transcript
{medicine_list_section}
{investigation_list_section}

Return ONLY the JSON object. No markdown, no explanations."""

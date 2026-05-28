**History**

Extract patient history including chief complaints with duration, history of present illness as ONE sentence, current medications (name/dosage/frequency only), past medical and surgical history, and other history combining family/social/allergies.

**Extraction Rules:**
- Chief Complaints: Extract key symptoms in ultra-brief medical terminology. Include ALL symptoms (primary + associated) in priority order. Convert to medical terminology: "sleepless nights" → "Insomnia", "difficulty breathing" → "Dyspnea". Include duration with "×" notation (× 2d = for 2 days)
- History of present illness: Characterize in one line the onset, severity and progression where relevant. Include negative findings in history if explicitly mentioned (e.g., "No altered bowel movements")
- Past Medical History: Previous medical conditions and hospitalizations
- Past Surgical History: Mention Previous surgeries along with year of procedure
- Other History: Includes details on family medical conditions, allergy etc. 
- Current medications: medication_name, dosage and frequency (1-0-0, 1-0-1). Use standard medical notation: OD = Once Daily, BD = Twice Daily, TDS = Three times daily, QID = Four times daily

**Examples:**
["Headache, dizziness × 2d post-medication discontinuation. Sever, started 2 days ago and gradually worsening", "Fatigue, palpitations. No chest pain"]

{
  "type": "object",
  "properties": {
    "other_history": {
      "type": "string",
      "description": "Combined family, social and allergic history or N/A"
    },
    "chief_complaints": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Array of symptoms in medical terminology with duration (e.g., Headache x 2d)"
    },
    "current_medications": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "dosage": {
            "type": "string"
          },
          "frequency": {
            "type": "string"
          },
          "medication_name": {
            "type": "string"
          }
        }
      },
      "description": "Current medications with name, dosage, frequency only"
    },
    "past_medical_history": {
      "type": "string",
      "description": "Comma-separated previous medical conditions or N/A"
    },
    "past_surgical_history": {
      "type": "string",
      "description": "Comma-separated previous surgeries with years or N/A"
    },
    "history_of_present_illness": {
      "type": "string",
      "description": "ONE SENTENCE combining onset, progression, severity, negative findings"
    }
  }
}

**Diagnosis**

Extract primary and secondary diagnoses using precise medical terminology. Include ICD10 codes for diagnoses

**Extraction Rules:**
- ✅ Use precise medical terminology with staging/severity
- ✅ Primary diagnosis: Main diagnosis exactly as stated or clinically inferred
- ✅ Secondary diagnoses: Additional conditions (if explicitly stated as secondary OR totally different from primary)
- ❌ Do NOT fabricate diagnoses not stated or clearly implied
- ❌ Do NOT repeat the same diagnosis in both primary and secondary

**Examples:**
Primary: "Hypertension Stage 2 with medication withdrawal syndrome"
Secondary: "Generalized Anxiety Disorder" (comma-separated if multiple: "Generalized Anxiety Disorder, Type 2 Diabetes Mellitus")

{
  "type": "object",
  "properties": {
    "icd10_codes": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "primary_diagnosis": {
      "type": "string",
      "description": "Main diagnosis with medical terminology"
    },
    "secondary_diagnoses": {
      "type": "string",
      "description": "Comma-separated additional conditions or N/A"
    }
  }
}


**EXAMINATION**

Extract vital signs with units, system examinations (CVS, RS, CNS, P/A, MSK), and clinical assessment connecting symptoms to findings to diagnosis in 1-2 sentences.

**Extraction Rules:**
- Get Doctor's objective findings(e.g. "abdominal tenderness")
- Include complete vital signs with units: Temperature (°F/°C), Pulse Rate (/min), Respiratory Rate (/min), BP (mmHg), Height (cm), Weight (kg), SpO2 (%)
- System examinations: CVS (Cardiovascular), RS (Respiratory), CNS (Central nervous), P/A (Per abdomen), MSK (Musculoskeletal)
- Use standard abbreviations

**Example Vital Signs:**
Temperature: "98.6°F", Pulse: "72/min", BP: "160/90 mmHg", Height: "165 cm", Weight: "57 kg", BMI: "20.9", SpO2: "98%"
**Example clinical assessment:**
Patient presents with withdrawal symptoms (↑BP 160/90, giddiness) after 4-day medication lapse. Current vitals show Stage 2 hypertension requiring immediate resumption of therapy
**Example System Findings:**
CVS: "S1, S2 present, no murmurs" | RS: "Clear breath sounds bilaterally, no wheezing"

{
  "type": "object",
  "properties": {
    "vital_signs": {
      "type": "object",
      "properties": {
        "height": {
          "type": "string"
        },
        "weight": {
          "type": "string"
        },
        "pulse_rate": {
          "type": "string"
        },
        "temperature": {
          "type": "string"
        },
        "blood_pressure": {
          "type": "string"
        },
        "respiratory_rate": {
          "type": "string"
        },
        "oxygen_saturation": {
          "type": "string"
        }
      }
    },
    "other_systems": {
      "type": "string"
    },
    "musculoskeletal": {
      "type": "string"
    },
    "respiratory_system": {
      "type": "string"
    },
    "clinical_assessment": {
      "type": "string",
      "description": "1-2 sentences: symptoms → findings → diagnosis connection with severity"
    },
    "cardiovascular_system": {
      "type": "string"
    },
    "central_nervous_system": {
      "type": "string"
    }
  }
}

**Investigations**

Extract laboratory test results with normal ranges, imaging study findings, and other investigations with dates.

{
  "type": "object",
  "properties": {
    "other_tests": {
      "type": "string",
      "description": "test: findings, date or N/A"
    },
    "imaging_studies": {
      "type": "string",
      "description": "study: findings, date or N/A"
    },
    "laboratory_tests": {
      "type": "string",
      "description": "test: result [range] - interpretation, date or N/A"
    }
  }
}

**PRESCRIPTION**
Medication Object Fields:
- name: Drug name with strength (e.g. 10mg, 200mg, 650)
- morning_qty: How much to take in the morning (e.g. "1.00")
- noon_qty: How much to take at noon (e.g. "1.00")
- evening_qty: How much to take in the evening (e.g. "0.00")
- night_qty: How much to take in the night (e.g. "1.00")
- durationDays: How long to take (e.g. 5 days)
- timeToTake: Before/after food
- remarks: Take one tablet orally after food every morning

**Extraction Rules:**
- ✅ Split the dosing schedule into respective fields (e.g. dosing schedule of 1-0-0-1 will be split as morning_qty="1.00", noon_qty="0.00", evening_qty="0.00", night_qty="1.00")
- ✅ Include medication name WITH strength in name field
- ✅ Note timing: before food, after food, specific time
- ✅ Include route of administration when specified in remarks field
- ✅ Include dosage such as 1 tablet or 5ml when specified in remarks field
- ❌ Do NOT separate strength from name incorrectly
**Example:**
```json
{
  "medications": [
    {
      "name": "TAB. AMLODIPINE 5MG",
      "morning_qty": "1.00",
      "noon_qty": "0.00",
      "evening_qty": "0.00",
      "night_qty": "0.00",
      "durationDays": "30.00",
      "timeToTake": "after food",
      "remarks": "Take 1 tablet every morning orally after food"
    }
  ]
}
```
{
  "type": "object",
  "properties": {
    "medications": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "remarks": {
            "type": "string"
          },
          "noon_qty": {
            "type": "string"
          },
          "night_qty": {
            "type": "string"
          },
          "timeToTake": {
            "type": "string"
          },
          "evening_qty": {
            "type": "string"
          },
          "morning_qty": {
            "type": "string"
          },
          "durationDays": {
            "type": "string"
          }
        }
      }
    }
  }
}

**Treatment Plan**
Extract follow-up timeline and conditions, and other instructions combining diet, activity, monitoring, and warning signs into one field.
***Example:***
```
json
{
  "follow_up": "Come back in 2 weeks on 10-12-2025 and bring your previous blood reports,
  "other_instructions": "Increase protein intake, avoid spicy food and avoid heavy lifting. Contact immediately if fever >102°F, severe headache, or breathing difficulty"
}
```

{
  "type": "object",
  "properties": {
    "follow_up": {
      "type": "string", 
      "description": "Instructions on when to come back..."
    },
    "other_instructions": {
      "type": "string",
      "description": "Non prescription instructions or N/A"
    }
 }
}
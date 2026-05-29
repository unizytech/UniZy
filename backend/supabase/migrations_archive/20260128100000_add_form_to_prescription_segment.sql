-- Add "form" field to AOSTA Prescription segment definition (schema + prompt)
-- This allows Gemini to extract the medicine form (tablet, syrup, capsule, etc.) when mentioned

UPDATE segment_definitions
SET
  schema_definition_json = '{
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "form": { "type": "string" },
        "remarks": { "type": "string" },
        "noon_qty": { "type": "string" },
        "night_qty": { "type": "string" },
        "timeToTake": { "type": "string" },
        "evening_qty": { "type": "string" },
        "morning_qty": { "type": "string" },
        "durationDays": { "type": "string" }
      }
    }
  }'::jsonb,
  prompt_section_text = E'Extract prescription with medication details (name with strength, form if mentioned, morning/noon/evening/night quantities, duration, timing, remarks). For Discharge cases, these are medications to be followed upon discharge. If the form (tablet, syrup, capsule, drops, injection, etc.) is mentioned or clearly implied, include it in the "form" field. If not mentioned, omit or leave empty.\n\n***Example:***\n```\njson\n{\n  "prescription": [\n    {\n      "name": "Paracetamol 500mg",\n      "form": "Tablet",\n      "remarks": "Take after food",\n      "morning_qty": "1",\n      "noon_qty": "0",\n      "evening_qty": "1",\n      "night_qty": "1",\n      "timeToTake": "After meals",\n      "durationDays": "5"\n    },\n    {\n      "name": "Amoxicillin 500mg",\n      "form": "Capsule",\n      "remarks": "Complete the full course",\n      "morning_qty": "1",\n      "noon_qty": "0",\n      "evening_qty": "0",\n      "night_qty": "1",\n      "timeToTake": "Before meals",\n      "durationDays": "7"\n    },\n    {\n      "name": "Vitamin D3 60000 IU",\n      "form": "",\n      "remarks": "Once weekly",\n      "morning_qty": "1",\n      "noon_qty": "0",\n      "evening_qty": "0",\n      "night_qty": "0",\n      "timeToTake": "After breakfast",\n      "durationDays": "28"\n    }\n  ]\n}\n```'
WHERE id = '50008f45-7688-4d78-9ef9-331be39c180d';

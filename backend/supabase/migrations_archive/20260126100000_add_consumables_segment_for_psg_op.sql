-- Add CONSUMABLES segment definition and link to PSG_OP template
-- This segment extracts medical consumables/supplies prescribed for the patient

-- Step 1: Insert CONSUMABLES segment definition
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'CONSUMABLES',
    'PSG Consumables',
    '**CONSUMABLES:**
Extract any consumables/medical supplies mentioned for the patient. For each consumable:
- name: Name of the consumable item (e.g., gauze, bandage, syringe, cotton, gloves, catheter, etc.)
- qty: Quantity prescribed or dispensed (as a number)
- instructions: Usage instructions or special notes

If no consumables are mentioned, return an empty array.

***Example:***
```json
{
  "consumables": [
    {
      "name": "Sterile Gauze 4x4",
      "qty": 10,
      "instructions": "Change dressing twice daily"
    },
    {
      "name": "Surgical Tape",
      "qty": 1,
      "instructions": "Use to secure dressing"
    }
  ]
}
```',
    '{
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of consumable item from hospital list"
                },
                "qty": {
                    "type": "number",
                    "description": "Quantity of consumable prescribed or dispensed"
                },
                "instructions": {
                    "type": "string",
                    "description": "Usage instructions or special notes"
                }
            }
        },
        "description": "List of medical consumables/supplies prescribed for the patient"
    }'::jsonb,
    'core',
    false,
    14,
    'balanced',
    'medical_terms',
    'Medical consumables and supplies prescribed for the patient (gauze, bandages, syringes, etc.)',
    true,
    'system',
    NOW(),
    NOW()
);

-- Step 2: Link CONSUMABLES segment to PSG_OP template
-- Get the segment_id we just created and link it
INSERT INTO template_segments (
    id,
    template_id,
    segment_code,
    segment_id,
    category,
    display_order,
    brevity_level,
    terminology_style,
    created_at,
    template_name
)
SELECT
    gen_random_uuid(),
    'a35a6622-8111-4366-acac-664209ab56a2'::uuid,  -- PSG_OP template ID
    'CONSUMABLES',
    sd.id,
    'core',
    14,  -- After PRESCRIPTION (13)
    'balanced',
    'medical_terms',
    NOW(),
    'PSG_OP'
FROM segment_definitions sd
WHERE sd.segment_code = 'CONSUMABLES'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL;

-- Step 3: Trigger template reassembly by updating the template
UPDATE templates
SET
    updated_at = NOW(),
    prompt_trigger_source = 'migration: added CONSUMABLES segment',
    schema_trigger_source = 'migration: added CONSUMABLES segment'
WHERE id = 'a35a6622-8111-4366-acac-664209ab56a2';

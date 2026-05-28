# Doctor Configuration API Integration Guide

**Version:** 1.0  
**Base URL:** `http://localhost:8000` (or your deployment URL)

## Table of Contents
1. [Overview](#overview)
2. [Core Concepts](#core-concepts)
3. [API Endpoints](#api-endpoints)
4. [Frontend Service Code](#frontend-service-code)
5. [Integration Examples](#integration-examples)

---

## Overview

The Doctor Configuration system allows doctors to:
- **Activate templates** with custom names
- **Move segments** between categories (Core, Additional, Excluded)
- **Customize segment preferences** (brevity, terminology)
- **Manage multiple template activations** independently

All configurations persist in the database and are automatically applied during AI extraction.

---

## Core Concepts

### Template Activation
- Same template can be activated **multiple times** with different names
- Each activation gets a unique `activation_id` (used as `active_template_id`)
- Use `template_name_override` to identify specific activations in API calls

### Segment Categories
- **Core**: Essential segments, extracted first (~25-35s)
- **Additional**: Supplementary segments, background loading (~30-45s)
- **Excluded**: Hidden from extraction

### Configuration Hierarchy (Highest to Lowest Priority)
1. Doctor's template-specific config (`doctor_segment_configurations` with `active_template_id`)
2. Template config (`template_segment_configurations`)
3. Consultation type defaults (`consultation_type_segment_defaults`)
4. Segment base defaults (`segment_definitions`)

---

## API Endpoints

### 1. Get All Available Templates

**Endpoint:** `GET /api/v1/summary/templates`

**Query Parameters:**
- `doctor_id` (optional): UUID - Filter templates visible to this doctor

**Response:**
```json
{
  "success": true,
  "templates": [
    {
      "id": "uuid",
      "template_code": "PSYCHIATRY_CORE",
      "template_name": "Psychiatry Core Template",
      "template_description": "Core segments for psychiatry consultations",
      "consultation_type_id": "uuid",
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient Consultation",
      "specialization": "Psychiatry",
      "hospital_id": null,
      "created_by_doctor_id": null,
      "is_active": true
    }
  ],
  "count": 1
}
```

---

### 2. Get Doctor's Activated Templates

**Endpoint:** `GET /api/v1/doctors/{doctor_id}/activated-templates`

**Path Parameters:**
- `doctor_id`: UUID - Doctor's unique identifier

**Response:**
```json
{
  "success": true,
  "templates": [
    {
      "id": "activation-uuid-123",
      "template_id": "template-uuid-456",
      "doctor_id": "doctor-uuid",
      "template_code": "PSYCHIATRY_CORE",
      "template_name": "Psychiatry Core Template",
      "template_name_override": "My Psych Template",
      "consultation_type_id": "consult-uuid",
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient Consultation",
      "description": "Core segments for psychiatry",
      "activated_at": "2025-01-15T10:30:00Z",
      "has_custom_overrides": true
    }
  ],
  "count": 1
}
```

**Key Fields:**
- `id`: Unique activation ID (use for deletion)
- `template_id`: Original template UUID (can repeat across activations)
- `template_name_override`: Doctor's custom name (use in segment API calls)

---

### 3. Activate a Template

**Endpoint:** `POST /api/v1/summary/templates/{consultation_type_code}/activate/{template_code}`

**Path Parameters:**
- `consultation_type_code`: String - e.g., "OP", "DISCHARGE"
- `template_code`: String - e.g., "PSYCHIATRY_CORE"

**Query Parameters:**
- `doctor_id`: UUID - Required

**Request Body:**
```json
{
  "custom_name": "My Custom Template Name"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Template activated successfully",
  "activation": {
    "id": "activation-uuid",
    "template_id": "template-uuid",
    "template_name_override": "My Custom Template Name"
  }
}
```

---

### 4. Get Segments for Template

**Endpoint:** `GET /api/v1/summary/segments/{consultation_type_code}`

**Path Parameters:**
- `consultation_type_code`: String - e.g., "OP"

**Query Parameters:**
- `doctor_id`: UUID - Required
- `template_name`: String - The `template_name_override` value
- `mode`: String - `'full'` | `'core'` | `'additional'` (default: 'full')

**Response:**
```json
{
  "segments": [
    {
      "segment_code": "DIAGNOSIS",
      "segment_name": "Diagnosis",
      "default_category": "core",
      "display_order": 1,
      "is_required": true,
      "default_brevity_level": "balanced",
      "default_terminology_style": "medical_terms",
      "prompt_section_text": "Extract primary and differential diagnoses...",
      "schema_definition_json": {
        "type": "object",
        "properties": {
          "primary_diagnosis": {"type": "string"},
          "icd_10_code": {"type": "string"}
        }
      }
    }
  ]
}
```

---

### 5. Move Segment Between Categories

**Endpoint:** `POST /api/v1/summary/segments/move`

**Query Parameters:**
- `doctor_id`: UUID - Required
- `template_name`: String - The `template_name_override` value

**Request Body:**
```json
{
  "segment_code": "INVESTIGATIONS",
  "new_category": "core"
}
```

**Valid Categories:** `"core"` | `"additional"` | `"excluded"`

**Response:**
```json
{
  "success": true,
  "message": "Segment 'INVESTIGATIONS' moved to CORE (template 'My Template')",
  "configuration": {
    "id": "config-uuid",
    "doctor_id": "doctor-uuid",
    "segment_code": "INVESTIGATIONS",
    "category": "core",
    "active_template_id": "activation-uuid"
  }
}
```

**Notes:**
- Required segments (where `is_required=true`) cannot be moved from Core
- Automatically sets `has_custom_overrides=true` on the template activation

---

### 6. Update Segment Preferences

**Endpoint:** `PUT /api/v1/summary/segments/{segment_code}`

**Path Parameters:**
- `segment_code`: String - e.g., "DIAGNOSIS"

**Query Parameters:**
- `doctor_id`: UUID - Required
- `template_name`: String - The `template_name_override` value

**Request Body:**
```json
{
  "brevity_level": "concise",
  "terminology_style": "simple_terms"
}
```

**Valid Values:**
- `brevity_level`: `"concise"` | `"balanced"` | `"detailed"`
- `terminology_style`: `"medical_terms"` | `"simple_terms"` | `"as_spoken"`

**Response:**
```json
{
  "success": true,
  "message": "Segment configuration updated successfully",
  "segment": {
    "segment_code": "DIAGNOSIS",
    "brevity_level": "concise",
    "terminology_style": "simple_terms"
  }
}
```

---

### 7. Rename Template

**Endpoint:** `PUT /api/v1/summary/templates/{template_code}/rename`

**Path Parameters:**
- `template_code`: String - Original template code

**Query Parameters:**
- `doctor_id`: UUID - Required

**Request Body:**
```json
{
  "new_name": "Updated Template Name"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Template renamed successfully"
}
```

---

### 8. Delete Activated Template

**Endpoint:** `DELETE /api/v1/doctors/{doctor_id}/activated-templates/{activation_id}`

**Path Parameters:**
- `doctor_id`: UUID - Doctor's ID
- `activation_id`: UUID - The unique activation ID (from `id` field)

**Response:**
```json
{
  "success": true,
  "message": "Template 'My Template' (PSYCHIATRY_CORE) deactivated successfully",
  "deleted_activation_id": "activation-uuid"
}
```

**Note:** This cascades to delete all associated `doctor_segment_configurations`

---

## Frontend Service Code

### TypeScript/JavaScript Service

```typescript
// doctorConfigApi.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

export interface Template {
  id: string;
  template_code: string;
  template_name: string;
  template_description: string;
  consultation_type_code: string;
  consultation_type_name: string;
  specialization: string | null;
  is_active: boolean;
}

export interface ActivatedTemplate {
  id: string;                        // Activation ID
  template_id: string;               // Original template ID
  template_code: string;
  template_name: string;             // Original name
  template_name_override: string;    // Custom name
  consultation_type_code: string;
  consultation_type_name: string;
  activated_at: string;
  has_custom_overrides: boolean;
}

export interface Segment {
  segment_code: string;
  segment_name: string;
  default_category: 'core' | 'additional' | 'excluded';
  display_order: number;
  is_required: boolean;
  default_brevity_level: 'concise' | 'balanced' | 'detailed';
  default_terminology_style: 'medical_terms' | 'simple_terms' | 'as_spoken';
  prompt_section_text: string;
  schema_definition_json: any;
}

// Get all available templates
export async function getAvailableTemplates(doctorId?: string): Promise<Template[]> {
  const url = doctorId 
    ? `${API_BASE_URL}/api/v1/summary/templates?doctor_id=${doctorId}`
    : `${API_BASE_URL}/api/v1/summary/templates`;
    
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to fetch templates');
  
  const data = await response.json();
  return data.templates;
}

// Get doctor's activated templates
export async function getActivatedTemplates(doctorId: string): Promise<ActivatedTemplate[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/doctors/${doctorId}/activated-templates`
  );
  
  if (!response.ok) throw new Error('Failed to fetch activated templates');
  
  const data = await response.json();
  return data.templates;
}

// Activate a template
export async function activateTemplate(
  doctorId: string,
  consultationTypeCode: string,
  templateCode: string,
  customName: string
): Promise<any> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/summary/templates/${consultationTypeCode}/activate/${templateCode}?doctor_id=${doctorId}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ custom_name: customName })
    }
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to activate template');
  }
  
  return response.json();
}

// Load segments for a template
export async function getTemplateSegments(
  doctorId: string,
  consultationTypeCode: string,
  templateName: string,
  mode: 'full' | 'core' | 'additional' = 'full'
): Promise<Segment[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/summary/segments/${encodeURIComponent(consultationTypeCode)}?doctor_id=${doctorId}&template_name=${encodeURIComponent(templateName)}&mode=${mode}`
  );
  
  if (!response.ok) throw new Error('Failed to load segments');
  
  const data = await response.json();
  return data.segments;
}

// Move segment to different category
export async function moveSegment(
  doctorId: string,
  templateName: string,
  segmentCode: string,
  newCategory: 'core' | 'additional' | 'excluded'
): Promise<any> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/summary/segments/move?doctor_id=${doctorId}&template_name=${encodeURIComponent(templateName)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segment_code: segmentCode, new_category: newCategory })
    }
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to move segment');
  }
  
  return response.json();
}

// Update segment preferences
export async function updateSegmentPreferences(
  doctorId: string,
  templateName: string,
  segmentCode: string,
  brevityLevel: 'concise' | 'balanced' | 'detailed',
  terminologyStyle: 'medical_terms' | 'simple_terms' | 'as_spoken'
): Promise<any> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/summary/segments/${encodeURIComponent(segmentCode)}?doctor_id=${doctorId}&template_name=${encodeURIComponent(templateName)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brevity_level: brevityLevel,
        terminology_style: terminologyStyle
      })
    }
  );
  
  if (!response.ok) throw new Error('Failed to update segment preferences');
  
  return response.json();
}

// Rename template
export async function renameTemplate(
  doctorId: string,
  templateCode: string,
  newName: string
): Promise<any> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/summary/templates/${templateCode}/rename?doctor_id=${doctorId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_name: newName })
    }
  );
  
  if (!response.ok) throw new Error('Failed to rename template');
  
  return response.json();
}

// Delete activated template
export async function deleteActivatedTemplate(
  doctorId: string,
  activationId: string
): Promise<any> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/doctors/${doctorId}/activated-templates/${activationId}`,
    { method: 'DELETE' }
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete template');
  }
  
  return response.json();
}
```

---

## Integration Examples

### Example 1: Complete Template Activation Flow

```typescript
import * as api from './doctorConfigApi';

async function activateAndConfigureTemplate(doctorId: string) {
  try {
    // 1. Get available templates
    const templates = await api.getAvailableTemplates(doctorId);
    const psychiatryTemplate = templates.find(t => t.template_code === 'PSYCHIATRY_CORE');
    
    if (!psychiatryTemplate) {
      throw new Error('Template not found');
    }
    
    // 2. Activate template with custom name
    const activation = await api.activateTemplate(
      doctorId,
      psychiatryTemplate.consultation_type_code,
      psychiatryTemplate.template_code,
      'My Psychiatry Workflow'
    );
    
    console.log('Template activated:', activation);
    
    // 3. Load segments
    const segments = await api.getTemplateSegments(
      doctorId,
      psychiatryTemplate.consultation_type_code,
      'My Psychiatry Workflow',
      'full'
    );
    
    console.log('Loaded segments:', segments);
    
    // 4. Move a segment to Core
    await api.moveSegment(
      doctorId,
      'My Psychiatry Workflow',
      'INVESTIGATIONS',
      'core'
    );
    
    // 5. Update segment preferences
    await api.updateSegmentPreferences(
      doctorId,
      'My Psychiatry Workflow',
      'DIAGNOSIS',
      'detailed',
      'medical_terms'
    );
    
    console.log('Configuration complete!');
    
  } catch (error) {
    console.error('Error:', error);
  }
}
```

### Example 2: Display Activated Templates with Segments

```typescript
async function displayDoctorConfig(doctorId: string) {
  // Get activated templates
  const activatedTemplates = await api.getActivatedTemplates(doctorId);
  
  for (const template of activatedTemplates) {
    console.log(`\nTemplate: ${template.template_name_override}`);
    console.log(`Original: ${template.template_name}`);
    console.log(`Customized: ${template.has_custom_overrides}`);
    
    // Load segments for this template
    const segments = await api.getTemplateSegments(
      doctorId,
      template.consultation_type_code,
      template.template_name_override,
      'full'
    );
    
    // Group by category
    const core = segments.filter(s => s.default_category === 'core');
    const additional = segments.filter(s => s.default_category === 'additional');
    const excluded = segments.filter(s => s.default_category === 'excluded');
    
    console.log(`  Core: ${core.length} segments`);
    console.log(`  Additional: ${additional.length} segments`);
    console.log(`  Excluded: ${excluded.length} segments`);
  }
}
```

### Example 3: Drag-and-Drop Handler

```typescript
// React example with drag-and-drop
async function handleSegmentDrop(
  doctorId: string,
  templateName: string,
  segmentCode: string,
  targetCategory: 'core' | 'additional' | 'excluded'
) {
  try {
    // Move segment
    await api.moveSegment(doctorId, templateName, segmentCode, targetCategory);
    
    // Reload segments to reflect changes
    const updatedSegments = await api.getTemplateSegments(
      doctorId,
      'OP', // consultation type
      templateName,
      'full'
    );
    
    // Update UI state
    return updatedSegments;
    
  } catch (error) {
    console.error('Failed to move segment:', error);
    throw error;
  }
}
```

---

## Important Notes

### Authentication
The API endpoints shown do not include authentication headers. In production, you should add:
```typescript
headers: {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
}
```

### Error Handling
All endpoints return error details in this format:
```json
{
  "detail": "Error message describing what went wrong"
}
```

### Template Name Usage
- Always use `template_name_override` (the custom name) in segment API calls
- This identifies the specific activation instance
- Multiple activations of the same template have different `template_name_override` values

### Required Segments
- Segments with `is_required: true` cannot be moved from Core category
- Validate this on the frontend before calling the move API
- The backend will reject attempts to move required segments

### Performance Considerations
- Cache template and segment lists when possible
- Reload segments only after configuration changes
- Use `mode='core'` for faster loading if you only need core segments

---

## Support

For issues or questions:
- Review the existing `ADMIN_DOCTOR_CONFIGURATION_GUIDE.md` for detailed system architecture
- Check database schema in `backend/supabase/schema_enhanced.sql`
- Reference implementation: `app/components/DoctorTemplateConfigScreen.tsx`

---

**End of Document**

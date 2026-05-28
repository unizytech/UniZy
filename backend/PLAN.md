# Development Plan

**Last Updated:** 2025-12-30 18:23:05

## Current Plan

# Plan: Add Patient Creation API Endpoint

## Goal
Create a dedicated API endpoint to manually create patients in the `patients` table.

## Patients Table Schema
| Column | Type | Required | Notes |
|--------|------|----------|-------|
| `id` | uuid | Auto | Primary key |
| `patient_id` | varchar | **Yes** | External ID (UHID/MRN) |
| `full_name` | varchar | No | Patient name |
| `date_of_birth` | date | No | Birth date |
| `gender` | varchar | No | M/F |
| `ip_id` | varchar | No | Inpatient ID (dedicated column) |
| `op_id` | varchar | No | Outpatient ID (dedicated column) |
| `add_info` | jsonb | No | Additional metadata |
| `is_anonymized` | boolean | No | Default false |

## File to Modify
`backend/routers/patient_history.py`

## Implementation

### 1. Add Request/Response Models
```python
class PatientCreateRequest(BaseModel):
    patient_id: str  # Required - UHID/MRN
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None  # ISO format: YYYY-MM-DD
    gender: Optional[str] = None
    ip_id: Optional[str] = None
    op_id: Optional[str] = None
    add_info: Optional[Dict[str, Any]] = None

class PatientCreateResponse(BaseModel):
    success: bool
    patient: Optional[Dict[str, Any]] = None
    created: bool = False  # True if new, False if existing
    message: str
```

### 2. Add POST Endpoint
```python
@router.post("", response_model=PatientCreateResponse)
async def create_patient(request: Request, body: PatientCreateRequest):
    """Create a new patient or return existing if patient_id already exists."""
```

**Logic:**
1. Check if patient exists by `patient_id`
2. If exists: return existing patient with `created=False`
3. If not: insert new patient with all provided fields
4. Return the patient record with `created=True`

### 3. Placement
Add after the router definition (around line 97) before the search endpoint.

---

*This file is automatically updated by Claude Code hooks when plans are created.*

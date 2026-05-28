# Command Center Dashboard API Documentation

Base URL: `http://localhost:8000`

---

## Authentication

All endpoints require authentication via `Depends(get_current_client)`. Supported client types: `admin`, `web_app`, `mobile_app`, `ehr`.

| Endpoint Group | Auth Required | Auth Level |
|---|---|---|
| `/api/v1/dashboard/*` | Yes | `Depends(get_current_client)` — admin, web_app, mobile_app, ehr |
| `/api/v1/doctors/hospitals` | Yes | `Depends(get_current_client)` — admin, web_app, mobile_app, ehr |
| `/api/v1/doctors/list-all` | Yes | `Depends(get_current_client)` — admin, web_app, mobile_app, ehr |
| `/api/v1/doctors/specializations` | Yes | `Depends(get_current_client)` — admin, web_app, mobile_app, ehr |

All requests must include a valid authentication header. Unauthenticated requests will receive a `401 Unauthorized` response.

---

## Common Query Parameters

These filters are shared across most dashboard endpoints:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `hospital_id` | `string (UUID)` | `null` | Filter by hospital |
| `department_id` | `string (UUID)` | `null` | Filter by department |
| `doctor_id` | `string (UUID)` | `null` | Filter by doctor |
| `period` | `string` | varies | Time period: `today`, `week`, `mtd`, `ytd`, `custom` |

---

## Intervention Categories (7-category system)

| Code | Label | Description |
|---|---|---|
| `OP_TO_IP` | OPD to IPD Conversion | Surgical conversion potential |
| `FOLLOWUP_DUE` | Follow-up Due | Return visits needed |
| `RX_REFILL` | Prescription Refill | Prescription refill opportunities |
| `DIAGNOSTICS_DUE` | Diagnostics Due | Diagnostic test opportunities |
| `ALLIED_HEALTH` | Allied Health | Allied health referrals |
| `RETENTION_RISK` | Retention Risk | Patient retention alerts |
| `QUALITY_RISK` | Quality & Safety | Clinical safety alerts |

---

## Intervention Status Progression

```
PENDING → CONTACTED → ACCEPTED → COMPLETED
                    ↘ DECLINED
         Any status → EXPIRED
```

---

## 1. GET `/api/v1/dashboard/intervention-summary`

Main dashboard metrics — summary totals, category breakdown, department/doctor breakdown.

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `period` | `string` | `mtd` | `today`, `week`, `mtd`, `ytd`, `custom` |
| `start_date` | `date` | `null` | Required when `period=custom` (format: `YYYY-MM-DD`) |
| `end_date` | `date` | `null` | Required when `period=custom` (format: `YYYY-MM-DD`) |
| `hospital_id` | `string (UUID)` | `null` | Filter by hospital |
| `department_id` | `string (UUID)` | `null` | Filter by department |
| `doctor_id` | `string (UUID)` | `null` | Filter by doctor |
| `priority_threshold` | `string` | `MEDIUM` | Minimum priority: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |

### Response

```json
{
  "total_patients": 12,
  "patients_with_interventions": 9,
  "percentage": 75.0,
  "revenue_potential": 810000.0,
  "by_period": {
    "today": {
      "total_patients": 3,
      "patients_with_interventions": 2,
      "percentage": 66.7,
      "revenue_potential": 150000.0
    },
    "week": { "..." : "..." },
    "mtd": { "..." : "..." },
    "ytd": { "..." : "..." }
  },
  "by_category": [
    {
      "category": "OP_TO_IP",
      "label": "OPD → IPD Conversion",
      "icon": "🏥",
      "color": "purple",
      "patient_count": 3,
      "intervention_count": 5,
      "revenue_potential": 250000.0,
      "aggregate_risk_score": 50.0,
      "risk_band": "MEDIUM",
      "intervention_types": ["surgery_referral", "admission_recommend"]
    }
  ],
  "high_risk_categories": ["RETENTION_RISK", "QUALITY_RISK"],
  "by_department": [
    {
      "id": "uuid",
      "name": "Cardiology",
      "specialization": "Cardiology",
      "by_category": {
        "OP_TO_IP": 2,
        "FOLLOWUP_DUE": 3
      },
      "total_at_risk": 5
    }
  ],
  "by_doctor": [
    {
      "id": "uuid",
      "name": "Dr. Smith",
      "specialization": "Cardiology",
      "by_category": {
        "OP_TO_IP": 1,
        "RX_REFILL": 2
      },
      "total_at_risk": 3
    }
  ],
  "filters_applied": {
    "period": "mtd",
    "start_date": null,
    "end_date": null,
    "hospital_id": "uuid-or-null",
    "department_id": null,
    "doctor_id": null,
    "priority_threshold": "MEDIUM"
  }
}
```

### Error Responses

| Status | Condition |
|---|---|
| `400` | Invalid UUID or parameter value |
| `500` | Internal server error |

---

## 2. GET `/api/v1/dashboard/patients`

Patient list with their interventions, filterable by category. Used for the **Patient Info** tab drill-down.

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `category` | `string` | `null` | One of the 7 categories. If omitted, returns all. |
| `hospital_id` | `string (UUID)` | `null` | Filter by hospital |
| `department_id` | `string (UUID)` | `null` | Filter by department |
| `doctor_id` | `string (UUID)` | `null` | Filter by doctor |
| `priority_threshold` | `string` | `MEDIUM` | Minimum priority: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `page` | `int` | `1` | Page number (min: 1) |
| `page_size` | `int` | `20` | Items per page (1–100) |
| `sort_by` | `string` | `priority_score` | `priority_score`, `revenue_potential`, `created_at` |
| `period` | `string` | `ytd` | `today`, `week`, `mtd`, `ytd` |

### Response

```json
{
  "patients": [
    {
      "patient_id": "uuid",
      "patient_name": "John Doe",
      "mrn": "MRN-12345",
      "doctor_name": "Dr. Smith",
      "last_consultation": "2026-01-28T10:30:00",
      "interventions": [
        {
          "id": "uuid",
          "code": "SURG-001",
          "category": "OP_TO_IP",
          "priority": "HIGH",
          "priority_score": 85,
          "take_up_likelihood": 70,
          "revenue_estimate": 50000.0,
          "trigger_reason": "Surgical admission recommended based on diagnosis",
          "action": "Schedule pre-admission workup",
          "days_since_generated": 3,
          "status": "PENDING"
        }
      ],
      "total_revenue_potential": 50000.0
    }
  ],
  "total_count": 45,
  "page": 1,
  "page_size": 20,
  "has_more": true
}
```

### Error Responses

| Status | Condition |
|---|---|
| `400` | Invalid category value or UUID |
| `500` | Internal server error |

---

## 3. GET `/api/v1/dashboard/outcome-metrics`

ROI and conversion tracking metrics. Used for measuring intervention program effectiveness.

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `hospital_id` | `string (UUID)` | `null` | Filter by hospital |
| `department_id` | `string (UUID)` | `null` | Filter by department |
| `doctor_id` | `string (UUID)` | `null` | Filter by doctor |
| `period` | `string` | `mtd` | `today`, `week`, `mtd`, `ytd` |

### Response

```json
{
  "total_interventions": 120,
  "by_status": {
    "PENDING": 45,
    "CONTACTED": 30,
    "ACCEPTED": 20,
    "DECLINED": 10,
    "COMPLETED": 12,
    "EXPIRED": 3
  },
  "conversion_rate": 26.7,
  "completion_rate": 10.0,
  "actual_revenue": 320000.0,
  "potential_revenue": 1200000.0,
  "revenue_capture_rate": 26.7
}
```

### Metric Definitions

| Metric | Formula |
|---|---|
| `conversion_rate` | (ACCEPTED + COMPLETED) / total * 100 |
| `completion_rate` | COMPLETED / total * 100 |
| `revenue_capture_rate` | actual_revenue / potential_revenue * 100 |

### Error Responses

| Status | Condition |
|---|---|
| `400` | Invalid UUID or parameter |
| `500` | Internal server error |

---

## 4. GET `/api/v1/dashboard/time-to-action`

Staff response time analytics. Used for performance benchmarking.

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `hospital_id` | `string (UUID)` | `null` | Filter by hospital |
| `period` | `string` | `mtd` | `today`, `week`, `mtd`, `ytd` |

> **Note:** This endpoint only supports `hospital_id` filtering (no department/doctor).

### Response

```json
{
  "avg_time_to_contact_hours": 4.5,
  "avg_time_to_completion_days": 3.2,
  "by_priority": {
    "CRITICAL": { "avg_contact_hours": 1.2, "avg_completion_days": 1.5 },
    "HIGH": { "avg_contact_hours": 3.0, "avg_completion_days": 2.8 },
    "MEDIUM": { "avg_contact_hours": 6.5, "avg_completion_days": 4.0 },
    "LOW": { "avg_contact_hours": 12.0, "avg_completion_days": 7.0 }
  },
  "by_category": {
    "OP_TO_IP": { "avg_contact_hours": 2.0, "avg_completion_days": 2.5 },
    "FOLLOWUP_DUE": { "avg_contact_hours": 5.0, "avg_completion_days": 3.0 },
    "RX_REFILL": { "avg_contact_hours": 8.0, "avg_completion_days": 5.0 }
  }
}
```

### Error Responses

| Status | Condition |
|---|---|
| `400` | Invalid UUID or parameter |
| `500` | Internal server error |

---

## 5. POST `/api/v1/dashboard/interventions/{intervention_id}/status`

Update the status of an intervention. Tracks outreach progress and revenue capture.

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `intervention_id` | `string (UUID)` | The intervention to update |

### Request Body

```json
{
  "status": "CONTACTED",
  "notes": "Called patient, scheduled follow-up for next week",
  "actual_revenue": null,
  "updated_by_user_id": "uuid-or-null",
  "updated_by_user_type": "coordinator"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `string` | **Yes** | `CONTACTED`, `ACCEPTED`, `DECLINED`, `COMPLETED`, `EXPIRED` |
| `notes` | `string` | No | Free-text notes about the status change |
| `actual_revenue` | `float` | No | Actual revenue captured (use when `status=COMPLETED`) |
| `updated_by_user_id` | `string (UUID)` | No | User making the update |
| `updated_by_user_type` | `string` | No | Default: `coordinator`. Options: `coordinator`, `nurse`, `admin` |

### Response

```json
{
  "success": true,
  "intervention_id": "uuid",
  "new_status": "CONTACTED",
  "message": "Intervention status updated to CONTACTED"
}
```

### Side Effects

| Status Set | Side Effect |
|---|---|
| `CONTACTED` | Records `first_contact_at` timestamp |
| `COMPLETED` | Records actual revenue for ROI calculation |

### Error Responses

| Status | Condition |
|---|---|
| `400` | Invalid status value or invalid UUID |
| `500` | Internal server error |

---

## 6. GET `/api/v1/doctors/hospitals`

List all active hospitals for filter dropdowns. **Requires authentication.**

### Auth

`Depends(get_current_client)` — any authenticated client (admin, web_app, mobile_app, ehr).

### Response

```json
{
  "success": true,
  "hospitals": [
    {
      "id": "uuid",
      "hospital_name": "Guru Hospital",
      "hospital_code": "GURU",
      "city": "Coimbatore",
      "state": "Tamil Nadu"
    }
  ],
  "count": 1
}
```

---

## 7. GET `/api/v1/doctors/list-all`

List all active doctors for filter dropdowns. **Requires authentication.**

### Auth

`Depends(get_current_client)` — any authenticated client.

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `hospital_id` | `string (UUID)` | `null` | Filter by hospital (client-side filtering also applied in frontend) |

### Response

```json
{
  "success": true,
  "doctors": [
    {
      "id": "uuid",
      "full_name": "Dr. Priya Sharma",
      "email": "priya@hospital.com",
      "specialization": "Cardiology",
      "hospital_id": "uuid",
      "ehr_type_id": "uuid-or-null"
    }
  ],
  "count": 15
}
```

---

## 8. GET `/api/v1/doctors/specializations`

List distinct specializations from active doctors. **Requires authentication.**

### Auth

`Depends(get_current_client)` — any authenticated client.

### Response

```json
{
  "success": true,
  "specializations": [
    "Cardiology",
    "General Practice",
    "Orthopedics",
    "Pediatrics",
    "Psychiatry"
  ],
  "count": 5
}
```

---

## 9. GET `/api/v1/dashboard/health`

Health check for the dashboard service. No auth required.

### Response

```json
{
  "status": "healthy",
  "service": "dashboard",
  "timestamp": "2026-01-30T12:00:00.000000"
}
```

---

## Frontend Client Reference

All dashboard API calls are made through `lib/dashboardApi.ts`. Key function-to-endpoint mapping:

| Function | Endpoint |
|---|---|
| `getInterventionSummary()` | `GET /api/v1/dashboard/intervention-summary` |
| `getPatientsByCategory()` | `GET /api/v1/dashboard/patients` |
| `getOutcomeMetrics()` | `GET /api/v1/dashboard/outcome-metrics` |
| `getTimeToActionMetrics()` | `GET /api/v1/dashboard/time-to-action` |
| `updateInterventionStatus()` | `POST /api/v1/dashboard/interventions/{id}/status` |
| `getHospitals()` | `GET /api/v1/doctors/hospitals` |
| `getDoctors()` | `GET /api/v1/doctors/list-all` |
| `getSpecializations()` | `GET /api/v1/doctors/specializations` |

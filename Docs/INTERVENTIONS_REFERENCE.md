# Interventions Reference

This document describes the 33 interventions generated after consultation insights analysis. Interventions are categorized into three main groups: **REVENUE**, **RETENTION**, and **QUALITY**.

## Overview

| Category | Count | Purpose |
|----------|-------|---------|
| REVENUE | 17 | Allied health referrals, clinical upsells, diagnostics |
| RETENTION | 9 | Dropoff prevention, emotional support, follow-up |
| QUALITY | 7 | Medication safety, documentation compliance |

---

## REVENUE Interventions (17)

Revenue interventions identify opportunities for additional services that benefit patient outcomes while generating hospital revenue.

### Allied Health Services (9)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `NUTRITIONAL_REFERRAL` | Nutritional Counseling Referral | Patient has condition requiring dietary guidance | HIGH | 80 |
| `PHYSIOTHERAPY_REFERRAL` | Physiotherapy Referral | Patient has condition that would benefit from physiotherapy | HIGH | 80 |
| `MENTAL_HEALTH_REFERRAL` | Mental Health Specialist Referral | Patient shows signs requiring mental health support | HIGH | 80 |
| `SLEEP_CLINIC_REFERRAL` | Sleep Study Consultation | Patient reports symptoms suggesting sleep disorder | MEDIUM | 60 |
| `CARDIAC_REHAB_REFERRAL` | Cardiac Rehabilitation Program | Patient had cardiac event and would benefit from cardiac rehabilitation | HIGH | 80 |
| `GENERAL_REHAB_REFERRAL` | General Rehabilitation Assessment | Patient requires rehabilitation following condition | MEDIUM | 60 |
| `HOMECARE_SERVICES` | Home Healthcare Services | Patient needs home-based care support | MEDIUM | 60 |
| `WELLNESS_PROGRAM` | Wellness and Prevention Program | Patient has lifestyle risk factors | LOW | 40 |
| `TREATMENT_EDUCATION_PROGRAM` | Patient Education Session | Patient shows difficulty understanding treatment | LOW | 40 |

**Trigger:** `allied_health_needs` assessment

### Clinical Upsell (4)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `SURGICAL_CONSULTATION` | Surgical Consultation | Patient condition may require surgical intervention | HIGH | 80 |
| `SECOND_OPINION_CONSULT` | Second Opinion Consultation | Complex diagnosis warrants second opinion | HIGH | 80 |
| `ALTERNATIVE_TREATMENT_CONSULT` | Alternative Treatment Review | Alternative treatment options available | MEDIUM | 60 |
| `CHRONIC_CARE_PROGRAM` | Chronic Care Management Program | Patient has chronic condition requiring ongoing management | MEDIUM | 60 |

**Trigger:** `clinical_severity` assessment

### Diagnostics & Rx (3)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `HOME_DIAGNOSTIC_COLLECTION` | Home Sample Collection | Patient requires tests - home collection available | MEDIUM | 60 |
| `PRESCRIPTION_REFILL_REMINDER` | Prescription Refill Service | Patient on multiple medications needs refill coordination | LOW | 40 |
| `RECURRING_TEST_SCHEDULE` | Scheduled Lab Panel | Patient needs periodic monitoring | LOW | 40 |

**Trigger:** `other_clinical_needs` assessment

**Note:** `PRESCRIPTION_REFILL_REMINDER` requires `med_count >= 3`

### Specialist Referral (1)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `SPECIALIST_REFERRAL_NEEDED` | Specialist Referral | Patient condition warrants specialist referral | MEDIUM | 60 |

**Trigger:** `care_quality_risk` assessment (`is_referral_risk`)

**Severity Adjustment:** Priority boosted to HIGH when severity is SEVERE/CRITICAL

---

## RETENTION Interventions (9)

Retention interventions aim to prevent patient dropoff and ensure continuity of care.

### Dropoff Prevention (6)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `COMPETITOR_COUNTEROFFER` | Competitive Retention Outreach | Patient mentioned considering other healthcare providers | CRITICAL | 95 |
| `ACCESS_BARRIER_RESOLUTION` | Access Barrier Resolution | Patient faces barriers to accessing care | HIGH | 80 |
| `FINANCIAL_ASSISTANCE` | Financial Assistance Connection | Patient expressed financial concerns with high dropoff risk | HIGH | 80 |
| `COMPLIANCE_SUPPORT` | Treatment Adherence Support | Patient shows low treatment adherence likelihood | MEDIUM | 60 |
| `FOLLOW_UP_REMINDER` | Follow-up Reminder Call | No specific follow-up scheduled with retention risk | LOW | 40 |
| `SATISFACTION_RECOVERY` | Service Recovery Callback | Patient dissatisfaction detected | HIGH | 80 |

**Trigger:** `patient_dropoff_risk` assessment

**Special Conditions:**
- `FINANCIAL_ASSISTANCE`: Requires `dropoff_probability >= 50`. **Skipped when severity is MILD/NONE**
- `COMPLIANCE_SUPPORT`: Priority boosted to HIGH when severity is SEVERE/CRITICAL
- `FOLLOW_UP_REMINDER`: Requires `risk_level MEDIUM/HIGH AND dropoff_probability >= 30`. Priority boosted to MEDIUM when severity is MODERATE+

### Emotional Support (1)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `EMOTIONAL_SUPPORT` | Emotional Support Follow-up | Patient showed emotional distress requiring support | MEDIUM | 60 |

**Trigger:** `anxiety_elevated_or_worsened` from emotional segments

**Severity Adjustment:** Priority boosted to HIGH when severity is SEVERE/CRITICAL

### Followup & Education (2)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `URGENT_FOLLOWUP_NEEDED` | Urgent Follow-up Required | Urgent follow-up needed for condition | HIGH | 80 |
| `PATIENT_EDUCATION_GAP` | Patient Education Gap | Patient lacks understanding of treatment plan | LOW | 40 |

**Trigger:** `care_quality_risk` assessment

**Severity Adjustments:**
- `URGENT_FOLLOWUP_NEEDED`: Priority boosted to CRITICAL when severity is SEVERE/CRITICAL
- `PATIENT_EDUCATION_GAP`: Priority boosted to MEDIUM when severity is MODERATE+

---

## QUALITY Interventions (7)

Quality interventions flag potential clinical safety issues and documentation gaps.

### Medication Safety (4)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `CONTRAINDICATION_ALERT` | Contraindication Alert | Potential contraindication detected | CRITICAL | 95 |
| `DRUG_INTERACTION_REVIEW` | Drug Interaction Review | Potential drug interaction detected | HIGH | 80 |
| `POLYPHARMACY_REVIEW` | Polypharmacy Review | Patient on multiple medications - polypharmacy risk | MEDIUM | 60 |
| `DOSAGE_VERIFICATION` | Dosage Verification | Dosage concern detected | HIGH | 80 |

**Trigger:** `care_quality_risk` assessment (medication safety flags)

### Documentation & Protocol (3)

| Code | Name | Description | Priority | Score |
|------|------|-------------|----------|-------|
| `MISSING_DIAGNOSIS_ALERT` | Missing Diagnosis Alert | Treatment prescribed without documented diagnosis | HIGH | 80 |
| `PROTOCOL_DEVIATION_REVIEW` | Protocol Deviation Review | Treatment deviates from standard protocol | MEDIUM | 60 |
| `INCOMPLETE_WORKUP_ALERT` | Incomplete Workup Alert | Recommended investigations not ordered | HIGH | 80 |

**Trigger:** `care_quality_risk` assessment (documentation flags)

---

## Priority Levels & Scores

| Priority | Score Range | Description |
|----------|-------------|-------------|
| CRITICAL | 95 | Immediate action required |
| HIGH | 80 | Action within 24 hours |
| MEDIUM | 60 | Action within 48-72 hours |
| LOW | 40 | Action within 1 week |

---

## Severity-Based Adjustments Summary

Several interventions have their priority dynamically adjusted based on clinical severity:

| Intervention | Adjustment |
|--------------|------------|
| `FINANCIAL_ASSISTANCE` | **Skipped** when severity is MILD/NONE |
| `COMPLIANCE_SUPPORT` | Priority → HIGH when severity is SEVERE/CRITICAL |
| `FOLLOW_UP_REMINDER` | Priority → MEDIUM when severity is MODERATE+ |
| `EMOTIONAL_SUPPORT` | Priority → HIGH when severity is SEVERE/CRITICAL |
| `URGENT_FOLLOWUP_NEEDED` | Priority → CRITICAL when severity is SEVERE/CRITICAL |
| `PATIENT_EDUCATION_GAP` | Priority → MEDIUM when severity is MODERATE+ |
| `SPECIALIST_REFERRAL_NEEDED` | Priority → HIGH when severity is SEVERE/CRITICAL |

---

## Take-Up Likelihood Prediction

Each intervention includes a `take_up_likelihood` score (0-100) that predicts patient acceptance probability. This is calculated using:

### Category Weights

| Category | Severity | Anxiety | Financial | Compliance |
|----------|----------|---------|-----------|------------|
| REVENUE | 15% | 20% | 40% | 25% |
| RETENTION | 15% | 35% | 15% | 35% |
| QUALITY | 50% | 10% | 10% | 30% |

### Priority Adjustment Based on Take-Up

| Take-Up Likelihood | Modifier |
|--------------------|----------|
| ≥ 70% (High) | Score × 1.15 |
| 40-69% (Medium) | Score × 1.0 |
| < 40% (Low) | Score × 0.85 |

---

## Database Schema

Interventions are stored in the `intervention_definitions` table:

```sql
CREATE TABLE intervention_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intervention_code TEXT NOT NULL UNIQUE,
    intervention_name TEXT NOT NULL,
    description TEXT,
    priority_level TEXT NOT NULL,
    priority_score INTEGER NOT NULL,
    category TEXT NOT NULL, -- REVENUE, RETENTION, QUALITY
    trigger_conditions JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Related Files

- `backend/services/intervention_orchestrator.py` - Main orchestration logic
- `backend/services/revenue_interventions_service.py` - Revenue intervention triggers
- `backend/services/retention_interventions_service.py` - Retention intervention triggers
- `backend/services/quality_interventions_service.py` - Quality intervention triggers
- `backend/services/take_up_prediction_service.py` - Take-up likelihood calculation
- `references/intervention_config.json` - ICD-10 severity configuration

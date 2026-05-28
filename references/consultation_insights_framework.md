# Consultation Insights Framework

> Revenue Intelligence & Patient Retention Insights for Hospital Management

## Overview

1hat extracts actionable insights from every consultation to help hospital management:
- **Increase revenue** through conversion opportunities
- **Improve retention** by identifying churn risks early
- **Optimize operations** with data-driven decisions

**Primary Audience:** Hospital CEO / Management  
**Delivery:** Real-time alerts + Configurable batch reports

---

## Insight Categories

### 1. Revenue Conversion Opportunities

| Insight | Signals Detected | Revenue Impact | Urgency |
|---------|------------------|----------------|---------|
| **Surgical Likelihood (OP→IP)** | Surgery keywords in treatment plan, condition severity, "might need operation" | IP admission | This month |
| **Diagnostics Before Follow-up** | "Get tests done", specific test names, "before next visit" | Lab/Radiology | This week |
| **Chronic Prescription Refill** | Chronic diagnosis + ongoing medications + follow-up scheduled | Pharmacy | Ongoing |
| **Recurring Diagnostics** | Chronic condition + monitoring tests (HbA1c, lipid panel, creatinine) | Lab | Monthly/Quarterly |
| **Specialist Referral** | Symptoms outside current specialty, "you should also see a..." | Multi-department | This week |
| **Procedure Upsell** | Conservative treatment discussed but procedure is option | Procedure revenue | This month |
| **Allied Services Referral** | Diet, exercise, physio, counseling needs mentioned | Allied health | This week |
| **Health Package Fit** | Age + risk factors + no recent comprehensive checkup | Preventive care | This month |
| **Second Opinion Conversion** | Patient came for second opinion, shows trust signals | Competitor capture | Immediate |
| **Corporate/Insurance Patient** | Insurance mentioned, corporate employee, TPA name | Higher realization | Immediate |

---

### 2. Patient Retention Risk Signals

| Insight | Signals Detected | Risk Level | Action Window |
|---------|------------------|------------|---------------|
| **Churn Risk - Financial** | High financial concern + asks about costs + cheaper alternatives | High | Immediate |
| **Churn Risk - Competitor** | Mentions other hospital, "I was told elsewhere..." | High | Immediate |
| **Churn Risk - Dissatisfaction** | Anxiety increased post-consultation, concerns unaddressed | High | Same day |
| **Churn Risk - Access** | Distance, travel difficulty, parking, wait time complaints | Medium | This week |
| **Follow-up Dropout Risk** | Low compliance + no follow-up scheduled + vague instructions | High | Same day |
| **Price Sensitivity Alert** | Financial concern high + cost questions + EMI inquiry | Medium | Before checkout |
| **Doctor Rapport Weak** | Short consultation + questions unanswered + anxiety unchanged | Medium | This week |
| **Treatment Confusion** | Complex plan + low health literacy + no written summary | Medium | Same day |

---

### 3. High-Value Patient Identification

| Insight | Signals Detected | Strategic Value |
|---------|------------------|-----------------|
| **VIP / High LTV Patient** | Multiple chronic conditions + multiple specialists + frequent visits | Prioritize retention |
| **Family Influence** | Mentions family members' health issues, decision-maker for family | Family acquisition |
| **Corporate Decision-Maker** | Senior role + corporate insurance + mentions employee health | B2B opportunity |
| **Referral Potential** | Highly satisfied + good rapport + expresses gratitude | Word-of-mouth growth |
| **Medical Tourism** | Out-of-town + complex procedure + quality-seeking signals | High-value conversion |

---

### 4. Service Line Growth Opportunities

| Insight | Signals Detected | Target Service |
|---------|------------------|----------------|
| **Mental Health Add-on** | High anxiety + stress + sleep issues + mood concerns | Psychiatry/Counseling |
| **Nutrition Consultation** | Diabetes, obesity, cardiac + diet discussion | Dietitian |
| **Physiotherapy Pathway** | MSK diagnosis + mobility issues + post-surgical + chronic pain | Rehab services |
| **Home Care Candidate** | Elderly + chronic + mobility issues + caregiver present | Home healthcare |
| **Wellness Program Fit** | Lifestyle diseases + prevention discussion + health-conscious | Wellness packages |
| **Fertility Services** | Age + gynec visit + conception mentions | Fertility clinic |
| **Sleep Study Candidate** | Snoring + fatigue + obesity + hypertension | Sleep lab |
| **Cardiac Rehab Eligible** | Post-MI, post-CABG, heart failure | Rehab program |
| **Diabetes Education** | New diabetes + poor understanding + lifestyle gaps | DSME program |

---

### 5. Operational Intelligence

| Insight | Signals Detected | Operational Value |
|---------|------------------|-------------------|
| **Consultation Complexity Mismatch** | Simple case in specialist slot, complex in short slot | Scheduling optimization |
| **Extended Consultation Needed** | Multiple concerns, complex history, first visit | Time slot planning |
| **Pre-consultation Workup Missing** | Doctor asks for tests that should have been done before | Process improvement |
| **Language Support Needed** | Language difficulty in consultation | Service quality |
| **Patient Education Gap** | Same questions repeated across patients | Content creation |

---

### 6. Quality & Safety Alerts

| Insight | Signals Detected | Impact |
|---------|------------------|--------|
| **Medication Issue** | Conflicting medications, polypharmacy risk | Patient safety |
| **Missed Red Flag** | Serious symptoms not addressed | Quality concern |
| **Incomplete Treatment Plan** | Diagnosis without clear next steps | Care quality |
| **Follow-up Gap Risk** | Serious condition + no follow-up scheduled | Continuity gap |
| **Expectation Mismatch** | Patient expected X, doctor recommended Y | Satisfaction risk |

---

## Insight Data Structure

```json
{
  "consultation_id": "abc123",
  "patient_id": "patient_456",
  "doctor_id": "doc_789",
  "department": "orthopedics",
  "timestamp": "2024-12-24T10:30:00Z",
  
  "insights": [
    {
      "type": "revenue_opportunity",
      "name": "surgical_likelihood",
      "confidence": 0.85,
      "revenue_category": "IP_conversion",
      "estimated_value": "high",
      "urgency": "this_month",
      "signals": [
        "Diagnosis: severe knee osteoarthritis",
        "Doctor mentioned: 'surgery might be needed'",
        "Conservative treatment failing"
      ],
      "action": "Schedule surgery counselor follow-up within 1 week",
      "target_team": "surgery_coordinator",
      "alert_priority": "high"
    }
  ],
  
  "summary": {
    "total_insights": 3,
    "revenue_opportunities": 2,
    "retention_risks": 1,
    "immediate_actions": 1
  }
}
```

---

## Real-Time Alerts

### Alert Configuration

| Alert Type | Default Trigger | Delivery Channel | Target Role |
|------------|-----------------|------------------|-------------|
| **High Churn Risk** | Churn score ≥ 7 | Push + SMS | Care Coordinator |
| **Financial Concern** | Score ≥ 8 | Push | Billing Desk |
| **Surgical Conversion** | Likelihood ≥ 0.8 | Push | Surgery Coordinator |
| **VIP Patient** | LTV score ≥ 9 | Push | Front Desk Manager |
| **Dissatisfaction** | Post-anxiety > Pre-anxiety | Push | Patient Relations |
| **Specialist Referral** | Confidence ≥ 0.7 | Push | Referral Desk |

### Alert Payload

```json
{
  "alert_id": "alert_001",
  "type": "churn_risk_high",
  "priority": "immediate",
  "timestamp": "2024-12-24T10:35:00Z",
  
  "patient": {
    "id": "patient_456",
    "name": "Rajesh Kumar",
    "phone": "+91-98xxx-xxxxx",
    "current_location": "OP Block - Room 204"
  },
  
  "context": {
    "doctor": "Dr. Sharma",
    "department": "Cardiology",
    "consultation_end": "10:32:00"
  },
  
  "insight": {
    "name": "Financial Concern - High",
    "confidence": 0.88,
    "signals": [
      "Asked about treatment cost multiple times",
      "Mentioned insurance won't cover",
      "Financial concern score: 9/10"
    ]
  },
  
  "recommended_action": "Intercept before checkout - offer EMI options",
  "action_deadline": "10:45:00",
  "target_team": "billing_counselor"
}
```

### User-Configurable Alert Settings

```json
{
  "user_id": "ceo_001",
  "alert_preferences": {
    "channels": ["push", "email", "sms"],
    "quiet_hours": {"start": "22:00", "end": "07:00"},
    "minimum_priority": "high",
    
    "subscribed_alerts": [
      {"type": "surgical_conversion", "threshold": 0.75},
      {"type": "churn_risk", "threshold": 7},
      {"type": "vip_patient", "enabled": true},
      {"type": "daily_summary", "time": "08:00"}
    ],
    
    "departments": ["all"],
    "value_threshold": "high"
  }
}
```

---

## Batch Reports

### Report Types

| Report | Frequency | Contents |
|--------|-----------|----------|
| **Daily Executive Summary** | Daily 8 AM | Yesterday's insights, revenue pipeline, churn risks |
| **Weekly Revenue Report** | Monday 9 AM | Conversion rates, revenue by category, trends |
| **Monthly Strategic Review** | 1st of month | Department performance, growth opportunities, retention metrics |
| **Custom Date Range** | On-demand | User-selected metrics for chosen period |

### Daily Executive Summary Structure

```
📊 DAILY INSIGHTS SUMMARY - {date}
Hospital: {hospital_name}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 REVENUE OPPORTUNITIES
├── Surgical conversions pending: {count} (₹{estimated_value})
├── Diagnostics revenue potential: {count} patients (₹{estimated_value})
├── Specialist referrals identified: {count}
├── Allied services opportunities: {count}
└── Total pipeline value: ₹{total}

⚠️ RETENTION ALERTS
├── High churn risk patients: {count}
├── Financial concern cases: {count}
├── Dissatisfied patients: {count}
└── Follow-up dropouts predicted: {count}

⭐ HIGH-VALUE PATIENTS
├── VIP patients seen: {count}
├── Corporate patients: {count}
└── Medical tourism: {count}

🏥 DEPARTMENT HIGHLIGHTS
├── {dept_1}: {key_insight}
├── {dept_2}: {key_insight}
└── {dept_3}: {key_insight}

📋 TODAY'S PRIORITY ACTIONS
1. {action_1} - {patient/context}
2. {action_2} - {patient/context}
3. {action_3} - {patient/context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Weekly Revenue Report Structure

```
📊 WEEKLY REVENUE INTELLIGENCE - Week {week_number}
Period: {start_date} to {end_date}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 REVENUE CONVERSION SUMMARY

| Category              | Opportunities | Converted | Conversion % | Value (₹)  |
|-----------------------|---------------|-----------|--------------|------------|
| OP → IP (Surgical)    | {n}           | {n}       | {%}          | {value}    |
| Diagnostics           | {n}           | {n}       | {%}          | {value}    |
| Pharmacy/Refills      | {n}           | {n}       | {%}          | {value}    |
| Specialist Referrals  | {n}           | {n}       | {%}          | {value}    |
| Allied Services       | {n}           | {n}       | {%}          | {value}    |
| **TOTAL**             | {n}           | {n}       | {%}          | {value}    |

📉 RETENTION METRICS

| Metric                      | This Week | Last Week | Trend |
|-----------------------------|-----------|-----------|-------|
| Churn risk patients         | {n}       | {n}       | {↑↓}  |
| Intervention success rate   | {%}       | {%}       | {↑↓}  |
| Follow-up completion rate   | {%}       | {%}       | {↑↓}  |
| Patient satisfaction proxy  | {score}   | {score}   | {↑↓}  |

🏆 TOP PERFORMING

- Highest conversion dept: {department} ({%})
- Most referrals generated: Dr. {name} ({count})
- Best retention rate: {department} ({%})

⚠️ NEEDS ATTENTION

- Lowest conversion: {department} ({%})
- Highest churn risk: {department} ({count} patients)
- Most missed opportunities: {category}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Report Configuration API

```json
{
  "report_config": {
    "report_type": "custom",
    "date_range": {
      "start": "2024-12-01",
      "end": "2024-12-24"
    },
    "filters": {
      "departments": ["cardiology", "orthopedics"],
      "insight_types": ["revenue_opportunity", "churn_risk"],
      "minimum_confidence": 0.7,
      "minimum_value": "medium"
    },
    "grouping": "department",
    "include_patient_details": false,
    "format": "pdf",
    "delivery": {
      "email": ["ceo@hospital.com"],
      "schedule": "immediate"
    }
  }
}
```

---

## CEO Dashboard Metrics

### Primary KPIs (Top of Dashboard)

| Metric | Description | Target |
|--------|-------------|--------|
| **Revenue Pipeline** | Total estimated value of identified opportunities | ₹{X} lakhs/month |
| **Conversion Rate** | % of opportunities converted to revenue | ≥40% |
| **Churn Risk Index** | Weighted average of at-risk patients | ≤15% |
| **Intervention Success** | % of at-risk patients retained after intervention | ≥70% |

### Secondary Metrics

| Category | Metrics Tracked |
|----------|-----------------|
| **Revenue** | By department, by category, by doctor, trend over time |
| **Retention** | Churn rate, follow-up completion, satisfaction proxy |
| **Operations** | Referral completion rate, intervention response time |
| **Growth** | New service line adoption, cross-sell success |

### Drill-Down Capability

```
CEO Dashboard
├── Revenue Pipeline: ₹45L
│   ├── By Department
│   │   ├── Cardiology: ₹18L (click to see patients)
│   │   ├── Orthopedics: ₹12L
│   │   └── ...
│   ├── By Category
│   │   ├── Surgical: ₹25L
│   │   ├── Diagnostics: ₹12L
│   │   └── ...
│   └── By Time Period (trend chart)
│
├── Churn Risk: 12% (32 patients)
│   ├── By Risk Factor
│   │   ├── Financial: 18 patients
│   │   ├── Dissatisfaction: 8 patients
│   │   └── ...
│   └── Action Status
│       ├── Pending intervention: 12
│       ├── In progress: 15
│       └── Resolved: 5
│
└── Today's Priority Actions: 8 items
    └── (Actionable list with assign capability)
```

---

## Implementation Priority

### Phase 1 (MVP)
- [ ] Surgical likelihood detection
- [ ] Diagnostics opportunity detection
- [ ] Basic churn risk (financial + compliance)
- [ ] Daily summary report
- [ ] Real-time high-priority alerts

### Phase 2
- [ ] All revenue opportunity types
- [ ] Full retention risk signals
- [ ] Weekly reports
- [ ] Department-level dashboards
- [ ] Alert configuration UI

### Phase 3
- [ ] Predictive models (ML-based confidence)
- [ ] ROI tracking (opportunity → actual revenue)
- [ ] Benchmarking across hospitals
- [ ] Custom insight rules engine

---

## Appendix: Signal Detection Keywords

### Surgical Likelihood
```
"surgery", "operation", "surgical", "procedure needed",
"might need to operate", "conservative treatment not working",
"replacement", "bypass", "resection", "implant"
```

### Financial Concern
```
"cost", "expensive", "afford", "insurance", "coverage",
"cheaper", "EMI", "payment plan", "discount", "package"
```

### Churn Risk
```
"other hospital", "second opinion", "not sure", "think about it",
"far from home", "difficult to come", "wait time", "rushed"
```

### Specialist Referral
```
"also see", "refer you to", "specialist opinion",
"beyond my expertise", "need a {specialty} consultation"
```

---

*Document Version: 1.0*  
*Last Updated: December 2024*  
*Author: 1hat Health*

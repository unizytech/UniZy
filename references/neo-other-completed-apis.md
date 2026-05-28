# Transcription Integration API v2 - Complete Documentation

## Overview

Complete API v2 documentation for all Transcription Integration endpoints with clean nested structures and no duplicate fields.

**Version:** 2.0  
**Last Updated:** 2026-02-05

---

## Table of Contents

1. [Neonatal Proforma API v2](#1-neonatal-proforma-api-v2)
2. [NICU Admission API v2](#2-nicu-admission-api-v2)
3. [OP Neonatal API v2](#3-op-neonatal-api-v2)
4. [NICU Discharge API v2](#4-nicu-discharge-api-v2)
5. [Common Notes](#common-notes)

---

## 1. Neonatal Proforma API v2

**Endpoint:** `POST /v2/store-neonatal-proforma-transcribed-data`  
**Method:** [storeTranscribedNeonatalProformaDataV2](file:///var/www/html/neopaed/app/Http/Controllers/TranscribtionIntegrationController.php#1298-1314)

### Complete JSON Payload

```json
{
  "uhid": "NH123456",
  "baby": {
    "uhid": "NH123456",
    "name": "Baby of Priya",
    "dob": "2026-02-05",
    "tob": "14:30:00",
    "sex": "Male",
    "birthWeight": 2.5,
    "birthStatus": "Inborn",
    "birthOrder": "1",
    "bloodGroup": "O+",
    "gestation": {
      "weeks": 37,
      "days": 2
    }
  },
  "mother": {
    "name": {
      "first": "Priya"
    },
    "gravida": 2,
    "para": 1,
    "liveBirth": 1,
    "abortion": 0,
    "bloodGroup": "O+",
    "mobile": "9876543210"
  },
  "maternal": {
    "consanguinity": "No",
    "lmp": "2025-05-01",
    "edd": {
      "byUsg": "2026-02-05",
      "byDate": "2026-02-06"
    },
    "history": {
      "booked": "Yes",
      "bookedPlace": "Government Hospital",
      "supervised": "Yes",
      "placeOfSupervision": "Same Hospital",
      "antenatalSteroids": "Yes",
      "steroidType": "Betamethasone",
      "antenatalMgso4": "No",
      "thyroidStatus": "Normal",
      "hiv": "Negative",
      "hepatitisB": "Negative",
      "vdrl": "Negative"
    },
    "labour": {
      "status": "Spontaneous",
      "nature": "Normal"
    }
  },
  "delivery": {
    "mode": "Normal Vaginal Delivery",
    "presentation": "Vertex",
    "cordBlood": {
      "status": "Done",
      "ph": 7.32,
      "hco3": 22,
      "be": -2
    }
  },
  "birthDetails": {
    "dateTime": "2026-02-05 14:30:00",
    "length": 48,
    "ofc": 33,
    "apgar": {
      "status": "Yes",
      "matrix": {
        "min1": {
          "colour": 2,
          "hr": 2,
          "reflex": 2,
          "tone": 2,
          "respiration": 2,
          "total": 10
        },
        "min5": {
          "colour": 2,
          "hr": 2,
          "reflex": 2,
          "tone": 2,
          "respiration": 2,
          "total": 10
        }
      }
    },
    "vitaminK": {
      "status": "Given",
      "dose": "1mg",
      "route": "IM"
    }
  },
  "examination": {
    "general": {
      "pallor": "No",
      "jaundice": "No",
      "temperature": 36.8
    },
    "vitals": {
      "hr": 140,
      "rr": 45,
      "spo2": 98
    }
  }
}
```

---

## 2. NICU Admission API v2

**Endpoint:** `POST /v2/store-nicu-admission-transcribed-data`  
**Method:** `storeTranscribedNicuAdmissionDataV2`

### Complete JSON Payload

```json
{
  "uhid": "NH123456",
  "baby": {
    "uhid": "NH123456",
    "name": "Baby of Lakshmi",
    "dob": "2026-02-04",
    "tob": "10:15:00",
    "sex": "Female",
    "birthWeight": 1.8,
    "birthStatus": "Outborn",
    "bloodGroup": "B+",
    "gestation": {
      "weeks": 32,
      "days": 4
    }
  },
  "mother": {
    "name": {
      "first": "Lakshmi"
    },
    "gravida": 1,
    "para": 1,
    "liveBirth": 1,
    "abortion": 0,
    "bloodGroup": "B+",
    "mobile": "9988776655"
  },
  "referredBy": "Dr. Kumar",
  "referralReason": "Respiratory distress",
  "admission": {
    "visitNumber": "IP/2402001",
    "admissionDate": "2026-02-05 08:30:00",
    "typeOfCare": "Level III",
    "admissionWt": 1.75,
    "surgeon": "Dr. Sharma",
    "hospitalName": "City General Hospital",
    "seenBy": [
      {
        "id": "101",
        "name": "Dr. Patel"
      },
      {
        "id": "102",
        "name": "Dr. Reddy"
      }
    ],
    "admittedFrom": "Emergency",
    "majorComplaints": "Respiratory distress, poor feeding",
    "ventilation": "Yes",
    "mode": "SIMV",
    "retractions": "Moderate",
    "airEntry": "Bilateral reduced",
    "chestMovement": "Asymmetrical",
    "hr": 165,
    "systolicBp": 55,
    "diastolic_bp": 35,
    "meanBP": 42,
    "centralPulses": "Present",
    "peripheralPulses": "Weak",
    "femoralPulses": "Palpable",
    "s1s2": "Normal",
    "murmur": "No"
  },
  "medicalHistory": {
    "smoking": "No",
    "alcohol": "No",
    "tobacco": "No"
  },
  "babyDetails": {
    "descriptionOfResuscitation": "Bag and mask ventilation for 3 minutes",
    "ventilationRequired": "Yes",
    "surfactantGiven": "Yes",
    "surfactantType": "Poractant alfa",
    "dose": "200 mg/kg",
    "dateofAdministration": "2026-02-05",
    "ageAfterBirth": "2 hours",
    "deliveryCpap": "Yes",
    "airFlow": "8 L/min",
    "oxgenFlow": "5 L/min",
    "transferFiO2": "40%"
  },
  "pregnancy": {
    "multiplePregnancy": "No",
    "pregnancyComplications": "Preeclampsia"
  },
  "procedures": [
    {
      "name": "Umbilical line insertion",
      "date": "2026-02-05",
      "time": "09:00:00"
    },
    {
      "name": "Chest X-ray",
      "date": "2026-02-05",
      "time": "09:30:00"
    }
  ],
  "diagnosis": [
    {
      "code": "P22.0",
      "description": "Respiratory distress syndrome of newborn"
    },
    {
      "code": "P07.3",
      "description": "Preterm newborn"
    }
  ],
  "crib_2": {
    "score": 8,
    "components": {
      "birthWeight": 2,
      "gestationalAge": 3,
      "congenitalMalformations": 0,
      "baseExcess": 2,
      "temperature": 1
    }
  },
  "snappe_2": {
    "score": 15,
    "components": {
      "meanBP": 3,
      "lowestTemp": 2,
      "po2FiO2": 4,
      "lowestPh": 3,
      "seizures": 0,
      "urine": 3
    }
  }
}
```

### Response

**Success (200):**
```json
{
  "type": "success",
  "message": "NICU admission details updated"
}
```

**Error (500):**
```json
{
  "type": "error",
  "message": "Error while storing NICU admission details"
}
```

---

## 3. OP Neonatal API v2

**Endpoint:** `POST /v2/store-op-neonatal-transcribed-data`  
**Method:** `storeTranscribedOpNeonatalDataV2`

### Complete JSON Payload

```json
{
  "uhid": "NH123457",
  "baby": {
    "uhid": "NH123457",
    "name": "Baby of Meera",
    "dob": "2026-01-15",
    "sex": "Male",
    "birthWeight": 3.2,
    "birthStatus": "Inborn",
    "bloodGroup": "A+",
    "gestation": {
      "weeks": 39,
      "days": 1
    }
  },
  "mother": {
    "name": {
      "first": "Meera",
      "last": "Sharma"
    },
    "age": 28,
    "gravida": 2,
    "para": 2,
    "liveBirth": 2,
    "abortion": 0,
    "bloodGroup": "A+",
    "mobile": "9876543210",
    "address": "123 Main Street, Chennai"
  },
  "partner": {
    "name": "Rajesh Sharma",
    "age": 32,
    "occupation": "Engineer",
    "mobile": "9876543211"
  },
  "patient": {
    "currentAge": {
      "years": 0,
      "months": 0,
      "days": 21
    },
    "correctedAge": {
      "years": 0,
      "months": 0,
      "days": 21
    },
    "weight": 3.5,
    "length": 52,
    "ofc": 35,
    "complaints": "Routine follow-up",
    "presentingComplaints": "No complaints",
    "historyOfPresentingComplaints": "Baby feeding well, no issues"
  },
  "eligibility": {
    "highrisk": "No",
    "nicu": "No",
    "birthAsphyxia": "No",
    "preterm": "No",
    "lowBirthWeight": "No"
  },
  "medicalHistory": {
    "pastHistory": "Uneventful",
    "birthHistory": "Normal vaginal delivery",
    "immunization": "Up to date",
    "developmentalHistory": "Age appropriate",
    "familyHistory": "No significant history"
  },
  "examination": {
    "general": {
      "appearance": "Active and alert",
      "pallor": "No",
      "jaundice": "No",
      "cyanosis": "No",
      "edema": "No"
    },
    "vitals": {
      "hr": 135,
      "rr": 42,
      "temperature": 36.9,
      "spo2": 99
    },
    "systemic": {
      "respiratory": "Clear breath sounds bilaterally",
      "cardiovascular": "S1 S2 normal, no murmur",
      "abdomen": "Soft, non-tender",
      "cns": "Normal tone and activity",
      "skin": "Normal"
    }
  },
  "followUp": {
    "nextVisitDate": "2026-03-05",
    "nextVisitReason": "Routine check-up",
    "advice": "Continue breastfeeding, maintain hygiene"
  },
  "medications": [
    {
      "name": "Vitamin D drops",
      "dose": "400 IU",
      "frequency": "Once daily",
      "duration": "Ongoing",
      "route": "Oral"
    }
  ],
  "immunization": [
    {
      "vaccine": "BCG",
      "date": "2026-01-15",
      "site": "Left upper arm",
      "batchNumber": "BCG2026001"
    },
    {
      "vaccine": "Hepatitis B",
      "date": "2026-01-15",
      "site": "Right thigh",
      "batchNumber": "HEPB2026001"
    },
    {
      "vaccine": "OPV-0",
      "date": "2026-01-15",
      "batchNumber": "OPV2026001"
    }
  ]
}
```

### Response

**Success (200):**
```json
{
  "type": "success",
  "message": "OP Neonatal details updated"
}
```

**Error (500):**
```json
{
  "type": "error",
  "message": "Error while storing OP neonatal details"
}
```

---

## 4. NICU Discharge API v2

**Endpoint:** `POST /v2/store-nicu-discharge-transcribed-data`  
**Method:** `storeTranscribedNicuDischargeDataV2`

### Complete JSON Payload

```json
{
  "uhid": "NH123456",
  "visitNumber": "IP/2402001",
  "baby": {
    "uhid": "NH123456",
    "name": "Baby of Lakshmi"
  },
  "discharge": {
    "dischargeDate": "2026-02-15",
    "dischargeTime": "14:00:00",
    "dischargeWeight": 2.1,
    "dischargeLength": 45,
    "dischargeOfc": 32,
    "dischargeType": "Home",
    "dischargeStatus": "Improved",
    "outcome": "Alive",
    "feedingAtDischarge": "Exclusive breastfeeding",
    "modeOfFeeding": "Direct breastfeeding"
  },
  "summary": {
    "admissionDate": "2026-02-05",
    "lengthOfStay": 10,
    "admissionDiagnosis": [
      {
        "code": "P22.0",
        "description": "Respiratory distress syndrome of newborn"
      },
      {
        "code": "P07.3",
        "description": "Preterm newborn"
      }
    ],
    "dischargeDiagnosis": [
      {
        "code": "P22.0",
        "description": "Respiratory distress syndrome - resolved"
      }
    ],
    "clinicalCourse": "Baby admitted with respiratory distress. Started on CPAP, later intubated and given surfactant. Extubated on day 3. Gradually improved and maintained on room air by day 7. Feeding established by day 8.",
    "complications": [
      {
        "name": "Patent ductus arteriosus",
        "treatment": "Conservative management",
        "outcome": "Closed spontaneously"
      }
    ],
    "procedures": [
      {
        "name": "Endotracheal intubation",
        "date": "2026-02-05",
        "indication": "Respiratory failure"
      },
      {
        "name": "Surfactant administration",
        "date": "2026-02-05",
        "indication": "RDS"
      },
      {
        "name": "Umbilical catheterization",
        "date": "2026-02-05",
        "indication": "Vascular access"
      }
    ]
  },
  "investigations": {
    "bloodTests": [
      {
        "test": "Complete Blood Count",
        "date": "2026-02-05",
        "results": {
          "hb": "14.5 g/dL",
          "wbc": "12000/cumm",
          "platelets": "180000/cumm"
        }
      },
      {
        "test": "CRP",
        "date": "2026-02-06",
        "result": "8 mg/L"
      }
    ],
    "imaging": [
      {
        "test": "Chest X-ray",
        "date": "2026-02-05",
        "findings": "Ground glass appearance, air bronchograms"
      },
      {
        "test": "Cranial ultrasound",
        "date": "2026-02-08",
        "findings": "Normal study"
      }
    ],
    "screening": {
      "newbornScreening": {
        "done": "Yes",
        "date": "2026-02-07",
        "result": "Normal"
      },
      "hearingScreening": {
        "done": "Yes",
        "date": "2026-02-14",
        "result": "Pass"
      },
      "rop": {
        "done": "Yes",
        "date": "2026-02-12",
        "result": "No ROP"
      }
    }
  },
  "medications": {
    "dischargeMedications": [
      {
        "name": "Iron supplements",
        "dose": "2 mg/kg/day",
        "frequency": "Once daily",
        "duration": "3 months",
        "route": "Oral"
      },
      {
        "name": "Vitamin D",
        "dose": "400 IU",
        "frequency": "Once daily",
        "duration": "Ongoing",
        "route": "Oral"
      }
    ],
    "antibiotics": [
      {
        "name": "Ampicillin",
        "dose": "100 mg/kg/dose",
        "frequency": "Q12H",
        "startDate": "2026-02-05",
        "endDate": "2026-02-12",
        "indication": "Rule out sepsis"
      },
      {
        "name": "Gentamicin",
        "dose": "4 mg/kg/dose",
        "frequency": "Q24H",
        "startDate": "2026-02-05",
        "endDate": "2026-02-12",
        "indication": "Rule out sepsis"
      }
    ]
  },
  "followUp": {
    "nextVisitDate": "2026-02-22",
    "nextVisitLocation": "NICU Follow-up Clinic",
    "followUpRequired": [
      "Weight monitoring",
      "Developmental assessment",
      "ROP screening if needed",
      "Hearing assessment"
    ],
    "advice": [
      "Exclusive breastfeeding",
      "Maintain hygiene",
      "Watch for danger signs",
      "Continue medications as prescribed",
      "Follow immunization schedule"
    ],
    "dangerSigns": [
      "Difficulty breathing",
      "Poor feeding",
      "Lethargy",
      "Fever",
      "Jaundice"
    ]
  },
  "immunization": [
    {
      "vaccine": "BCG",
      "date": "2026-02-10",
      "site": "Left upper arm",
      "batchNumber": "BCG2026001"
    },
    {
      "vaccine": "Hepatitis B",
      "date": "2026-02-10",
      "site": "Right thigh",
      "batchNumber": "HEPB2026001"
    },
    {
      "vaccine": "OPV-0",
      "date": "2026-02-10",
      "batchNumber": "OPV2026001"
    }
  ]
}
```

### Response

**Success (200):**
```json
{
  "type": "success",
  "message": "NICU discharge details updated"
}
```

**Error (500):**
```json
{
  "type": "error",
  "message": "Error while storing NICU discharge details"
}
```

---

## Common Notes

### Date/Time Formats
- **Date:** `YYYY-MM-DD` (e.g., "2026-02-05")
- **Time:** `HH:mm:ss` (e.g., "14:30:00")
- **DateTime:** `YYYY-MM-DD HH:mm:ss` (e.g., "2026-02-05 14:30:00")

### Required Fields
- **uhid** (string) - Required for all endpoints
- **visitNumber** - Required for NICU Discharge

### Optional Fields
- All other fields are optional
- Send `null` for unknown/not applicable values
- Send empty arrays `[]` for array fields with no data

### Nested Structure Benefits
1. **Clarity** - Each field has exactly ONE way to send it
2. **Organization** - Related fields grouped logically
3. **Maintainability** - Easier to understand and modify
4. **Consistency** - Follows modern API design practices

### Authentication
- All endpoints require proper authentication
- User ID for transcription operations is set to `7` (transcription_user)

### Error Handling
- All endpoints return JSON responses
- Success responses have `type: "success"`
- Error responses have `type: "error"` with descriptive messages
- HTTP status codes: 200 (success), 500 (error)

---

**Version:** 2.0  
**Last Updated:** 2026-02-05  
**For Support:** Contact the development team

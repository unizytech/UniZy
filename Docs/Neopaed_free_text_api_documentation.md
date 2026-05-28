# Free Text Modules API Documentation

**Version:** 1.0\
**Last Updated:** 2026-02-16\
**Base URL:** `http://117.247.185.219:121/neopaed_transcribtion_integration`

------------------------------------------------------------------------

## Overview

This document provides complete API documentation for integrating with 4
Free Text modules:

1.  **Neonatal Proforma Free Text**
2.  **NICU Discharge Free Text**
3.  **Postnatal Daycare Free Text**
4.  **Postnatal Discharge Free Text**

All APIs use **POST** method with **JSON** payload format.

## 1. NEONATAL PROFORMA FREE TEXT API

### Endpoint

    POST /store-neonatal-proforma-free-text

### Description

Create or update a Neonatal Proforma Free Text entry for a baby's
admission record.

### Required Headers

    Content-Type: application/json

### Field Descriptions

  ------------------------------------------------------------------------------
  Field Name                Type       Required          Description
  ------------------------- ---------- ----------------- -----------------------
  `uhid`                    String     ✅ Yes            Baby's Medical Record
                                                         Number (MR No)

  `entry Date`              Date       No                Date of entry
                                                         (YYYY-MM-DD format).
                                                         Defaults to today

  `seenBy`                  Array      No                Array of doctor IDs who
                                                         reviewed this record

  `obstetricHistory`        Text       No                Maternal obstetric
                                                         history including
                                                         gravida, para, live
                                                         births, abortions,
                                                         blood group, antenatal
                                                         care, complications

  `pregnancy`               Text       No                Pregnancy details
                                                         including
                                                         consanguinity, LMP, EDD
                                                         (by USG and dates),
                                                         booking status,
                                                         supervision, antenatal
                                                         steroids, MgSO4,
                                                         thyroid status, HIV,
                                                         Hepatitis B, VDRL,
                                                         maternal pyrexia,
                                                         antibiotics, medical
                                                         problems

  `pregnancyContd`          Text       No                Continuation of
                                                         pregnancy details
                                                         including
                                                         complications,
                                                         conception method
                                                         (natural/ART), multiple
                                                         pregnancy, dating scan,
                                                         anomaly scan, other
                                                         scans, Doppler findings

  `labour`                  Text       No                Labour details
                                                         including
                                                         spontaneous/induced,
                                                         nature, use of
                                                         syntocinon, risk
                                                         factors for sepsis with
                                                         details

  `delivery`                Text       No                Delivery information
                                                         including mode
                                                         (NVD/LSCS/etc),
                                                         indication,
                                                         presentation, fetal
                                                         distress, CTG findings,
                                                         anesthesia type,
                                                         gastric aspirate,
                                                         delayed cord clamping
                                                         (DCC) with duration,
                                                         cord blood gas (pH,
                                                         HCO3, BE), liquor
                                                         status, PROM duration

  `apgar`                   Text       No                APGAR scores at 1, 5,
                                                         10, 15, 20 minutes with
                                                         color, heart rate,
                                                         reflex, tone,
                                                         respiration breakdown

  `resuscitationDetails`    Text       No                Resuscitation
                                                         performed: facial O2
                                                         duration & max FiO2,
                                                         initial steps, time to
                                                         first gasp, time to
                                                         regular respiration,
                                                         delivery room CPAP,
                                                         bag-mask ventilation
                                                         duration, intubation
                                                         (ETT size, depth), PPV
                                                         duration, CPR duration,
                                                         drugs administered

  `essentialDetails`        Text       No                Initial examination
                                                         summary, malformations,
                                                         ICT, DCT results,
                                                         background, plan

  `transferStatus`          String     No                Transfer destination:
                                                         NICU/Postnatal/Other

  `admissionWeight`         Decimal    No                Weight at admission (in
                                                         kg)

  `visitNumber`             Integer    No                Visit/Admission
                                                         sequence number

  `ageOnAdmission`          Integer    No                Age in hours at
                                                         admission

  `correctedGestation`      String     No                Corrected gestational
                                                         age (e.g., "37 + 2")

  `postResuscitationCare`   Text       No                Post-resuscitation care
                                                         provided in NICU

  `admissionDetails`        Text       No                Details of NICU
                                                         admission including
                                                         reason, time

  `procedures`              Text       No                Procedures performed
                                                         (e.g., line insertion,
                                                         surfactant)

  `diagnosis`               Text       No                Admission diagnosis

  `summaryOfExamination`    Text       No                Detailed physical
                                                         examination findings
                                                         for postnatal ward
                                                         babies
  ------------------------------------------------------------------------------

### Complete JSON Payload Example

``` json
{
  "uhid": "NH123456",
  "entryDate": "2026-02-16",
  "seenBy": [8, 33],
  "obstetricHistory": "MATERNAL DETAILS:\n• Mother's Name: Priya | Age: 28 years\n• Gravida: G2 P1 L1 A0 | Blood Group: O+ Rh Positive\n• Antenatal Care: Regular\n• Complications: None",
  "pregnancy": "PREGNANCY HISTORY:\n• Consanguinity: No\n• LMP: 2025-05-01 | EDD by USG: 2026-02-05 | EDD by Dates: 2026-02-06\n• Booked: Yes at Government Hospital\n• Supervised: Yes at same hospital\n• Antenatal Steroids: Yes - Betamethasone, Complete course, Last dose 24 hours before delivery\n• Antenatal MgSO4: No\n• Thyroid Status: Normal\n• HIV: Negative | Hepatitis B: Negative | VDRL: Negative | HBsAg: Negative\n• Maternal Pyrexia: No\n• Maternal Antibiotics: No\n• Medical Problems: None",
  "pregnancyContd": "PREGNANCY DETAILS (CONTD.):\n• Pregnancy Complications: No\n• Conception: Natural\n• Multiple Pregnancy: No\n• Dating Scan: Done on 2025-06-15 at 6 weeks - Normal\n• Anomaly Scan: Done on 2025-09-20 at 20 weeks - No anomalies detected\n• Other Scans: Growth scan at 34 weeks - Appropriate for gestational age\n• Doppler Scan: Not required",
  "labour": "LABOUR:\n• Status: Spontaneous\n• Nature: Normal\n• Syntocinon: No\n• Risk Factors for Sepsis: No",
  "delivery": "DELIVERY:\n• Mode: Normal Vaginal Delivery (NVD)\n• Indication: N/A\n• Presentation: Vertex\n• Fetal Distress: No\n• CTG: Reassuring\n• Anesthesia Type: None\n• Gastric Aspirate: No\n• Delayed Cord Clamping: Yes - 60 seconds\n• Cord Blood Gas: pH 7.32, HCO3 22, BE -2\n• Liquor: Clear\n• PROM: No",
  "apgar": "APGAR SCORES:\n1 Minute: Colour 2, HR 2, Reflex 2, Tone 2, Respiration 2 | Total: 10\n5 Minutes: Colour 2, HR 2, Reflex 2, Tone 2, Respiration 2 | Total: 10\n10 Minutes: Not assessed",
  "resuscitationDetails": "RESUSCITATION:\n• Required: No\n• Facial Oxygen: No\n• Initial Steps: Routine care - drying, stimulation\n• Time to First Gasp: 30 seconds\n• Time to Regular Respiration: 1 minute\n• Delivery Room CPAP: No\n• Bag-Mask Ventilation: No\n• Intubation: No\n• PPV: No\n• CPR: No\n• Drugs: None\n• Details: Baby cried immediately after birth",
  "essentialDetails": "INITIAL EXAMINATION:\n• Summary: Term appropriate for gestational age baby, active and crying well\n• Malformation: No\n• ICT: No\n• DCT: Negative\n• Background: 37+2 weeks baby, normal delivery, no complications\n• Plan: Rooming in with mother, observe feeding",
  "transferStatus": "Postnatal Ward",
  "admissionWeight": 2.85,
  "visitNumber": 1,
  "ageOnAdmission": 2,
  "correctedGestation": "37 + 2",
  "postResuscitationCare": "",
  "admissionDetails": "",
  "procedures": "",
  "diagnosis": "",
  "summaryOfExamination": "GENERAL EXAMINATION:\n• Active baby, good tone\n• Pallor: No | Jaundice: No | Cyanosis: No\n• Vitals: HR 140/min, RR 45/min, SpO2 98%\n• CVS: S1 S2 Normal, No murmur\n• RS: Bilateral air entry equal, No retractions\n• Abdomen: Soft, non-tender, Liver 2cm, Spleen 1cm\n• CNS: Active, Normal tone, Fontanelle soft\n• Skin: Normal"
}
```

### Success Response (200)

``` json
{
  "type": "success",
  "message": "Neonatal Proforma Free Text saved successfully",
  "id": 123
}
```

### Error Response (500)

``` json
{
  "type": "failure",
  "message": "Error description"
}
```

------------------------------------------------------------------------

## 2. NICU DISCHARGE FREE TEXT API

### Endpoint

    POST /store-nicu-discharge-free-text

### Description

Create or update a NICU Discharge Free Text record.

### Field Descriptions

  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  Field Name                                                                          Type       Required          Description
  ----------------------------------------------------------------------------------- ---------- ----------------- ---------------------------------------------------------
  `uhid`                                                                              String     ✅ Yes            Baby's Medical Record Number

  [status](file:///var/www/html/neopaed/app/Http/library/SiteHelpers.php#1141-1159)   String     No                Discharge status:
                                                                                                                   "Discharged"/"Absconded"/"LAMA"/"Transferred"/"Expired"

  `dischargeDate`                                                                     Date       No                Date of discharge (YYYY-MM-DD)

  `dischargeTime`                                                                     Integer    No                Hour of discharge (1-12)

  `dischargeTimeMinutes`                                                              Integer    No                Minutes of discharge (0-59)

  `dischargeTimeSession`                                                              String     No                "AM" or "PM"

  `dolAtDischarge`                                                                    Integer    No                Day of life at discharge

  `correctedGestationWeeks`                                                           Integer    No                Corrected gestational age in weeks at discharge

  `correctedGestationDays`                                                            Integer    No                Corrected gestational age in days (0-6)

  `dischargeWeight`                                                                   Decimal    No                Weight at discharge (in kg)

  `dischargeOfc`                                                                      Decimal    No                Head circumference at discharge (in cm)

  `dischargeLength`                                                                   Decimal    No                Length at discharge (in cm)

  `immunization`                                                                      Text       No                Immunization status: vaccines given (BCG, Hepatitis B,
                                                                                                                   OPV, etc.), pending vaccines, next due dates

  `dischargeExamination`                                                              Text       No                Discharge physical examination findings: general
                                                                                                                   appearance, vitals, systemic examination (CVS, RS, GI,
                                                                                                                   CNS), skin, any residual issues

  `dischargeBloodInvestigations`                                                      Text       No                Recent blood investigations: CBC, CRP, cultures,
                                                                                                                   metabolic parameters, specific tests as applicable

  `additionalInformation`                                                             Text       No                NICU course summary: reason for admission, major problems
                                                                                                                   encountered, interventions required (ventilation, lines,
                                                                                                                   blood products), complications, peak oxygen requirement,
                                                                                                                   feeding progression

  `advice`                                                                            Text       No                Discharge advice: home care instructions, feeding
                                                                                                                   guidelines (type, frequency, volume), medication
                                                                                                                   instructions, warning signs to watch for, when to seek
                                                                                                                   medical help

  `planForFollowup`                                                                   Text       No                Follow-up plan: required specialist appointments
                                                                                                                   (pediatrician, ophthalmology for ROP screening, audiology
                                                                                                                   for hearing assessment, neurology, cardiology, etc.)

  `nextFollowupDetails`                                                               Text       No                Next scheduled follow-up: date, time, department/clinic,
                                                                                                                   doctor name, tests to bring

  `medications`                                                                       JSON       No                Discharge medications in array format (see medication
                                                                                                                   structure below)

  `seenBy`                                                                            Array      No                Array of doctor IDs
  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------

### Medication Structure

``` json
{
  "drugName": "Caffeine Citrate",
  "genericName": "Caffeine",
  "formulation": "Syrup 20mg/ml",
  "dose": "5ml",
  "frequency": "Once daily",
  "duration": "30 days",
  "additionalInstruction": "Give in the morning"
}
```

### Complete JSON Payload Example

``` json
{
  "uhid": "NH123456",
  "status": "Discharged",
  "dischargeDate": "2026-03-15",
  "dischargeTime": 11,
  "dischargeTimeMinutes": 30,
  "dischargeTimeSession": "AM",
  "dolAtDischarge": 28,
  "correctedGestationWeeks": 38,
  "correctedGestationDays": 4,
  "dischargeWeight": 2.15,
  "dischargeOfc": 33.5,
  "dischargeLength": 47,
  "immunization": "IMMUNIZATION:\n• BCG: Given on Day 7\n• Hepatitis B (Birth dose): Given on Day 1\n• OPV: Given on discharge\n• Pending: DPT, Hepatitis B (2nd dose) - due at 6 weeks\n• Next immunization due: 2026-04-26 at immunization clinic",
  "dischargeExamination": "DISCHARGE EXAMINATION:\n• General: Active, alert baby with good cry\n• Vitals: HR 145/min, RR 42/min, SpO2 98% in room air, Temperature 36.8°C\n• CVS: S1 S2 normal, no murmur\n• RS: Bilateral air entry equal and adequate, no retractions, clear breath sounds\n• GI: Soft abdomen, non-tender, no organomegaly, good bowel sounds\n• CNS: Active with normal tone, anterior fontanelle soft and flat, no seizures\n• Skin: No jaundice, no rashes\n• No residual oxygen requirement",
  "dischargeBloodInvestigations": "INVESTIGATIONS (Day 26):\n• Hemoglobin: 11.2 g/dL\n• Total WBC: 9,800/mm³\n• Platelets: 2,45,000/mm³\n• CRP: 0.4 mg/L (normal)\n• Blood Culture: Sterile (final report on Day 23)\n• Serum Electrolytes: Na 138, K 4.2, Normal\n• Thyroid Screening: Normal (TSH 3.2 mIU/L)",
  "additionalInformation": "NICU COURSE:\n• Admitted on Day 1 for Respiratory Distress Syndrome (RDS)\n• Birth Weight: 1.85 kg, Gestation: 35+4 weeks\n• Interventions:\n  - CPAP for 5 days (max PEEP 6, FiO2 40%)\n  - IV antibiotics (Ampicillin + Gentamicin) for 7 days - cultures sterile\n  - UVC and UAC placed on Day 1, removed on Day 5\n  - Phototherapy for hyperbilirubinemia (peak TSB 14.2 mg/dL on Day 3)\n• Feeding: Started on Day 2, progressed to full feeds by Day 10\n• Current feeding: Expressed breast milk 50ml every 3 hours (8 feeds/day)\n• No apnea episodes in last 7 days\n• Complications: None",
  "advice": "DISCHARGE ADVICE:\n• FEEDING:\n  - Continue breastfeeding every 2-3 hours (10-1 2 feeds/day)\n  - Ensure baby feeds well, gaining 20-30g/day\n• MEDICATIONS:\n  - Multivitamin drops: 0.6ml once daily\n  - Iron drops: 1ml once daily (start from Day 30)\n• HOME CARE:\n  - Keep baby warm (kangaroo mother care encouraged)\n  - Monitor temperature daily\n  - Watch for signs of illness\n• WARNING SIGNS (bring to hospital immediately):\n  - Refusal to feed or poor feeding\n  - Excessive sleepiness or difficult to wake\n  - Fast breathing (>60/min) or chest indrawing\n  - Blue discoloration\n  - Seizures/abnormal movements\n  - Fever >100.4°F or cold to touch\n  - Jaundice worsening",
  "planForFollowup": "FOLLOW-UP PLAN:\n1. Pediatrician: Every 2 weeks for first 2 months for weight monitoring\n2. ROP Screening: Scheduled for 2026-03-22 (at 6 weeks postnatal age)\n3. Hearing Assessment: BERA test scheduled for 2026-04-05\n4. Neurodevelopmental Assessment: At 3 months corrected age\n5. Immunization: As per schedule at immunization clinic",
  "nextFollowupDetails": "NEXT APPOINTMENT:\n• Date: 2026-03-22 (Monday)\n• Time: 10:00 AM\n• Department: Pediatric Ophthalmology  \n• Doctor: Dr. Kumar\n• Purpose: ROP Screening\n• Bring: This discharge summary, vaccination card",
  "medications": [
    {
      "drugName": "Multivitamin Drops",
      "genericName": "Vitamin A, D, E, C, B complex",
      "formulation": "Oral drops",
      "dose": "0.6ml",
      "frequency": "Once daily",
      "duration": "Continue",
      "additionalInstruction": "Give in the morning after feeding"
    },
    {
      "drugName": "Iron Drops",
      "genericName": "Ferrous Sulfate",
      "formulation": "Oral drops 25mg/ml",
      "dose": "1ml",
      "frequency": "Once daily",
      "duration": "Continue for 3 months",
      "additionalInstruction": "Start from Day 30. Give between feeds, not with milk"
    }
  ],
  "seenBy": [8, 33, 77]
}
```

### Success Response (200)

``` json
{
  "type": "success",
  "message": "NICU Discharge Free Text saved successfully",
  "id": 456
}
```

------------------------------------------------------------------------

## 3. POSTNATAL DAYCARE FREE TEXT API

### Endpoint

    POST /store-postnatal-daycare-free-text

### Description

Create or update Postnatal Daycare Free Text entry (mother-baby daycare
records).

### Field Descriptions

  ------------------------------------------------------------------------
  Field Name          Type       Required          Description
  ------------------- ---------- ----------------- -----------------------
  `uhid`              String     ✅ Yes            Baby's Medical Record
                                                   Number

  `dateOfEntry`       Date       No                Date of daycare entry
                                                   (YYYY-MM-DD)

  `timeOfEntry`       Time       No                Time of entry (HH:mm:ss
                                                   format, 24-hour)

  `dol`               Integer    No                Day of life

  `seenBy`            Array      No                Array of doctor IDs

  `background`        Text       No                Background/reason for
                                                   daycare: birth details,
                                                   any perinatal issues,
                                                   current concerns

  `diagnosis`         Text       No                Current diagnosis or
                                                   identified issues

  `notes`             Text       No                Clinical notes:
                                                   assessment findings,
                                                   vital signs,
                                                   examination details,
                                                   observations, baby's
                                                   feeding and behavior,
                                                   mother's concerns

  `plan`              Text       No                Management plan:
                                                   interventions, advice
                                                   given, follow-up plan,
                                                   discharge planning
  ------------------------------------------------------------------------

### Complete JSON Payload Example

``` json
{
  "uhid": "NH789012",
  "dateOfEntry": "2026-02-16",
  "timeOfEntry": "14:30:00",
  "dol": 2,
  "seenBy": [8, 45],
  "background": "BACKGROUND:\n• Baby born on 2026-02-14 at 15:45\n• Birth Weight: 3.2 kg\n• Gestation: 39+3 weeks\n• Mode of Delivery: Normal Vaginal Delivery\n• Mother: Primigravida, 25 years old\n• Postnatal: Rooming-in since birth\n• Reason for Review: Mother concerned about jaundice noted this morning",
  "diagnosis": "DIAGNOSIS:\n• Neonatal Jaundice (Physiological) - Day 2\n• Exclusive Breastfeeding - establishing well",
  "notes": "CLINICAL NOTES:\n• VITALS:\n  - Temperature: 36.7°C\n  - Heart Rate: 135/min\n  - Respiratory Rate: 40/min\n  - SpO2: 99% (room air)\n• EXAMINATION:\n  - General: Active, alert baby with good cry\n  - Jaundice: Present up to chest (zone 2-3)\n  - CVS: S1 S2 normal, no murmur, peripheral pulses palpable\n  - RS: Bilateral air entry equal, no distress\n  - Abdomen: Soft, non-tender, bowel sounds present\n  - Umbilicus: Clean, no discharge\n  - CNS: Active movements, normal tone, fontanelle soft\n• FEEDING:\n  - Breastfeeding: 10 feeds in 24 hours\n  - Latch: Good\n  -母乳 transfer: Adequate (baby satisfied after feeds)\n  - No vomiting\n• ELIMINATION:\n  - Urine: Passing well (6 wet diapers in 24h)\n  - Stools: Passed meconium, now transitional stools (3 times)\n• WEIGHT: 3.1 kg (3% loss from birth weight - acceptable)\n• TSB: 10.2 mg/dL (order placed)\n• MOTHER:\n  - Feeling well\n  - Breast fullness present\n  - No sore nipples\n  - Understanding baby cues well",
  "plan": "PLAN:\n1. Continue exclusive breastfeeding\n2. Encourage frequent feeding (10-12 feeds/24h)\n3. Ensure adequate hydration for mother\n4. TSB monitoring:\n   - Current: 10.2 mg/dL\n   - Repeat TSB tomorrow morning\n   - Phototherapy threshold: >13 mg/dL at this age\n5. Watch for increased jaundice (beyond abdomen level)\n6. Ensure adequate weight gain (weigh daily)\n7. Advice given:\n   - Keep baby well-fed to promote bilirubin excretion\n   - Expose to indirect sunlight (not direct) for 10-15 minutes\n   - Watch for lethargy, poor feeding, high-pitched cry\n8. Review tomorrow (Day 3) or earlier if concerns\n9. Planned discharge: Day 3 if:\n   - TSB stable/declining\n   - Feeding well\n   - Weight stable/gaining\n   - Mother confident"
}
```

### Success Response (200)

``` json
{
  "type": "success",
  "message": "Postnatal Daycare Free Text saved successfully",
  "id": 789
}
```

------------------------------------------------------------------------

## 4. POSTNATAL DISCHARGE FREE TEXT API

### Endpoint

    POST /store-postnatal-discharge-free-text

### Description

Create or update Postnatal Discharge Free Text record (for babies
discharging from postnatal ward).

### Field Descriptions

  -------------------------------------------------------------------------------------------------------------------------------------------------
  Field Name                                                                          Type       Required          Description
  ----------------------------------------------------------------------------------- ---------- ----------------- --------------------------------
  `uhid`                                                                              String     ✅ Yes            Baby's Medical Record Number

  [status](file:///var/www/html/neopaed/app/Http/library/SiteHelpers.php#1141-1159)   String     No                Discharge status:
                                                                                                                   "Discharged"/"LAMA"/"Referred"

  `dischargeDate`                                                                     Date       No                Date of discharge (YYYY-MM-DD)

  `dolAtDischarge`                                                                    Integer    No                Day of life at discharge

  `correctedGestationWeeks`                                                           Integer    No                Corrected gestational age in
                                                                                                                   weeks

  `correctedGestationDays`                                                            Integer    No                Corrected gestational age in
                                                                                                                   days (0-6)

  `dischargeWeight`                                                                   Decimal    No                Weight at discharge (in kg)

  `dischargeOfc`                                                                      Decimal    No                Head circumference at discharge
                                                                                                                   (in cm)

  `dischargeLength`                                                                   Decimal    No                Length at discharge (in cm)

  `immunization`                                                                      Text       No                Immunization status and schedule

  `diagnosis`                                                                         Text       No                Discharge diagnosis (if any
                                                                                                                   issues identified)

  `dischargeExamination`                                                              Text       No                Final examination findings
                                                                                                                   before discharge

  `postnatalCourse`                                                                   Text       No                Postnatal course summary: birth
                                                                                                                   details, any issues during stay,
                                                                                                                   feeding establishment, maternal
                                                                                                                   health, bonding

  `medications`                                                                       JSON       No                Discharge medications in array
                                                                                                                   format (usually minimal for
                                                                                                                   healthy newborns)

  `seenBy`                                                                            Array      No                Array of doctor IDs
  -------------------------------------------------------------------------------------------------------------------------------------------------

### Complete JSON Payload Example

``` json
{
  "uhid": "NH789012",
  "status": "Discharged",
  "dischargeDate": "2026-02-17",
  "dolAtDischarge": 3,
  "correctedGestationWeeks": 39,
  "correctedGestationDays": 6,
  "dischargeWeight": 3.15,
  "dischargeOfc": 34.5,
  "dischargeLength": 51,
  "immunization": "IMMUNIZATION:\n• BCG: Given on Day 2 (2026-02-16)\n• Hepatitis B (Birth dose): Given on Day 1 (2026-02-15)\n• OPV (Zero dose): Given on Day 1 (2026-02-15)\n\nNEXT IMMUNIZATION:\n• Due at 6 weeks (2026-03-28)\n• Vaccines: DPT-1, Hepatitis B-2, OPV-1, Hib-1, Rotavirus-1, PCV-1\n• Bring vaccination card to immunization clinic",
  "diagnosis": "DIAGNOSIS:\n• Healthy term appropriate for gestational age baby\n• Physiological jaundice - resolved\n• Exclusive breastfeeding established",
  "dischargeExamination": "DISCHARGE EXAMINATION (Day 3):\n• GENERAL: Active, alert, feeding well, good cry\n• VITALS:\n  - Temperature: 36.8°C\n  - Heart Rate: 132/min\n  - Respiratory Rate: 38/min  \n  - SpO2: 99% in room air\n• JAUNDICE: Significantly reduced, now zone 1 only (mild facial jaundice)\n• CVS: S1 S2 normal, no murmur, femoral pulses palpable bilaterally\n• RS: Bilateral air entry equal and adequate, no respiratory distress\n• ABDOMEN: Soft, non-tender, liver 1cm, spleen not palpable, good bowel sounds\n• UMBILICUS: Clean and dry, separating well\n• GENITALIA: Normal male, testes descended bilaterally\n• HIPS: Barlow and Ortolani negative\n• SPINE: Intact, no sacral dimple\n• CNS: Active with symmetric movements, normal tone, Moro reflex present, fontanelle soft\n• SKIN: No rashes, no birth marks requiring attention",
  "postnatalCourse": "POSTNATAL COURSE:\n• BIRTH DETAILS:\n  - Born on 2026-02-14 at 15:45\n  - Birth Weight: 3.2 kg\n  - Gestation: 39+3 weeks\n  - Mode of Delivery: Normal Vaginal Delivery\n  - Apgar: 9/9 at 1 and 5 minutes\n  - No resuscitation required\n\n• HOSPITAL STAY:\n  - Day 1: Rooming-in with mother, breastfeeding initiated within 1 hour\n  - Day 2: Jaundice noted, TSB 10.2 mg/dL, breastfeeding well\n  - Day 3: Jaundice decreasing, TSB 8.4 mg/dL, weight stable\n\n• FEEDING:\n  - Exclusive breastfeeding\n  - Frequency: 10-12 feeds per 24 hours\n  - Good latch and milk transfer\n  - Mother confident with feeding\n\n• WEIGHT:\n  - Birth: 3.2 kg\n  - Day 2: 3.1 kg (3% loss - physiological)\n  - Discharge: 3.15 kg (gaining)\n\n• MATERNAL HEALTH:\n  - Mother doing well\n  - Breast milk adequately established\n  - No nipple trauma\n  - Understanding baby care\n  - No postpartum complications\n\n• ISSUES DURING STAY:\n  - Physiological jaundice (peak Day 2: 10.2 mg/dL, resolved with frequent feeding)\n  - No other issues",
  "medications": [
    {
      "drugName": "Vitamin K",
      "genericName": "Phytomenadione",
      "formulation": "IM injection 1mg",
      "dose": "1mg",
      "frequency": "Single dose",
      "duration": "Given at birth",
      "additionalInstruction": "Already administered"
    },
    {
      "drugName": "Vitamin D3",
      "genericName": "Cholecalciferol",
      "formulation": "Oral drops 400 IU/drop",
      "dose": "1 drop (400 IU)",
      "frequency": "Once daily",
      "duration": "Continue until 1 year",
      "additionalInstruction": "Start from Day 7. Give directly into mouth or mix with expressed breast milk"
    }
  ],
  "seenBy": [8, 45]
}
```

### Success Response (200)

``` json
{
  "type": "success",
  "message": "Postnatal Discharge Free Text saved successfully",
  "id": 1011
}
```

------------------------------------------------------------------------

## Error Responses

All endpoints may return the following errors:

### Missing UHID (500)

``` json
{
  "type": "failure",
  "message": "UHID is missing"
}
```

### Baby Not Found (500)

``` json
{
  "type": "failure",
  "message": "Baby details not found"
}
```

### Admission Not Found (500)

``` json
{
  "type": "failure",
  "message": "Admission details not found"
}
```

### General Error (500)

``` json
{
  "type": "failure",
  "message": "Error saving entry: [specific error message]"
}
```

------------------------------------------------------------------------

## Postman Collection Structure

### Collection Variables

    base_url: https://your-domain.com/api
    content_type: application/json

### Request Structure Example (for all 4 endpoints)

**Name:** Create Neonatal Proforma Free Text\
**Method:** POST\
**URL:** `{{base_url}}/store-neonatal-proforma-free-text`\
**Headers:**

    Content-Type: {{content_type}}

**Body:** Raw JSON (use the complete JSON payload examples above)

------------------------------------------------------------------------

## Integration Notes

1.  **Date Format:** Always use `YYYY-MM-DD` format for dates
2.  **Time Format:** Use `HH:mm:ss` 24-hour format for times
3.  **Decimal Values:** Use decimal notation (e.g., `2.85` for weight in
    kg)
4.  **Arrays:** For `seenBy`, send array of doctor IDs as integers:
    `[8, 33, 77]`
5.  **JSON Fields:** For `medications`, send as array of objects with
    specified structure
6.  **Required Field:** Only `uhid` is mandatory; all other fields are
    optional
7.  **Null Values:** For empty/unknown fields, either omit them or send
    `null`
8.  **Text Fields:** Can contain line breaks (`\n`) for formatting

------------------------------------------------------------------------

## Support

For integration support, please contact the development team.

**Document Version:** 1.0\
**Last Updated:** 2026-02-16

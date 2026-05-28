# Patient Respiratory Parameters API Specification

## Overview
This document defines the data structure for patient respiratory monitoring parameters.

---

## Parameters

### Patient Identification
- **uhid** 
  - **Type:** `String`
  - **Description:** Patient unique ID

- **dateTime**
  - **Type:** `datetime`
  - **Format:** `YYYY-MM-DD HH:MM:SS`
  - **Description:** Recorded date time

---

### Ventilation Parameters

- **invasiveVentilation**
  - **Type:** `String`
  - **Values:** `Yes`, `No`, `N/A`

- **ventilationType**
  - **Type:** `String`
  - **Values:** 
    - `NonInvasiveVentilation`
    - `OtherRespiratorySupport`
    - `SpontaneouslyVentilating`
    - `N/A`

- **nonInvasiveVentilationMode**
  - **Type:** `String`
  - **Values:** `CPAP`, `NIMV`, `HHHFNC`, `nHFOV`, `N/A`

- **otherRespiratorySupport**
  - **Type:** `String`
  - **Values:** `NPO2`, `HBO2`, `Face`, `N/A`

- **spontaneouslyVentilating**
  - **Type:** `String`
  - **Values:** `Yes`, `No`, `N/A`

- **volume_targeting**
  - **Type:** `boolean`
  - **Values:** `true`, `false`
  - **Default:** `false`

- **calco**
  - **Type:** `boolean`
  - **Values:** `true`, `false`
  - **Default:** `false`

---

### Respiratory Indication

- **respiratoryIndication**
  - **Type:** `array(int)`
  - **Description:** Array of indication IDs
  - **Valid Options:**
    1. Others
    2. Pneumonia
    3. MAS
    4. PPHN
    5. Apnea
    6. HIE
    7. CDH
    8. Cardiac
    9. Post Operative
    10. Airleak
    11. Pleural Effusion
    12. test
    13. Chylothorax
    14. TTN
    15. Preterm RDS
    16. Seizures
    17. Term RDS
    18. Sepsis
    19. Pooling of oral secretions/delayed promoter clearance
    20. Head Injury
    21. Bronchiolitis
    22. Acute Pulmonary Haemorrhage
    23. Acute Surgical abdomen
    24. NEC

---

### Treatment & Therapy

- **surfactantTherapy**
  - **Type:** `String`
  - **Values:** `Yes`, `No`, `N/A`

- **etTube**
  - **Type:** `String`
  - **Description:** Endotracheal tube
  - **Values:** `Yes`, `No`, `N/A`

---

### Vital Signs & Measurements

- **respiratoryRate**
  - **Type:** `Int`

- **spo2**
  - **Type:** `Numeric`
  - **Description:** Oxygen saturation percentage

- **lactate**
  - **Type:** `Numeric`

---

### Clinical Examination

- **retractions**
  - **Type:** `String`
  - **Values:** `No`, `Mild`, `Moderate`, `Severe`

- **airEntry**
  - **Type:** `String`
  - **Values:** `Equal`, `Reduced Bilateral`, `Reduced Rt`, `Reduced Lt`

- **chestMovements**
  - **Type:** `String`
  - **Values:** `Symmetrical`, `Asymmetrical`, `N/A`

- **addedSounds**
  - **Type:** `String`
  - **Values:** `Present`, `Absent`

---

### Diagnostics

- **bloodGasType**
  - **Type:** `String`
  - **Values:** `Not done`, `Arterial`, `Venous`, `Capillary`, `Not indicated`, `N/A`

- **cxrFindings**
  - **Type:** `String`
  - **Description:** Chest X-ray findings (free text)

- **otherRSFindings**
  - **Type:** `String`
  - **Description:** Other respiratory system findings (free text)

---

### Chronic Conditions

- **chronicLungDisease**
  - **Type:** `boolean`
  - **Values:** `true`, `false`
  - **Default:** `false`

---

## Notes

1. **Default Values:** Set `volume_targeting`, `calco`, and `chronicLungDisease` to `false` by default when sending data
2. **Respiratory Indication:** Use the corresponding IDs (1-24) from the options list
3. **Free Text Fields:** `cxrFindings` and `otherRSFindings` accept any text input
4. **N/A Values:** Many fields support `N/A` to indicate not applicable

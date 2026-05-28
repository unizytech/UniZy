# Ophthalmology Prescription Display Format Reference

## Overview

This document describes the display format for `OPHTHAL_PRESCRIPTION` consultation type - a general prescription form with numbered medication list format.

## Visual Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                     PRESCRIPTION FORM                            │
├─────────────────────────────────────────────────────────────────┤
│ Date        : ____________     Visit Id   : ____________         │
│ Patient Name: ____________________________________________       │
│ NIN         : ____________     Age : _____  Sex : ______        │
│ MR.No       : ____________                                       │
│ Address     : ____________________________________________       │
├─────────────────────────────────────────────────────────────────┤
│ Please supply the following :                                    │
│                                                                  │
│ 1. Cap.Ogareds : Take 1 capsule at night after food for         │
│    6 months.                                                     │
│                                                                  │
│ 2. Refresh tears : Apply 1 drop 4x a day to BOTH EYES for       │
│    6 months.                                                     │
│                                                                  │
│ (Both eyes-continue Latanoprost e/d 1x at night,                │
│                     Dorzox e/d 3x,                               │
│                     Brimonidine e/d 3x)                          │
├─────────────────────────────────────────────────────────────────┤
│ If the medications prescribed are unavailable, please call us    │
│ immediately                                                      │
│ Contact us :                                                     │
├─────────────────────────────────────────────────────────────────┤
│ Doctor's Name:                     Signature:                    │
│                                                                  │
│ Stamp:                                                           │
│ ┌────────────────────┐                                          │
│ │   [Hospital Stamp] │                                          │
│ └────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────┘
```

## JSON Data Schema

```typescript
interface OphthalPrescriptionData {
  // Patient Information
  patientDetails: {
    name: string;              // Patient full name
    date: string;              // Date of prescription (DD/MM/YYYY)
    visitId: string;           // Visit/appointment ID
    nin: string;               // National Identification Number
    age: string;               // Patient age (e.g., "59 Y 8 M 29 D")
    gender: string;            // "Male" | "Female"
    mrNumber: string;          // Medical Record number
    address: string;           // Patient address
  };

  // Prescription Items (numbered list)
  prescriptionItems: Array<{
    serialNumber: number;      // 1, 2, 3, etc.
    medicationName: string;    // "Cap.Ogareds", "Refresh tears"
    medicationType: string;    // "CAPSULE" | "TABLET" | "EYE_DROP" | "EYE_OINTMENT" | "GEL"
    dosage: string;            // "1 capsule", "1 drop"
    frequency: string;         // "at night", "4x a day"
    duration: string;          // "6 months", "2 weeks"
    eye: string;               // "BOTH EYES" | "LEFT EYE" | "RIGHT EYE" | "N/A"
    specialInstructions: string; // "after food", "before bed"
    isContinuing: boolean;     // false (new prescription)
  }>;

  // Continuing Medications (medications to continue)
  continuingMedications: Array<{
    medicationName: string;    // "Latanoprost", "Dorzox"
    eye: string;               // "e/d" (each day), "both eyes"
    frequency: string;         // "1x at night", "3x"
    notes: string;             // Additional notes
  }>;

  // Additional Notes
  additionalNotes: string;     // Any extra instructions

  // Pharmacy Contact Note
  pharmacyNote: string;        // "If medications unavailable..."

  // Doctor Information
  doctorDetails: {
    name: string;              // Doctor's name
    signature: string;         // (placeholder for signature)
    stamp: string;             // Hospital stamp info
  };

  // Follow-up Information
  followUp: {
    date: string;              // Next appointment date
    instructions: string;      // Follow-up instructions
  };
}
```

## Display Schema for External React Frontend

```typescript
// Display configuration for rendering OPHTHAL_PRESCRIPTION
export const OPHTHAL_PRESCRIPTION_DISPLAY_SCHEMA = {
  consultationType: 'OPHTHAL_PRESCRIPTION',
  displayName: 'Ophthalmology Prescription',

  layout: {
    type: 'form',           // 'form' | 'table' | 'report'
    orientation: 'portrait', // 'portrait' | 'landscape'
    paperSize: 'A4',
  },

  sections: [
    {
      id: 'header',
      type: 'title',
      content: 'PRESCRIPTION FORM',
      style: {
        textAlign: 'center',
        fontSize: '20pt',
        fontWeight: 'bold',
        textTransform: 'uppercase',
        borderBottom: '2px solid #000'
      }
    },
    {
      id: 'patientDetails',
      type: 'grid',
      columns: 2,
      fields: [
        { key: 'patientDetails.date', label: 'Date', format: 'date' },
        { key: 'patientDetails.visitId', label: 'Visit Id' },
        { key: 'patientDetails.name', label: 'Patient Name', fullWidth: true },
        { key: 'patientDetails.nin', label: 'NIN' },
        { key: 'patientDetails.age', label: 'Age' },
        { key: 'patientDetails.gender', label: 'Sex' },
        { key: 'patientDetails.mrNumber', label: 'MR.No' },
        { key: 'patientDetails.address', label: 'Address', fullWidth: true }
      ]
    },
    {
      id: 'prescriptionItems',
      type: 'numberedList',
      title: 'Please supply the following :',
      dataKey: 'prescriptionItems',
      itemTemplate: {
        format: '{serialNumber}. {medicationName} : {dosage} {frequency} to {eye} for {duration}. {specialInstructions}'
      }
    },
    {
      id: 'continuingMedications',
      type: 'paragraph',
      condition: 'continuingMedications.length > 0',
      format: '(Both eyes-continue {medications})',
      dataKey: 'continuingMedications',
      style: {
        background: '#f5f5f5',
        borderLeft: '3px solid #666',
        padding: '15px'
      }
    },
    {
      id: 'pharmacyNote',
      type: 'alert',
      dataKey: 'pharmacyNote',
      title: 'Contact us :',
      style: {
        background: '#fff9e6',
        border: '1px solid #999'
      }
    },
    {
      id: 'signature',
      type: 'signatureBlock',
      fields: ['doctorDetails.name', 'doctorDetails.signature', 'doctorDetails.stamp']
    }
  ],

  // Styling hints for the frontend
  styling: {
    fontFamily: "'Times New Roman', Times, serif",
    baseFontSize: '12pt',
    lineHeight: 1.5,
    labelMinWidth: '120px',
    fieldSeparator: ':',
    printMargins: '0.75in'
  }
};
```

## React Component Example

```tsx
// Example React component for external frontend
import React from 'react';

interface PrescriptionItemProps {
  item: {
    serialNumber: number;
    medicationName: string;
    dosage: string;
    frequency: string;
    duration: string;
    eye: string;
    specialInstructions?: string;
  };
}

const PrescriptionItem: React.FC<PrescriptionItemProps> = ({ item }) => {
  const instructions = [
    item.dosage,
    item.frequency,
    item.eye !== 'N/A' ? `to ${item.eye}` : '',
    `for ${item.duration}`,
    item.specialInstructions || ''
  ].filter(Boolean).join(' ');

  return (
    <div className="prescription-item">
      <span className="item-number">{item.serialNumber}.</span>
      <span className="item-content">
        {item.medicationName} : {instructions}.
      </span>
    </div>
  );
};

// Usage
const OphthalPrescription: React.FC<{ data: OphthalPrescriptionData }> = ({ data }) => {
  return (
    <div className="prescription-form">
      <header>PRESCRIPTION FORM</header>

      <section className="patient-info">
        {/* Patient details grid */}
      </section>

      <section className="medications">
        <h2>Please supply the following :</h2>
        {data.prescriptionItems.map(item => (
          <PrescriptionItem key={item.serialNumber} item={item} />
        ))}
      </section>

      {data.continuingMedications.length > 0 && (
        <section className="continuing">
          <p>(Both eyes-continue {data.continuingMedications.map(m =>
            `${m.medicationName} ${m.eye} ${m.frequency}`
          ).join(', ')})</p>
        </section>
      )}

      <section className="pharmacy-note">
        {data.pharmacyNote}
      </section>

      <footer className="signature-section">
        {/* Doctor signature area */}
      </footer>
    </div>
  );
};
```

## CSS Styling Guidelines

```css
.prescription-form {
  font-family: 'Times New Roman', Times, serif;
  font-size: 12pt;
  line-height: 1.5;
  max-width: 8.5in;
  margin: 0 auto;
  padding: 0.75in;
  background: white;
}

.prescription-item {
  margin-bottom: 12px;
  display: flex;
  align-items: flex-start;
}

.item-number {
  font-weight: bold;
  min-width: 25px;
}

.item-content {
  flex: 1;
}

.continuing {
  margin-top: 25px;
  padding: 15px;
  background: #f5f5f5;
  border-left: 3px solid #666;
}

.pharmacy-note {
  margin-top: 30px;
  padding: 15px;
  border: 1px solid #999;
  background: #fff9e6;
}

@media print {
  .prescription-form {
    padding: 0.5in;
  }
}
```

## Key Rendering Rules

1. **Medication Format**: Each prescription item follows the format:
   `{number}. {MedicationName} : {dosage} {frequency} to {eye} for {duration}. {specialInstructions}`

2. **Continuing Medications**: Display in parentheses format with "Both eyes-continue" prefix

3. **Pharmacy Note**: Always displayed at the bottom with warning styling

4. **Signature Area**: Include Doctor's Name, Signature line, and Stamp box

5. **Eye Specification**: Only show "to {eye}" if eye is not "N/A"

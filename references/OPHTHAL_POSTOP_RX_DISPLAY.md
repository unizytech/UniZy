# Post-Operative Medication Display Format Reference

## Overview

This document describes the display format for `OPHTHAL_POSTOP_RX` consultation type - a post-operative medication schedule with timing columns table format.

## Visual Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          POST OPERATIVE MEDICATION                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ PATIENT DETAILS                                                                      │
│ Name      : _______________  Visit ID : ____________  Date : _______________         │
│ MRNO      : _______________  Age / Gender : ___________________________              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│ ┌─────┬─────────────────┬───────────┬──────────────── TIMING ──────────────────┐    │
│ │  S  │                 │  DAYS /   ├─────┬─────┬─────┬─────┬─────┬─────┐       │    │
│ │ NO  │    EYE DROP     │   DATE    │  1  │  2  │  3  │  4  │  5  │  6  │       │    │
│ ├─────┼─────────────────┼───────────┼─────┼─────┼─────┼─────┼─────┼─────┤       │    │
│ │  1  │ MOXIFLOXACIN    │  2 weeks  │ 7am │10am │ 1pm │ 4pm │ 7pm │10pm │       │    │
│ │     │ EYEDROPS -      │(16/10/25  │     │     │     │     │     │     │       │    │
│ │     │ LEFT EYE        │-29/10/25) │     │     │     │     │     │     │       │    │
│ ├─────┼─────────────────┼───────────┼─────┼─────┼─────┼─────┼─────┼─────┤       │    │
│ │ 2a  │ FML EYE DROP-   │  5 days   │7.15am│7.15am│12pm │5pm  │     │8.30pm│    │    │
│ │     │ LEFT EYE        │(16/10/25  │     │     │     │     │     │     │       │    │
│ │     │                 │-20/10/25) │     │     │     │     │     │     │       │    │
│ ├─────┼─────────────────┼───────────┼─────┼─────┼─────┼─────┼─────┼─────┤       │    │
│ │ 2b  │ FML EYE DROP-   │  5 days   │7.15am│7.15am│12.30pm│   │     │8.30pm│    │    │
│ │     │ LEFT EYE        │(21/10/25  │     │     │     │     │     │     │       │    │
│ │     │                 │-25/10/25) │     │     │     │     │     │     │       │    │
│ ├─────┼─────────────────┼───────────┼─────┼─────┼─────┼─────┼─────┼─────┤       │    │
│ │  4  │ CARBOMER        │  6 weeks  │     │     │     │     │     │     │       │    │
│ │     │ GEL- LEFT EYE   │(16/10/25  │         Apply only at night (09.30pm)    │    │
│ │     │                 │-28/11/25) │                                          │    │
│ └─────┴─────────────────┴───────────┴──────────────────────────────────────────┘    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## JSON Data Schema

```typescript
interface OphthalPostOpRxData {
  // Patient Information
  patientDetails: {
    name: string;              // Patient full name
    visitId: string;           // Visit/appointment ID
    date: string;              // Date of document (DD/MM/YYYY)
    mrNumber: string;          // Medical Record number
    age: string;               // Patient age
    gender: string;            // "Male" | "Female"
  };

  // Surgery Details (optional)
  surgeryDetails: {
    procedure: string;         // "Cataract surgery", "LASIK"
    eyeOperated: string;       // "LEFT EYE" | "RIGHT EYE" | "BOTH EYES"
    surgeryDate: string;       // Date of surgery (DD/MM/YYYY)
    surgeon: string;           // Surgeon name
  };

  // Medications array (main table data)
  medications: Array<{
    serialNumber: string;      // "1", "2a", "2b", "3" (supports sub-rows)
    medicationName: string;    // "MOXIFLOXACIN EYEDROPS"
    medicationType: string;    // "EYE_DROP" | "EYE_OINTMENT" | "GEL"
    eye: string;               // "LEFT EYE" | "RIGHT EYE" | "BOTH EYES"

    // Duration info
    durationText: string;      // "2 weeks", "5 days"
    dateRange: string;         // "16/10/25 - 29/10/25"
    startDate: string;         // "16/10/25"
    endDate: string;           // "29/10/25"

    // Frequency
    frequency: number;         // Number of times per day (1-6)

    // Timing slots (up to 6)
    timing1: string;           // "7am", "7.15am" (or empty)
    timing2: string;           // "10am" (or empty)
    timing3: string;           // "1pm", "12pm" (or empty)
    timing4: string;           // "4pm", "5pm" (or empty)
    timing5: string;           // "7pm" (or empty)
    timing6: string;           // "10pm", "8.30pm" (or empty)

    // Special instructions (spans timing columns)
    specialInstructions: string; // "Apply only at night (09.30pm)"

    // For tapering schedules
    parentSerialNumber: string; // Reference to parent row (e.g., "2" for "2a")
    isTaperingRow: boolean;     // true if this is part of a tapering schedule
    taperingPhase: number;      // 1, 2, 3... for tapering order
  }>;

  // General Instructions
  generalInstructions: string[]; // Array of instruction strings

  // Follow-up Information
  followUp: {
    date: string;              // Next appointment date
    instructions: string;      // Follow-up instructions
  };
}
```

## Display Schema for External React Frontend

```typescript
// Display configuration for rendering OPHTHAL_POSTOP_RX
export const OPHTHAL_POSTOP_RX_DISPLAY_SCHEMA = {
  consultationType: 'OPHTHAL_POSTOP_RX',
  displayName: 'Post Operative Medication',

  layout: {
    type: 'table',           // 'form' | 'table' | 'report'
    orientation: 'landscape', // 'portrait' | 'landscape' (recommended for wide table)
    paperSize: 'A4',
  },

  sections: [
    {
      id: 'header',
      type: 'title',
      content: 'POST OPERATIVE MEDICATION',
      style: {
        textAlign: 'center',
        fontSize: '18pt',
        fontWeight: 'bold',
        textTransform: 'uppercase',
        borderBottom: '3px solid #000'
      }
    },
    {
      id: 'patientDetails',
      type: 'grid',
      columns: 3,
      background: '#f9f9f9',
      border: '1px solid #ccc',
      fields: [
        { key: 'patientDetails.name', label: 'Name' },
        { key: 'patientDetails.visitId', label: 'Visit ID' },
        { key: 'patientDetails.date', label: 'Date', format: 'date' },
        { key: 'patientDetails.mrNumber', label: 'MRNO' },
        { key: 'patientDetails.age', label: 'Age / Gender',
          format: '{age} / {gender}' }
      ]
    },
    {
      id: 'surgeryDetails',
      type: 'inline',
      condition: 'surgeryDetails.procedure',
      format: 'Surgery: {procedure} ({eyeOperated}) on {surgeryDate}'
    },
    {
      id: 'medicationTable',
      type: 'table',
      dataKey: 'medications',
      columns: [
        {
          key: 'serialNumber',
          header: 'S\nNO',
          width: '5%',
          align: 'center',
          rowSpan: 2
        },
        {
          key: 'medicationName',
          header: 'EYE DROP',
          width: '20%',
          subContent: '{eye}',
          rowSpan: 2
        },
        {
          key: 'duration',
          header: 'DAYS /\nDATE',
          width: '15%',
          format: '{durationText}\n({dateRange})',
          align: 'center',
          rowSpan: 2
        },
        {
          headerGroup: 'TIMING',
          colSpan: 6,
          subColumns: [
            { key: 'timing1', header: '1', width: '10%', align: 'center' },
            { key: 'timing2', header: '2', width: '10%', align: 'center' },
            { key: 'timing3', header: '3', width: '10%', align: 'center' },
            { key: 'timing4', header: '4', width: '10%', align: 'center' },
            { key: 'timing5', header: '5', width: '10%', align: 'center' },
            { key: 'timing6', header: '6', width: '10%', align: 'center' }
          ]
        }
      ],
      // Special row handling
      rowTypes: {
        standard: {
          condition: 'item => !item.specialInstructions',
          render: 'all columns'
        },
        withInstructions: {
          condition: 'item => item.specialInstructions',
          render: [
            { columns: ['serialNumber', 'medicationName', 'duration'] },
            { columns: ['timing1-6'], merge: true, content: '{specialInstructions}' }
          ]
        },
        subRow: {
          condition: 'item => item.isTaperingRow',
          style: { background: '#f5f5f5' }
        }
      }
    },
    {
      id: 'generalInstructions',
      type: 'list',
      title: 'General Instructions:',
      dataKey: 'generalInstructions',
      condition: 'generalInstructions.length > 0',
      style: {
        background: '#f5f5f5',
        borderLeft: '4px solid #333'
      }
    },
    {
      id: 'followUp',
      type: 'box',
      title: 'Follow-up:',
      dataKey: 'followUp',
      condition: 'followUp.date || followUp.instructions',
      style: {
        border: '2px solid #333'
      }
    }
  ],

  // Styling hints for the frontend
  styling: {
    fontFamily: "Arial, sans-serif",
    baseFontSize: '10pt',
    lineHeight: 1.4,
    tableHeaderBackground: '#333',
    tableHeaderColor: 'white',
    printMargins: '0.5in',
    maxWidth: '11in'
  }
};
```

## React Component Example

```tsx
// Example React component for external frontend
import React from 'react';

interface MedicationRowProps {
  med: {
    serialNumber: string;
    medicationName: string;
    eye: string;
    durationText: string;
    dateRange: string;
    timing1: string;
    timing2: string;
    timing3: string;
    timing4: string;
    timing5: string;
    timing6: string;
    specialInstructions?: string;
    isTaperingRow?: boolean;
  };
}

const MedicationRow: React.FC<MedicationRowProps> = ({ med }) => {
  const isSubRow = /^\d+[a-z]$/.test(med.serialNumber);

  return (
    <>
      <tr className={isSubRow ? 'sub-row' : ''}>
        <td className="serial-col">{med.serialNumber}</td>
        <td className="med-col">
          {med.medicationName}
          {med.eye && <br /><small className="eye-spec">{med.eye}</small>}
        </td>
        <td className="days-col">
          {med.durationText}
          {med.dateRange && <><br /><small>{med.dateRange}</small></>}
        </td>
        <td className="timing-col">{med.timing1}</td>
        <td className="timing-col">{med.timing2}</td>
        <td className="timing-col">{med.timing3}</td>
        <td className="timing-col">{med.timing4}</td>
        <td className="timing-col">{med.timing5}</td>
        <td className="timing-col">{med.timing6}</td>
      </tr>
      {med.specialInstructions && (
        <tr className="instruction-row">
          <td colSpan={9} className="special-instructions">
            {med.specialInstructions}
          </td>
        </tr>
      )}
    </>
  );
};

const PostOpMedicationTable: React.FC<{ data: OphthalPostOpRxData }> = ({ data }) => {
  return (
    <div className="postop-medication">
      <header>POST OPERATIVE MEDICATION</header>

      <section className="patient-section">
        <div className="patient-grid">
          <div className="field">
            <span className="label">Name</span>
            <span className="value">: {data.patientDetails.name}</span>
          </div>
          {/* ... other patient fields ... */}
        </div>
      </section>

      <table className="medication-table">
        <thead>
          <tr>
            <th rowSpan={2}>S<br/>NO</th>
            <th rowSpan={2}>EYE DROP</th>
            <th rowSpan={2}>DAYS /<br/>DATE</th>
            <th colSpan={6}>TIMING</th>
          </tr>
          <tr>
            <th>1</th>
            <th>2</th>
            <th>3</th>
            <th>4</th>
            <th>5</th>
            <th>6</th>
          </tr>
        </thead>
        <tbody>
          {data.medications.map((med, idx) => (
            <MedicationRow key={idx} med={med} />
          ))}
        </tbody>
      </table>

      {data.generalInstructions.length > 0 && (
        <section className="general-instructions">
          <h3>General Instructions:</h3>
          <ul>
            {data.generalInstructions.map((inst, idx) => (
              <li key={idx}>{inst}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
};
```

## CSS Styling Guidelines

```css
.postop-medication {
  font-family: Arial, sans-serif;
  font-size: 10pt;
  line-height: 1.4;
  max-width: 11in;
  margin: 0 auto;
  padding: 0.5in;
  background: white;
}

.medication-table {
  width: 100%;
  border-collapse: collapse;
  margin: 20px 0;
}

.medication-table th {
  background: #333;
  color: white;
  font-weight: bold;
  padding: 10px 5px;
  text-align: center;
  font-size: 9pt;
  border: 1px solid #333;
}

.medication-table td {
  border: 1px solid #999;
  padding: 8px 5px;
  vertical-align: top;
}

.medication-table .serial-col {
  width: 5%;
  text-align: center;
  font-weight: bold;
}

.medication-table .med-col {
  width: 20%;
  font-weight: bold;
}

.medication-table .days-col {
  width: 15%;
  text-align: center;
  font-size: 9pt;
}

.medication-table .timing-col {
  width: 10%;
  text-align: center;
  font-size: 9pt;
}

.medication-table .eye-spec {
  font-weight: normal;
  color: #666;
  font-style: italic;
}

.medication-table .sub-row td {
  background: #f5f5f5;
}

.medication-table .instruction-row td {
  background: #fffbe6;
  font-style: italic;
  font-size: 9pt;
  text-align: center;
  color: #666;
}

.general-instructions {
  margin-top: 20px;
  padding: 15px;
  background: #f5f5f5;
  border-left: 4px solid #333;
}

@media print {
  .postop-medication {
    padding: 0.25in;
    font-size: 9pt;
  }
  .medication-table th { font-size: 8pt; padding: 6px 3px; }
  .medication-table td { font-size: 8pt; padding: 5px 3px; }
}
```

## Key Rendering Rules

1. **Table Header**: Two-row header with "TIMING" spanning columns 1-6 in first row, and individual numbers 1-6 in second row

2. **Serial Number Format**:
   - Standard rows: "1", "2", "3", etc.
   - Tapering sub-rows: "2a", "2b", "2c" (alphabetic suffix)

3. **Days/Date Column**: Display both duration text and date range:
   - First line: Duration (e.g., "2 weeks", "5 days")
   - Second line: Date range in smaller text (e.g., "16/10/25 - 29/10/25")

4. **Timing Distribution**: Distribute times evenly based on frequency:
   - 4x/day: 7am, 12pm, 5pm, 10pm
   - 5x/day: 7am, 10am, 1pm, 5pm, 9pm
   - 6x/day: 7am, 10am, 1pm, 4pm, 7pm, 10pm

5. **Special Instructions Row**: When present, merge timing columns and display instruction text across all 6 timing columns

6. **Sub-row Styling**: Tapering rows (e.g., "2a", "2b") should have slightly different background (#f5f5f5)

7. **Eye Specification**: Display below medication name in smaller, italic text

## Tapering Schedule Example

When a medication needs tapering (e.g., "4x/day for 2 weeks, then 2x/day for next 2 weeks"):

```json
{
  "medications": [
    {
      "serialNumber": "2a",
      "medicationName": "FML EYE DROP",
      "eye": "LEFT EYE",
      "durationText": "5 days",
      "dateRange": "16/10/25 - 20/10/25",
      "frequency": 4,
      "timing1": "7.15am",
      "timing2": "7.15am",
      "timing3": "12pm",
      "timing4": "5pm",
      "timing5": "",
      "timing6": "8.30pm",
      "parentSerialNumber": "2",
      "isTaperingRow": true,
      "taperingPhase": 1
    },
    {
      "serialNumber": "2b",
      "medicationName": "FML EYE DROP",
      "eye": "LEFT EYE",
      "durationText": "5 days",
      "dateRange": "21/10/25 - 25/10/25",
      "frequency": 3,
      "timing1": "7.15am",
      "timing2": "",
      "timing3": "12.30pm",
      "timing4": "",
      "timing5": "",
      "timing6": "8.30pm",
      "parentSerialNumber": "2",
      "isTaperingRow": true,
      "taperingPhase": 2
    }
  ]
}
```

/**
 * Discharge Summary HTML Formatter (Simplified 18-segment schema - Gemini compatible)
 * Formats discharge summary JSON into professional medical document HTML
 * Uses simplified schema with strings instead of complex arrays/objects
 */

interface DischargeSummaryData {
  // SEGMENT 1: Student Information (11 fields)
  patient_information: {
    name: string;
    age: string;
    gender: string;
    registration_number: string;
    ip_number: string;
    admission_date: string;
    discharge_date: string;
    address: string;
    contact_number: string;
    ward_name: string;
    bed_number: string;
  };

  // SEGMENT 2: Medical Team (5 fields)
  medical_team: {
    chairman: string;
    unit_head: string;
    admitting_consultant: string;
    unit_consultants: string; // Comma or newline separated
    visiting_consultants: string; // Comma or newline separated
  };

  // SEGMENT 3: Diagnosis (2 fields) - FLATTENED SCHEMA
  diagnosis: {
    primary_diagnosis: string;
    secondary_diagnoses: string; // String (comma or newline separated) - NOT array
  };

  // SEGMENT 4: Complaints (1 field) - STILL ARRAY (not flattened)
  complaints: Array<string>; // Array of strings directly

  // SEGMENT 5: History of Present Illness (10 fields) - FLATTENED SCHEMA
  history_of_present_illness: {
    onset: string;
    duration: string;
    progression: string;
    characterization: string;
    alleviating_factors: string;
    aggravating_factors: string;
    severity: string;
    associated_symptoms: string; // String (comma separated) - NOT array
    negative_findings: string; // String (comma separated) - RESTORED
    impact_on_daily_life: string;
  };

  // SEGMENT 6: History (7 fields) - PARTIALLY FLATTENED SCHEMA
  history: {
    past_medical_history: string; // String (comma/newline separated) - NOT array
    past_surgical_history: string; // String (comma/newline separated) - NOT array
    family_history: string;
    social_history: string;
    birth_history: string;
    current_medications: Array<{  // Still array of objects - NO CHANGE
      medication_name: string;
      dosage: string;
      frequency: string;
      route: string;
      indication: string;
      ownership: string;
    }>;
    drug_allergies: string;
  };

  // SEGMENT 7: Physical Examination (6 fields) - vitals now in separate VITALS segment
  physical_examination: {
    cardiovascular_system: string;
    respiratory_system: string;
    central_nervous_system: string;
    per_abdomen: string;
    musculoskeletal: string;
    other_systems: string;
  };

  // SEGMENT 8: Investigations - flat array of {name, type, date}
  investigations: Array<{
    name: string;
    type: string; // "Laboratory" | "Imaging" | "Other"
    date: string;
  }>;

  // SEGMENT 9: Treatment Summary (3 fields) - FLATTENED SCHEMA
  treatment_summary: {
    treatment_summary: string;
    patient_response: string;
    complications: string; // String (comma/newline separated) - NOT array
  };

  // SEGMENT 10: Treatment Details (10 fields) - FLATTENED SCHEMA
  treatment_details: {
    procedure_name: string;
    anesthesia_type: string;
    patient_position: string; // String - RESTORED
    intraoperative_findings: string; // String (newline/bullet separated) - NOT array
    operation_notes: string;
    construction_details: string; // String - RESTORED
    procedure_date: string;
    duration: string;
    blood_loss: string; // String - RESTORED
    complications: string; // String (comma/newline separated) - NOT array
  };

  // SEGMENT 11: School Course (5 fields) - FLATTENED SCHEMA
  hospital_course: {
    summary: string;
    daily_progress: string; // String - ORIGINAL NAME RESTORED, NOT array
    complications: string; // String (comma/newline separated) - NOT array
    transfers: string;
    consultations: string; // String (comma separated) - NOT array
  };

  // SEGMENT 12: Discharge Condition (5 fields) - FLATTENED SCHEMA
  discharge_condition: {
    condition_at_discharge: string;
    functional_status: string;
    pain_level: string;
    vital_signs_at_discharge: string;
    pending_investigations: string; // String (comma/newline separated) - NOT array
  };

  // SEGMENT 13: Prescription (1 field) - ARRAY OF OBJECTS (no change)
  prescription: {
    medications: Array<{  // Still array of objects - NO CHANGE
      medication_name: string;
      dosage: string;
      frequency: string;
      route: string;
      duration: string;
      timing: string;
      instructions: string;
    }>;
  };

  // SEGMENT 14: Treatment Plan & Advice - array of instruction strings
  treatment_plan_advice: string[];

  // SEGMENT 15: Follow-up (3 fields) - SIMPLIFIED SCHEMA
  follow_up: {
    review_date: string;
    special_instructions: string;
    other_instructions: string;
  };

  // SEGMENT 16: Emergency Contact - single string
  emergency_contact: string;

  // SEGMENT 17: Timestamped Transcription (1 field)
  timestamped_transcription: string; // Newline separated transcript lines

  // SEGMENT 18: Report Metadata (8 fields)
  report_metadata: {
    prepared_by: string;
    checked_by: string;
    approved_by: string;
    report_date: string;
    report_time: string;
    school_name: string;
    hospital_address: string;
    hospital_contact: string;
  };
}

export interface FormatterConfig {
  ipno?: string;
  chairman?: string;
  unitHead?: string;
  admittingConsultant?: string;
  departmentName?: string;
  emergencyContactText?: string;
  doctorAppointmentNumber?: string;
  showEmptyFields?: boolean; // For testing: show all fields even if empty
}

export function formatDischargeSummaryHTML(
  data: DischargeSummaryData,
  config?: FormatterConfig
): string {
  const showEmptyFields = config?.showEmptyFields ?? false;
  const notNA = (value: any) => value && value !== 'N/A' && value !== '';

  // Helper to parse comma or newline separated strings into arrays
  const parseList = (value: string): string[] => {
    if (!notNA(value)) return [];
    // Split by newline or comma, clean up whitespace
    const items = value.includes('\n')
      ? value.split('\n')
      : value.split(',');
    return items.map(item => item.trim()).filter(item => item && item !== 'N/A');
  };

  // Helper to decide if field should be shown
  const shouldShow = (value: any) => showEmptyFields || notNA(value);

  // Helper to format medications array into reference format
  const formatMedications = (medications: Array<{
    medication_name: string;
    dosage: string;
    frequency: string;
    duration: string;
    instructions: string;
  }>): string => {
    if (!medications || medications.length === 0) return 'N/A';

    // Find the longest medication name to calculate alignment
    const maxNameLength = Math.max(...medications.map((med, idx) =>
      `${idx + 1}. ${med.medication_name}`.length
    ));

    // Add padding to ensure consistent alignment (minimum 40 characters)
    const alignColumn = Math.max(maxNameLength + 5, 40);

    return medications.map((med, index) => {
      // Format: "1. TAB. CETIL 500MG         1-0-1 X 5 DAYS"
      const prefix = `${index + 1}. ${med.medication_name}`;
      const spacesNeeded = alignColumn - prefix.length;
      const spaces = ' '.repeat(Math.max(spacesNeeded, 2)); // At least 2 spaces

      // Build medication line with proper spacing
      let line = `${prefix}${spaces}${med.frequency} ${med.duration}`;

      // Add instructions if present and not N/A
      if (notNA(med.instructions)) {
        line += ` ${med.instructions}`;
      }

      return line;
    }).join('\n');
  };

  // Use config values or extracted values or defaults
  const ipno = config?.ipno || data.patient_information.ip_number || 'IP202507935';
  const chairman = config?.chairman || data.medical_team.chairman || 'Prof. C Palanivelu.C, MBBS.,MS.,MCh.,FACS.,FRCS (ED).,DS.C.,Ph.D.,';
  const unitHead = config?.unitHead || data.medical_team.unit_head || 'Dr. ANAND VIJAI N MS DrNB(Surg.Gastro) FMAS FACS PhD, Fellowship In Liver Transplant';
  const admittingConsultant = config?.admittingConsultant || data.medical_team.admitting_consultant || unitHead;
  const departmentName = config?.departmentName || 'SURGICAL GASTROENTEROLOGY';
  const emergencyContactText = config?.emergencyContactText || 'For emergency contact Phone No SGE III secretary – 9842210174 (9.00 AM to 6.00 PM) (Monday to saturday) AFTER 6.00 PM and public holidays CONTACT GEM HOSPITAL NO : 0422 -4695100';
  const doctorAppointmentNumber = config?.doctorAppointmentNumber || '9003932323';

  // Parse list fields
  const unitConsultants = parseList(data.medical_team?.unit_consultants || '');
  const visitingConsultants = parseList(data.medical_team?.visiting_consultants || '');
  const secondaryDiagnoses = parseList(data.diagnosis?.secondary_diagnoses || '');
  const intraopFindings = parseList(data.treatment_details?.intraoperative_findings || '');
  const emergencyContactInfo = typeof data.emergency_contact === 'string' ? data.emergency_contact : '';

  // Student header for all pages (repeated at top of each page)
  const patientHeader = `
    <div class="patient-header">
        <div class="patient-header-left">
            <div class="patient-name-small">${data.patient_information.name || 'N/A'}</div>
            <div class="info-line-small">${data.patient_information.age || 'N/A'}${data.patient_information.age !== 'N/A' ? ' Y' : ''} / ${data.patient_information.gender ? data.patient_information.gender.toUpperCase() : 'N/A'}</div>
        </div>
        <div class="patient-header-right">
            <div class="info-line-small"><span class="info-label">REGNO :</span> ${data.patient_information.registration_number || 'N/A'}</div>
            <div class="info-line-small"><span class="info-label">IPNO :</span> ${ipno}</div>
        </div>
    </div>
  `;

  return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discharge Summary - ${data.patient_information.name || 'N/A'}</title>
    <style>
        @media print {
            body {
                margin: 0;
                padding: 15mm;
            }

            .patient-header {
                display: none; /* Don't show the simplified header */
            }

            /* Allow natural page breaks */
            .section {
                page-break-inside: avoid;
                break-inside: avoid;
            }
            .section-header {
                page-break-after: avoid;
                break-after: avoid;
            }
        }

        body {
            font-family: 'Arial', sans-serif;
            font-size: 11pt;
            line-height: 1.4;
            color: #000;
            max-width: 210mm;
            margin: 0 auto;
            padding: 20px;
            background: #fff;
        }

        .header {
            text-align: center;
            margin-bottom: 20px;
            border-bottom: 2px solid #000;
            padding-bottom: 10px;
        }

        .header h1 {
            margin: 0;
            font-size: 16pt;
            font-weight: bold;
            text-transform: uppercase;
        }

        .header h2 {
            margin: 5px 0 0 0;
            font-size: 13pt;
            font-weight: bold;
            text-transform: uppercase;
        }

        .patient-info-section {
            display: flex;
            justify-content: space-between;
            margin: 15px 0;
            border-bottom: 1px solid #000;
            padding-bottom: 10px;
        }

        .patient-info-left {
            flex: 1;
        }

        .patient-info-right {
            text-align: right;
            flex: 1;
        }

        .patient-name {
            font-size: 14pt;
            font-weight: bold;
            margin-bottom: 3px;
        }

        .info-line {
            margin: 2px 0;
            font-size: 10pt;
        }

        .info-label {
            font-weight: bold;
        }

        .patient-header {
            display: none; /* Hidden in screen view, shown via @page in print */
        }

        @media print {
            .patient-header {
                display: flex;
                justify-content: space-between;
                padding-bottom: 10px;
                border-bottom: 1px solid #000;
                margin-bottom: 15px;
            }
        }

        .patient-header-left {
            flex: 1;
        }

        .patient-header-right {
            text-align: right;
            flex: 1;
        }

        .patient-name-small {
            font-size: 12pt;
            font-weight: bold;
            margin-bottom: 3px;
        }

        .info-line-small {
            margin: 2px 0;
            font-size: 9pt;
        }

        .section {
            margin: 15px 0;
        }

        .section-header {
            font-weight: bold;
            text-decoration: underline;
            margin: 10px 0 5px 0;
            font-size: 11pt;
        }

        .team-section {
            display: flex;
            justify-content: space-between;
            border-bottom: 1px solid #000;
            padding-bottom: 10px;
            margin-bottom: 10px;
        }

        .team-left, .team-right {
            flex: 1;
        }

        .team-label {
            font-weight: bold;
            margin-top: 5px;
        }

        .content {
            margin: 5px 0;
            text-align: justify;
            white-space: pre-wrap;
        }

        .finding-list {
            margin: 5px 0 5px 20px;
        }

        .finding-list li {
            margin: 3px 0;
        }

        .vitals-line {
            font-weight: bold;
            margin: 5px 0;
        }

        .advice-list, .emergency-list {
            margin: 5px 0 5px 20px;
        }

        .advice-list li, .emergency-list li {
            margin: 5px 0;
        }

        .contact-info {
            margin: 10px 0;
            font-style: italic;
            font-weight: bold;
        }

        .signature-section {
            margin-top: 40px;
            text-align: right;
        }

        .page-break {
            margin-top: 30px;
        }

        .sub-section {
            margin: 8px 0 8px 15px;
        }

        .sub-section-header {
            font-weight: bold;
            margin: 5px 0 3px 0;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>DISCHARGE SUMMARY</h1>
        <h2>DEPARTMENT OF ${departmentName.toUpperCase()}</h2>
    </div>

    <div class="patient-info-section">
        <div class="patient-info-left">
            <div class="patient-name">${data.patient_information.name || 'N/A'}</div>
            <div class="info-line">${data.patient_information.age || 'N/A'}${data.patient_information.age && data.patient_information.age !== 'N/A' ? ' Y' : ''} / ${data.patient_information.gender ? data.patient_information.gender.toUpperCase() : 'N/A'}</div>
            <div class="info-line">${data.patient_information.address || 'N/A'}</div>
            <div class="info-line">${data.patient_information.contact_number || 'N/A'}</div>
        </div>
        <div class="patient-info-right">
            <div class="info-line"><span class="info-label">REGNO :</span> ${data.patient_information.registration_number || 'N/A'}</div>
            <div class="info-line"><span class="info-label">IPNO :</span> ${ipno}</div>
            <div class="info-line"><span class="info-label">ADMITTED ON :</span> ${data.patient_information.admission_date || 'N/A'}</div>
            <div class="info-line"><span class="info-label">DISCHARGED ON :</span> ${data.patient_information.discharge_date || 'N/A'}</div>
            <div class="info-line"><span class="info-label">WARD NAME :</span> ${data.patient_information.ward_name || 'N/A'}</div>
            <div class="info-line"><span class="info-label">BED NO :</span> ${data.patient_information.bed_number || 'N/A'}</div>
        </div>
    </div>

    <div class="team-section">
        <div class="team-left">
            <div class="team-label">Chairman :</div>
            <div>${chairman}</div>
            <div class="team-label">Admitting Consultant:</div>
            <div>${admittingConsultant}</div>
        </div>
        <div class="team-right">
            <div class="team-label">Unit Head :</div>
            <div>${unitHead}</div>
            ${unitConsultants.length > 0 ? `
                <div class="team-label">Unit Consultants:</div>
                ${unitConsultants.map(c => `<div>${c}</div>`).join('')}
            ` : ''}
        </div>
    </div>

    ${visitingConsultants.length > 0 ? `
        <div class="section">
            <div class="team-label">Visiting Consultants:</div>
            ${visitingConsultants.map(c => `<div>${c}</div>`).join('')}
        </div>
    ` : ''}

    <div class="section">
        <div class="section-header">Diagnosis :</div>
        <div class="content">${data.diagnosis.primary_diagnosis || 'N/A'}</div>
        ${secondaryDiagnoses.length > 0 ? `
            ${secondaryDiagnoses.map(d => `<div class="content">${d}</div>`).join('')}
        ` : ''}
    </div>

    <div class="section">
        <div class="section-header">Treatment Done :</div>
        <div class="content">${data.treatment_details?.procedure_name || 'N/A'}${notNA(data.treatment_details?.procedure_date) ? ` DONE ON ${data.treatment_details.procedure_date}` : ''}</div>
    </div>

    <div class="section">
        <div class="section-header">History of Present Illness :</div>
        ${(() => {
            const hpi = data.history_of_present_illness;
            if (!hpi) return '<div class="content">N/A</div>';

            const parts = [];

            // Build narrative paragraph (excluding negative findings)
            if (notNA(hpi.onset)) parts.push(`Onset: ${hpi.onset}`);
            if (notNA(hpi.duration)) parts.push(`Duration: ${hpi.duration}`);
            if (notNA(hpi.characterization)) parts.push(`Characterized by ${hpi.characterization}`);
            if (notNA(hpi.severity)) parts.push(`Severity: ${hpi.severity}`);
            if (notNA(hpi.progression)) parts.push(`Progression: ${hpi.progression}`);
            if (notNA(hpi.associated_symptoms)) parts.push(`Associated symptoms include ${hpi.associated_symptoms}`);
            if (notNA(hpi.alleviating_factors)) parts.push(`Relieved by ${hpi.alleviating_factors}`);
            if (notNA(hpi.aggravating_factors)) parts.push(`Aggravated by ${hpi.aggravating_factors}`);
            if (notNA(hpi.impact_on_daily_life)) parts.push(`Impact on daily life: ${hpi.impact_on_daily_life}`);

            // Keep negative findings separate for new line
            const negativeFindings = notNA(hpi.negative_findings)
                ? `<div class="content">${hpi.negative_findings}</div>`
                : '';

            const narrative = parts.length > 0 ? `<div class="content">${parts.join('. ') + '.'}</div>` : '<div class="content">N/A</div>';
            return narrative + negativeFindings;
        })()}
    </div>

    <div class="section">
        <div class="section-header">Past Medical History :</div>
        <div class="content">${data.history?.past_medical_history || 'N/A'}</div>
    </div>


    <div class="section">
        <div class="section-header">Past Surgical History :</div>
        <div class="content">${data.history?.past_surgical_history || 'N/A'}</div>
        ${shouldShow(data.history?.family_history) ? `
            <div class="sub-section">
                <div class="sub-section-header">Family History:</div>
                <div class="content">${data.history.family_history}</div>
            </div>
        ` : ''}
        ${shouldShow(data.history?.social_history) ? `
            <div class="sub-section">
                <div class="sub-section-header">Social History:</div>
                <div class="content">${data.history.social_history}</div>
            </div>
        ` : ''}
        ${shouldShow(data.history?.birth_history) ? `
            <div class="sub-section">
                <div class="sub-section-header">Birth History:</div>
                <div class="content">${data.history.birth_history}</div>
            </div>
        ` : ''}
        ${shouldShow(data.history?.current_medications) ? `
            <div class="sub-section">
                <div class="sub-section-header">Current Medications (Before Admission):</div>
                <div class="content">${data.history.current_medications}</div>
            </div>
        ` : ''}
        ${shouldShow(data.history?.drug_allergies) ? `
            <div class="sub-section">
                <div class="sub-section-header">Drug Allergies:</div>
                <div class="content">${data.history.drug_allergies}</div>
            </div>
        ` : ''}
    </div>

    <div class="section">
        <div class="section-header">PHYSICAL EXAMINATION:</div>
        ${shouldShow(data.physical_examination?.cardiovascular_system) ? `<div class="content"><b>CVS:</b> ${data.physical_examination.cardiovascular_system}</div>` : ''}
        ${shouldShow(data.physical_examination?.respiratory_system) ? `<div class="content"><b>RS:</b> ${data.physical_examination.respiratory_system}</div>` : ''}
        ${shouldShow(data.physical_examination?.central_nervous_system) ? `<div class="content"><b>CNS:</b> ${data.physical_examination.central_nervous_system}</div>` : ''}
        ${shouldShow(data.physical_examination?.per_abdomen) ? `<div class="content"><b>P/A:</b> ${data.physical_examination.per_abdomen}</div>` : ''}
        ${shouldShow(data.physical_examination?.musculoskeletal) ? `<div class="content"><b>Musculoskeletal:</b> ${data.physical_examination.musculoskeletal}</div>` : ''}
        ${shouldShow(data.physical_examination?.other_systems) ? `<div class="content">${data.physical_examination.other_systems}</div>` : ''}
    </div>

    <div class="section">
        <div class="section-header">INVESTIGATIONS :</div>
        ${(() => {
            const invs = data.investigations;
            if (!invs || !Array.isArray(invs) || invs.length === 0) {
                return '<div class="content">Reports Enclosed</div>';
            }
            const lab = invs.filter((i: any) => i.type?.toLowerCase() === 'laboratory');
            const imaging = invs.filter((i: any) => i.type?.toLowerCase() === 'imaging');
            const other = invs.filter((i: any) => !['laboratory', 'imaging'].includes(i.type?.toLowerCase()));
            const fmtList = (items: any[]) => items.map((i: any) => {
                const date = i.date && i.date !== 'N/A' ? ` (${i.date})` : '';
                return `${i.name}${date}`;
            }).join(', ');
            let html = '';
            if (lab.length > 0) {
                html += `<div class="sub-section"><div class="sub-section-header">Laboratory Tests:</div><div class="content">${fmtList(lab)}</div></div>`;
            }
            if (imaging.length > 0) {
                html += `<div class="sub-section"><div class="sub-section-header">Imaging Studies:</div><div class="content">${fmtList(imaging)}</div></div>`;
            }
            if (other.length > 0) {
                html += `<div class="content">${fmtList(other)}</div>`;
            }
            return html || '<div class="content">Reports Enclosed</div>';
        })()}
    </div>

    ${shouldShow(data.treatment_details?.procedure_name) ? `

        <div class="section">
            <div class="section-header">Name of surgery : ${data.treatment_details.procedure_name}${notNA(data.treatment_details.procedure_date) ? ` DONE ON ${data.treatment_details.procedure_date}` : ''}</div>
            ${shouldShow(data.treatment_details.anesthesia_type) ? `<div class="section-header">Anesthesia : ${data.treatment_details.anesthesia_type}</div>` : ''}
            ${shouldShow(data.treatment_details.patient_position) ? `<div class="section-header">Position : ${data.treatment_details.patient_position}</div>` : ''}
            ${shouldShow(data.treatment_details.duration) ? `<div class="section-header">Duration : ${data.treatment_details.duration}</div>` : ''}
            ${shouldShow(data.treatment_details.blood_loss) ? `<div class="section-header">Blood Loss : ${data.treatment_details.blood_loss}</div>` : ''}

            ${intraopFindings.length > 0 ? `
                <div class="section-header">Finding :</div>
                <ul class="finding-list">
                    ${intraopFindings.map(f => `<li>${f}</li>`).join('')}
                </ul>
            ` : ''}

            ${shouldShow(data.treatment_details.operation_notes) ? `
                <div class="section-header">Operation notes :</div>
                <div class="content">${data.treatment_details.operation_notes}</div>
            ` : ''}

            ${shouldShow(data.treatment_details.construction_details) ? `
                <div class="section-header">Construction :</div>
                <div class="content">${data.treatment_details.construction_details}</div>
            ` : ''}

            ${shouldShow(data.treatment_details.complications) ? `
                <div class="section-header">Complications :</div>
                <div class="content">${data.treatment_details.complications}</div>
            ` : ''}
        </div>
    ` : ''}


    <div class="section">
        <div class="section-header">Course In School :</div>
        <div class="content">${data.hospital_course?.summary || 'N/A'}</div>
        ${shouldShow(data.treatment_summary?.treatment_summary) ? `
            <div class="sub-section">
                <div class="sub-section-header">Treatment Summary:</div>
                <div class="content">${data.treatment_summary.treatment_summary}</div>
            </div>
        ` : ''}
        ${shouldShow(data.treatment_summary?.patient_response) ? `
            <div class="sub-section">
                <div class="sub-section-header">Student Response:</div>
                <div class="content">${data.treatment_summary.patient_response}</div>
            </div>
        ` : ''}
        ${shouldShow(data.hospital_course?.daily_progress) ? `
            <div class="sub-section">
                <div class="sub-section-header">Daily Progress:</div>
                <div class="content">${data.hospital_course.daily_progress}</div>
            </div>
        ` : ''}
        ${shouldShow(data.hospital_course?.complications) ? `
            <div class="sub-section">
                <div class="sub-section-header">Complications:</div>
                <div class="content">${data.hospital_course.complications}</div>
            </div>
        ` : ''}
        ${shouldShow(data.treatment_summary?.complications) ? `
            <div class="sub-section">
                <div class="sub-section-header">Treatment Complications:</div>
                <div class="content">${data.treatment_summary.complications}</div>
            </div>
        ` : ''}
        ${shouldShow(data.hospital_course?.transfers) ? `
            <div class="sub-section">
                <div class="sub-section-header">Transfers:</div>
                <div class="content">${data.hospital_course.transfers}</div>
            </div>
        ` : ''}
        ${shouldShow(data.hospital_course?.consultations) ? `
            <div class="sub-section">
                <div class="sub-section-header">Consultations:</div>
                <div class="content">${data.hospital_course.consultations}</div>
            </div>
        ` : ''}
    </div>

    ${shouldShow(data.discharge_condition) ? `
        <div class="section">
            <div class="section-header">Condition at Discharge :</div>
            ${shouldShow(data.discharge_condition.condition_at_discharge) ? `<div class="content">${data.discharge_condition.condition_at_discharge}</div>` : ''}
            ${shouldShow(data.discharge_condition.functional_status) ? `
                <div class="sub-section">
                    <div class="sub-section-header">Functional Status:</div>
                    <div class="content">${data.discharge_condition.functional_status}</div>
                </div>
            ` : ''}
            ${shouldShow(data.discharge_condition.pain_level) ? `
                <div class="sub-section">
                    <div class="sub-section-header">Pain Level:</div>
                    <div class="content">${data.discharge_condition.pain_level}</div>
                </div>
            ` : ''}
            ${shouldShow(data.discharge_condition.vital_signs_at_discharge) ? `
                <div class="sub-section">
                    <div class="sub-section-header">Vital Signs at Discharge:</div>
                    <div class="content">${data.discharge_condition.vital_signs_at_discharge}</div>
                </div>
            ` : ''}
            ${shouldShow(data.discharge_condition.pending_investigations) ? `
                <div class="sub-section">
                    <div class="sub-section-header">Pending Investigations:</div>
                    <div class="content">${data.discharge_condition.pending_investigations}</div>
                </div>
            ` : ''}
        </div>
    ` : ''}

    <div class="section">
        <div class="section-header">Advice On Discharge :</div>
        <div class="content">Post drug interaction explained to the student.</div>
        ${Array.isArray(data.treatment_plan_advice) && data.treatment_plan_advice.length > 0
            ? `<ul>${data.treatment_plan_advice.filter((i: any) => i).map((i: any) => `<li>${i}</li>`).join('')}</ul>`
            : ''}
    </div>

    <div class="section">
        <div class="section-header">Medications :</div>
        <div class="content" style="white-space: pre; font-family: monospace;">${formatMedications(data.prescription?.medications || [])}</div>
    </div>


    <div class="section">
        <div class="content"><b>For home delivery of drugs / home collection for lab investigations call 8925847518</b></div>
    </div>

    <div class="section">
        <div class="content"><b>Investigations :</b> Report Enclosed</div>
    </div>

    <div class="section">
        <div class="section-header">Review Date : ${data.follow_up?.review_date || 'N/A'}</div>
        ${shouldShow(data.follow_up?.special_instructions) ? `<div class="content"><b>Special Instructions:</b> ${data.follow_up.special_instructions}</div>` : ''}
        ${shouldShow(data.follow_up?.other_instructions) ? `<div class="content"><b>Other Instructions:</b> ${data.follow_up.other_instructions}</div>` : ''}
    </div>

    <div class="section">
        <div class="section-header">When and How to Obtain for Emergency or Urgent Care :</div>
        ${shouldShow(emergencyContactInfo) ? `
            <div class="content">${emergencyContactInfo}</div>
        ` : `
            <div class="contact-info" style="font-style: italic;">
                ${emergencyContactText}
            </div>
        `}
    </div>

    <div class="section">
        <div class="contact-info">
            FOR COUNSELLOR APPOINTMENT NO : ${doctorAppointmentNumber}
        </div>
    </div>

    <div class="section">
        <div class="section-header">PREPARED BY: ${data.report_metadata?.prepared_by || 'N/A'}</div>
        ${shouldShow(data.report_metadata?.checked_by) ? `<div class="content"><b>CHECKED BY:</b> ${data.report_metadata.checked_by}</div>` : ''}
        ${shouldShow(data.report_metadata?.approved_by) ? `<div class="content"><b>APPROVED BY:</b> ${data.report_metadata.approved_by}</div>` : ''}
    </div>

    ${shouldShow(data.timestamped_transcription) ? `
        <div class="section">
            <div class="section-header">Timestamped Transcription :</div>
            <div class="content" style="white-space: pre-line; font-family: 'Courier New', monospace; font-size: 9pt;">${data.timestamped_transcription}</div>
        </div>
    ` : ''}

    <div class="signature-section">
        <div style="margin-top: 60px; border-top: 1px solid #000; display: inline-block; padding-top: 5px;">
            ${unitHead}
        </div>
    </div>
</body>
</html>
  `;
}

export function downloadDischargeSummary(
  data: DischargeSummaryData,
  config?: FormatterConfig,
  filename?: string
) {
  const html = formatDischargeSummaryHTML(data, config);
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || `discharge-summary-${data.patient_information.name.replace(/\s+/g, '-')}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

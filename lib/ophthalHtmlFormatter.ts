/**
 * Ophthalmology HTML Formatter
 *
 * Generates properly formatted HTML documents for ophthalmology consultations
 * matching the reference formats from screenshots.
 */

import type { ActivatedTemplate } from './types';

/**
 * Generate HTML for ophthalmology consultations
 * Routes to appropriate formatter based on consultation type
 */
export function generateOphthalHtml(
  data: Record<string, any>,
  template: ActivatedTemplate | null
): string {
  const consultationType = template?.consultation_type_code;

  switch (consultationType) {
    case 'OPHTHALMOLOGY':
      return generateBasicConsultationHtml(data, template);
    case 'OPHTHAL_FULL':
      return generateFullConsultationHtml(data, template);
    case 'OPHTHAL_DISCHARGE':
      return generateDischargeHtml(data, template);
    case 'OPTOMETRY':
      return generateOptometryHtml(data, template);
    case 'OPHTHAL_PRESCRIPTION':
      return generatePrescriptionHtml(data, template);
    case 'OPHTHAL_POSTOP_RX':
      return generatePostOpRxHtml(data, template);
    default:
      return generateGenericOphthalHtml(data, template);
  }
}

/**
 * Generate HTML for basic ophthalmology consultation
 * Based on OPHTHALMOLOGY_BASIC_CONSULTATION_REFERENCE.md
 */
function generateBasicConsultationHtml(
  data: Record<string, any>,
  template: ActivatedTemplate | null
): string {
  // Support both snake_case (legacy) and camelCase (current extraction) field names
  const patientDetails = data.patient_details || data.patient_information || data.patientDemographics || {};
  const complaints = data.complaints || data.chief_complaints || data.chiefComplaints || '';
  const pastHistory = data.past_history || data.past_ocular_history || data.clinicalHistory?.pastHistory || '';
  const systemicIllness = data.systemic_illness || data.clinicalHistory?.systemicIllness || '';
  const familyHistory = data.family_history || data.clinicalHistory?.familyHistory || '';
  const allergy = data.allergy || data.allergies || data.clinicalHistory?.allergies || '';
  const currentTreatment = data.current_treatment || data.clinicalHistory?.currentMedications || '';
  const pgp = data.pgp || data.previous_glasses_prescription || data.clinicalHistory?.previousGlassesPrescription || '';

  // Visual Acuity - support both formats
  const visualAcuity = data.visual_acuity || data.visualAcuity || {};
  const vaDistance = visualAcuity.distance || {};
  const vaNear = visualAcuity.near || {};

  // Refraction - support both formats
  const refraction = data.refraction || {};
  const subjectiveRefraction = data.subjective_refraction || refraction.subjective || {};

  // Muscle Balance - support both formats
  const muscleBalance = data.muscle_balance || data.muscleBalance || {};
  const eom = muscleBalance.eom || {};
  const coverTest = muscleBalance.cover_test || muscleBalance.ct || {};

  // Slit Lamp - support both formats
  const slitLamp = data.slit_lamp_examination || data.slit_lamp || data.slitLampExamination || {};

  // IOP - support both formats
  const iop = data.iop || data.intra_ocular_pressure || data.intraocularPressure || {};

  // Gonioscopy - support both formats
  const gonioscopy = data.gonioscopy || data.gonio_scopy || {};

  // Fundus - support both formats
  const fundus = data.fundus || data.fundus_examination || data.fundusExamination || {};

  // Diagnosis & Advice - support both formats
  const diagnosis = data.diagnosis || '';
  const advice = data.advice || data.advice_for_continuing_cares || data.adviceAndFollowUp || '';

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ophthalmic Consultation</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Times New Roman', Times, serif;
      font-size: 12pt;
      line-height: 1.4;
      padding: 0.75in;
      max-width: 8.5in;
      margin: 0 auto;
      background: white;
      color: #000;
    }
    .header {
      text-align: center;
      margin-bottom: 20px;
      border-bottom: 2px solid #000;
      padding-bottom: 10px;
    }
    .header h1 {
      font-size: 18pt;
      font-weight: bold;
      text-transform: uppercase;
      margin-bottom: 5px;
    }
    .patient-box {
      border: 1px solid #000;
      padding: 10px;
      margin-bottom: 15px;
      background: #f9f9f9;
    }
    .patient-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .field {
      margin-bottom: 8px;
    }
    .field-label {
      font-weight: bold;
      display: inline-block;
      min-width: 80px;
    }
    .section {
      margin-bottom: 20px;
      page-break-inside: avoid;
    }
    .section-title {
      font-weight: bold;
      text-decoration: underline;
      margin-bottom: 8px;
      font-size: 13pt;
    }
    .bilateral-table {
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0;
    }
    .bilateral-table th,
    .bilateral-table td {
      border: 1px solid #000;
      padding: 8px;
      text-align: left;
    }
    .bilateral-table th {
      background: #e0e0e0;
      font-weight: bold;
      text-align: center;
    }
    .bilateral-grid {
      display: grid;
      grid-template-columns: 120px 1fr 1fr;
      gap: 0;
      border: 1px solid #000;
      margin: 10px 0;
    }
    .bilateral-grid > div {
      border-right: 1px solid #000;
      border-bottom: 1px solid #000;
      padding: 8px;
    }
    .bilateral-grid > div:nth-child(3n) {
      border-right: none;
    }
    .bilateral-header {
      background: #e0e0e0;
      font-weight: bold;
      text-align: center;
    }
    .fundus-diagrams {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin: 15px 0;
    }
    .fundus-diagram {
      text-align: center;
    }
    .fundus-circle {
      width: 150px;
      height: 150px;
      border: 2px solid #000;
      border-radius: 50%;
      margin: 10px auto;
      position: relative;
      background: #fff;
    }
    .fundus-disc {
      width: 30px;
      height: 30px;
      border: 2px solid #666;
      border-radius: 50%;
      position: absolute;
      left: 50%;
      top: 40%;
      transform: translate(-50%, -50%);
      background: #ffd;
    }
    .text-content {
      white-space: pre-wrap;
      line-height: 1.6;
    }
    @media print {
      body { padding: 0.5in; }
      .section { page-break-inside: avoid; }
    }
  </style>
</head>
<body>

  <!-- HEADER -->
  <div class="header">
    <h1>Consultation</h1>
  </div>

  <!-- PATIENT DETAILS -->
  <div class="patient-box">
    <div class="patient-grid">
      <div class="field">
        <span class="field-label">MR. No.:</span>
        <span>${escapeHtml(patientDetails.mr_no || patientDetails.mrno || patientDetails.student_id || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">Date:</span>
        <span>${escapeHtml(patientDetails.date || new Date().toLocaleDateString())}</span>
      </div>
      <div class="field">
        <span class="field-label">Student Name:</span>
        <span>${escapeHtml(patientDetails.name || patientDetails.patient_name || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">Age:</span>
        <span>${escapeHtml(patientDetails.age || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">Gender:</span>
        <span>${escapeHtml(patientDetails.gender || 'N/A')}</span>
      </div>
    </div>
  </div>

  <!-- COMPLAINTS -->
  <div class="section">
    <div class="section-title">Complaints:</div>
    <div class="text-content">${escapeHtml(complaints || 'No specific complaints reported')}</div>
  </div>

  <!-- PAST HISTORY -->
  <div class="section">
    <div class="section-title">Past History:</div>
    <div class="text-content">${escapeHtml(pastHistory || 'No significant past history')}</div>
  </div>

  <!-- SYSTEMIC ILLNESS -->
  <div class="section">
    <div class="section-title">Systemic illness:</div>
    <div class="text-content">${escapeHtml(systemicIllness || 'None reported')}</div>
  </div>

  <!-- FAMILY HISTORY -->
  <div class="section">
    <div class="section-title">Family History:</div>
    <div class="text-content">${escapeHtml(familyHistory || 'Not documented')}</div>
  </div>

  <!-- ALLERGY -->
  <div class="section">
    <div class="section-title">Allergy:</div>
    <div class="text-content">${escapeHtml(allergy || 'No known allergies')}</div>
  </div>

  <!-- CURRENT TREATMENT -->
  <div class="section">
    <div class="section-title">Current Treatment:</div>
    <div class="text-content">${escapeHtml(currentTreatment || 'None')}</div>
  </div>

  <!-- PGP -->
  <div class="section">
    <div class="section-title">PGP (Previous Glasses Prescription):</div>
    <div class="text-content">${escapeHtml(pgp || 'Not available')}</div>
  </div>

  <!-- VISUAL ACUITY -->
  <div class="section">
    <div class="section-title">Visual Acuity</div>
    <table class="bilateral-table">
      <tr>
        <th style="width: 30%;">Measurement</th>
        <th style="width: 35%;">OD (Right Eye)</th>
        <th style="width: 35%;">OS (Left Eye)</th>
      </tr>
      <tr>
        <td><strong>Distance</strong></td>
        <td>${escapeHtml(
          vaDistance.od || vaDistance.right_eye || vaDistance.rightEye ||
          visualAcuity.rightEye?.distance || visualAcuity.rightEye?.unaided || 'N/A'
        )}</td>
        <td>${escapeHtml(
          vaDistance.os || vaDistance.left_eye || vaDistance.leftEye ||
          visualAcuity.leftEye?.distance || visualAcuity.leftEye?.unaided || 'N/A'
        )}</td>
      </tr>
      <tr>
        <td><strong>Near</strong></td>
        <td>${escapeHtml(
          vaNear.od || vaNear.right_eye || vaNear.rightEye ||
          visualAcuity.rightEye?.near || 'N/A'
        )}</td>
        <td>${escapeHtml(
          vaNear.os || vaNear.left_eye || vaNear.leftEye ||
          visualAcuity.leftEye?.near || 'N/A'
        )}</td>
      </tr>
    </table>
  </div>

  <!-- REFRACTION -->
  <div class="section">
    <div class="section-title">Refraction:</div>
    <table class="bilateral-table">
      <tr>
        <th style="width: 50%;">OD (Right Eye)</th>
        <th style="width: 50%;">OS (Left Eye)</th>
      </tr>
      <tr>
        <td>${escapeHtml(formatRefraction(
          refraction.od || refraction.right_eye || refraction.rightEye ||
          refraction.objective?.rightEye
        ))}</td>
        <td>${escapeHtml(formatRefraction(
          refraction.os || refraction.left_eye || refraction.leftEye ||
          refraction.objective?.leftEye
        ))}</td>
      </tr>
    </table>
  </div>

  <!-- SUBJECTIVE REFRACTION -->
  <div class="section">
    <div class="section-title">Subjective Refraction</div>
    <table class="bilateral-table">
      <tr>
        <th style="width: 30%;">Type</th>
        <th style="width: 35%;">OD (Right Eye)</th>
        <th style="width: 35%;">OS (Left Eye)</th>
      </tr>
      <tr>
        <td><strong>Distance</strong></td>
        <td>${escapeHtml(formatRefraction(
          subjectiveRefraction.distance?.od || subjectiveRefraction.distance?.right_eye ||
          subjectiveRefraction.distance?.rightEye || subjectiveRefraction.rightEye?.distance
        ))}</td>
        <td>${escapeHtml(formatRefraction(
          subjectiveRefraction.distance?.os || subjectiveRefraction.distance?.left_eye ||
          subjectiveRefraction.distance?.leftEye || subjectiveRefraction.leftEye?.distance
        ))}</td>
      </tr>
      <tr>
        <td><strong>Near</strong></td>
        <td>${escapeHtml(formatRefraction(
          subjectiveRefraction.near?.od || subjectiveRefraction.near?.right_eye ||
          subjectiveRefraction.near?.rightEye || subjectiveRefraction.rightEye?.near
        ))}</td>
        <td>${escapeHtml(formatRefraction(
          subjectiveRefraction.near?.os || subjectiveRefraction.near?.left_eye ||
          subjectiveRefraction.near?.leftEye || subjectiveRefraction.leftEye?.near
        ))}</td>
      </tr>
    </table>
  </div>

  <!-- MUSCLE BALANCE -->
  <div class="section">
    <div class="section-title">Muscle Balance:</div>
    <div class="field">
      <span class="field-label">General:</span>
      <span>${escapeHtml(muscleBalance.general || 'Normal')}</span>
    </div>
    <div style="margin-top: 10px;">
      <strong>EOM (Extraocular Movements):</strong>
      <table class="bilateral-table" style="margin-top: 5px;">
        <tr>
          <th style="width: 50%;">OD (Right Eye)</th>
          <th style="width: 50%;">OS (Left Eye)</th>
        </tr>
        <tr>
          <td>${escapeHtml(eom.od || eom.right_eye || 'Full in all directions')}</td>
          <td>${escapeHtml(eom.os || eom.left_eye || 'Full in all directions')}</td>
        </tr>
      </table>
    </div>
    <div style="margin-top: 10px;">
      <strong>CT (Cover Test):</strong>
      <table class="bilateral-table" style="margin-top: 5px;">
        <tr>
          <th style="width: 30%;">Distance</th>
          <th style="width: 35%;">OD (Right Eye)</th>
          <th style="width: 35%;">OS (Left Eye)</th>
        </tr>
        <tr>
          <td><strong>Dist</strong></td>
          <td>${escapeHtml(coverTest.distance?.od || coverTest.dist?.od || coverTest.distance?.right_eye || 'Orthophoria')}</td>
          <td>${escapeHtml(coverTest.distance?.os || coverTest.dist?.os || coverTest.distance?.left_eye || 'Orthophoria')}</td>
        </tr>
        <tr>
          <td><strong>Near</strong></td>
          <td>${escapeHtml(coverTest.near?.od || coverTest.near?.right_eye || 'Orthophoria')}</td>
          <td>${escapeHtml(coverTest.near?.os || coverTest.near?.left_eye || 'Orthophoria')}</td>
        </tr>
      </table>
    </div>
  </div>

  <!-- NEW PAGE MARKER -->
  <div style="page-break-before: always;"></div>

  <!-- SLIT LAMP EXAMINATION -->
  <div class="section">
    <div class="section-title">Slit Lamp Examination</div>
    <table class="bilateral-table">
      <tr>
        <th style="width: 50%;">OD (Right Eye)</th>
        <th style="width: 50%;">OS (Left Eye)</th>
      </tr>
      <tr>
        <td style="vertical-align: top;">
          ${formatSlitLampFindings(slitLamp.od || slitLamp.right_eye || slitLamp.rightEye || slitLamp)}
        </td>
        <td style="vertical-align: top;">
          ${formatSlitLampFindings(slitLamp.os || slitLamp.left_eye || slitLamp.leftEye || slitLamp)}
        </td>
      </tr>
    </table>
  </div>

  <!-- INTRAOCULAR PRESSURE -->
  <div class="section">
    <div class="section-title">I.O.P. (Intraocular Pressure)</div>
    <table class="bilateral-table">
      <tr>
        <th style="width: 50%;">OD (Right Eye)</th>
        <th style="width: 50%;">OS (Left Eye)</th>
      </tr>
      <tr>
        <td>${escapeHtml(formatIOP(iop.od || iop.right_eye || iop.rightEye))}</td>
        <td>${escapeHtml(formatIOP(iop.os || iop.left_eye || iop.leftEye))}</td>
      </tr>
    </table>
  </div>

  <!-- GONIOSCOPY -->
  <div class="section">
    <div class="section-title">Gonio Scopy:</div>
    <table class="bilateral-table">
      <tr>
        <th style="width: 50%;">OD (Right Eye)</th>
        <th style="width: 50%;">OS (Left Eye)</th>
      </tr>
      <tr>
        <td>${escapeHtml(gonioscopy.od || gonioscopy.right_eye || gonioscopy.rightEye || 'Not performed')}</td>
        <td>${escapeHtml(gonioscopy.os || gonioscopy.left_eye || gonioscopy.leftEye || 'Not performed')}</td>
      </tr>
    </table>
  </div>

  <!-- FUNDUS EXAMINATION -->
  <div class="section">
    <div class="section-title">Fundus:</div>
    <div class="fundus-diagrams">
      <div class="fundus-diagram">
        <strong>OD (Right Eye)</strong>
        <div class="fundus-circle">
          <div class="fundus-disc"></div>
        </div>
        <div style="text-align: left; margin-top: 10px;">
          ${formatFundusFindings(fundus.od || fundus.right_eye || fundus.rightEye)}
        </div>
      </div>
      <div class="fundus-diagram">
        <strong>OS (Left Eye)</strong>
        <div class="fundus-circle">
          <div class="fundus-disc"></div>
        </div>
        <div style="text-align: left; margin-top: 10px;">
          ${formatFundusFindings(fundus.os || fundus.left_eye || fundus.leftEye)}
        </div>
      </div>
    </div>
  </div>

  <!-- DIAGNOSIS -->
  <div class="section">
    <div class="section-title">Diagnosis:</div>
    <div class="text-content">${
      Array.isArray(diagnosis)
        ? diagnosis.map(d => escapeHtml(d)).join('<br>')
        : escapeHtml(diagnosis || 'To be determined')
    }</div>
  </div>

  <!-- ADVICE -->
  <div class="section">
    <div class="section-title">Advice for continuing cares & Follow up:</div>
    <div class="text-content">${
      Array.isArray(advice)
        ? advice.map(a => escapeHtml(a)).join('<br>')
        : escapeHtml(advice || 'Follow up as needed')
    }</div>
  </div>

  <!-- SIGNATURE -->
  <div style="margin-top: 40px; border-top: 1px solid #000; padding-top: 20px;">
    <div><strong>Signature & Name</strong></div>
    <div style="margin-top: 30px;">_______________________________</div>
  </div>

</body>
</html>
  `.trim();
}

/**
 * Generate HTML for full ophthalmology consultation (4-page format)
 * Based on ophthal_consultation_full.md
 */
function generateFullConsultationHtml(
  data: Record<string, any>,
  template: ActivatedTemplate | null
): string {
  const patientDetails = data.patient_details || data.patient_information || data.patientDemographics || {};
  const pastHistory = data.past_history || data.past_ocular_history || data.pastOcularHistory || '';
  const currentTreatment = data.current_treatment || data.currentTreatment || '';
  const complaints = data.complaints || data.chief_complaints || data.chiefComplaints || '';

  // Refraction data
  const eyeRefraction = data.eye_refraction || data.eyeRefraction || data.visualAcuity || {};
  const kReading = data.k_reading || data.kReading || data.keratometry || {};

  // Cover test data
  const coverTestWithGlass = data.cover_test_with_glass || data.coverTestWithGlass || {};
  const coverTestWithoutGlass = data.cover_test_without_glass || data.coverTestWithoutGlass || {};

  // Additional tests
  const tests = data.tests || {};
  const colourVision = data.colour_vision || data.colourVision || {};
  const amslersTest = data.amslers_test || data.amslersTest || {};

  // Dry eye assessments
  const dryEye = data.dry_eye || data.dryEye || {};

  // Standard examinations
  const slitLamp = data.slit_lamp_examination || data.slit_lamp || data.slitLampExamination || {};
  const iop = data.iop || data.intra_ocular_pressure || data.intraocularPressure || {};
  const gonioscopy = data.gonioscopy || {};
  const fundus = data.fundus || data.fundus_examination || data.fundusExamination || {};

  // Visual field and advanced tests
  const diurnalIOP = data.diurnal_iop || data.diurnalIOP || [];
  const hvf = data.hvf || data.humphrey_visual_field || {};

  // Clinical outcomes
  const diagnosis = data.diagnosis || '';
  const procedures = data.procedures || '';
  const doctorRecommendation = data.doctor_recommendation || data.doctorRecommendation || data.advice || '';
  const doctorNotes = data.doctor_notes || data.doctorNotes || '';
  const investigation = data.investigation || data.investigations || '';

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ophthalmology Consultation Form</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Times New Roman', Times, serif;
      font-size: 10pt;
      line-height: 1.3;
      padding: 0.5in;
      max-width: 8.5in;
      margin: 0 auto;
      background: white;
      color: #000;
    }
    .header {
      text-align: center;
      margin-bottom: 15px;
      border-bottom: 3px solid #000;
      padding-bottom: 8px;
    }
    .header h1 {
      font-size: 18pt;
      font-weight: bold;
      margin-bottom: 5px;
    }
    .form-id {
      font-size: 9pt;
      color: #666;
    }
    .section {
      margin-bottom: 12px;
      page-break-inside: avoid;
    }
    .section-title {
      font-weight: bold;
      border-bottom: 2px solid #000;
      margin-bottom: 6px;
      padding-bottom: 2px;
      font-size: 11pt;
    }
    .patient-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-bottom: 10px;
    }
    .field {
      margin-bottom: 4px;
      font-size: 10pt;
    }
    .field-label {
      font-weight: bold;
      display: inline-block;
    }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      margin: 8px 0;
      font-size: 9pt;
    }
    .data-table th,
    .data-table td {
      border: 1px solid #000;
      padding: 4px 6px;
      text-align: left;
    }
    .data-table th {
      background: #d0d0d0;
      font-weight: bold;
      text-align: center;
    }
    .data-table td:first-child {
      font-weight: bold;
      background: #f0f0f0;
    }
    .bilateral-table {
      width: 100%;
      border-collapse: collapse;
      margin: 8px 0;
      font-size: 9pt;
    }
    .bilateral-table th,
    .bilateral-table td {
      border: 1px solid #000;
      padding: 4px;
      text-align: center;
    }
    .bilateral-table th {
      background: #d0d0d0;
      font-weight: bold;
    }
    .text-content {
      padding: 6px;
      border: 1px solid #ccc;
      background: #f9f9f9;
      min-height: 30px;
      white-space: pre-wrap;
    }
    .page-break {
      page-break-before: always;
      margin-top: 20px;
    }
    @media print {
      body { padding: 0.25in; }
      .section { page-break-inside: avoid; }
      .page-break { page-break-before: always; }
    }
  </style>
</head>
<body>

  <!-- HEADER -->
  <div class="header">
    <h1>Ophthalmology Consultation Form</h1>
    <div class="form-id">Form ID: OPH-251203</div>
  </div>

  <!-- PATIENT DETAILS -->
  <div class="section">
    <div class="section-title">Student Details</div>
    <div class="patient-grid">
      <div class="field"><span class="field-label">Name:</span> ${escapeHtml(patientDetails.name || patientDetails.patient_name || 'N/A')}</div>
      <div class="field"><span class="field-label">MR.No:</span> ${escapeHtml(patientDetails.mrno || patientDetails.mr_no || 'N/A')}</div>
      <div class="field"><span class="field-label">Date:</span> ${escapeHtml(patientDetails.date || new Date().toLocaleDateString())}</div>
      <div class="field"><span class="field-label">Visit Id:</span> ${escapeHtml(patientDetails.visit_id || 'N/A')}</div>
      <div class="field"><span class="field-label">Age:</span> ${escapeHtml(patientDetails.age || 'N/A')}</div>
      <div class="field"><span class="field-label">Gender:</span> ${escapeHtml(patientDetails.gender || 'N/A')}</div>
    </div>
  </div>

  <!-- PAST OCULAR HISTORY -->
  <div class="section">
    <div class="section-title">Past Ocular History</div>
    <div class="text-content">${escapeHtml(pastHistory || 'No significant past ocular history')}</div>
  </div>

  <!-- CURRENT TREATMENT -->
  <div class="section">
    <div class="section-title">Current Treatment</div>
    <div class="text-content">${escapeHtml(currentTreatment || 'None')}</div>
  </div>

  <!-- COMPLAINTS -->
  <div class="section">
    <div class="section-title">Complaints</div>
    <div class="text-content">${escapeHtml(complaints || 'No specific complaints reported')}</div>
  </div>

  <!-- EYE REFRACTION -->
  <div class="section">
    <div class="section-title">Eye Refraction</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Right Eye Vision</th>
          <th>Left Eye Vision</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Unaided Vision</td>
          <td>${escapeHtml(eyeRefraction.unaided?.rightEye || eyeRefraction.rightEye?.unaided || '')}</td>
          <td>${escapeHtml(eyeRefraction.unaided?.leftEye || eyeRefraction.leftEye?.unaided || '')}</td>
        </tr>
        <tr>
          <td>Aided Vision</td>
          <td>${escapeHtml(eyeRefraction.aided?.rightEye || eyeRefraction.rightEye?.aided || '')}</td>
          <td>${escapeHtml(eyeRefraction.aided?.leftEye || eyeRefraction.leftEye?.aided || '')}</td>
        </tr>
        <tr>
          <td>Student Glasses</td>
          <td>${escapeHtml(eyeRefraction.patient_glasses?.rightEye || eyeRefraction.rightEye?.patient_glasses || '')}</td>
          <td>${escapeHtml(eyeRefraction.patient_glasses?.leftEye || eyeRefraction.leftEye?.patient_glasses || '')}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- K READING -->
  <div class="section">
    <div class="section-title">K Reading</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Eye</th>
          <th>Horizontal Axis</th>
          <th>Vertical Axis</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>RIGHT</td>
          <td>${escapeHtml(kReading.right?.horizontal || kReading.rightEye?.horizontal || '')}</td>
          <td>${escapeHtml(kReading.right?.vertical || kReading.rightEye?.vertical || '')}</td>
        </tr>
        <tr>
          <td>LEFT</td>
          <td>${escapeHtml(kReading.left?.horizontal || kReading.leftEye?.horizontal || '')}</td>
          <td>${escapeHtml(kReading.left?.vertical || kReading.leftEye?.vertical || '')}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- COVER TEST - WITH GLASS -->
  <div class="section">
    <div class="section-title">Cover Test - With Glass</div>
    <div class="field"><strong>Cover test:</strong> Dist: ${escapeHtml(coverTestWithGlass.cover?.dist || '')}, Near: ${escapeHtml(coverTestWithGlass.cover?.near || '')}</div>
    <div class="field"><strong>Uncover test:</strong> Dist: ${escapeHtml(coverTestWithGlass.uncover?.dist || '')}, Near: ${escapeHtml(coverTestWithGlass.uncover?.near || '')}</div>
    <div class="field"><strong>Alternate Cover Test:</strong> Dist: ${escapeHtml(coverTestWithGlass.alternate?.dist || '')}, Near: ${escapeHtml(coverTestWithGlass.alternate?.near || '')}</div>
  </div>

  <!-- COVER TEST - WITHOUT GLASS -->
  <div class="section">
    <div class="section-title">Cover Test - Without Glass</div>
    <div class="field"><strong>Cover test:</strong> Dist: ${escapeHtml(coverTestWithoutGlass.cover?.dist || '')}, Near: ${escapeHtml(coverTestWithoutGlass.cover?.near || '')}</div>
    <div class="field"><strong>Uncover test:</strong> Dist: ${escapeHtml(coverTestWithoutGlass.uncover?.dist || '')}, Near: ${escapeHtml(coverTestWithoutGlass.uncover?.near || '')}</div>
    <div class="field"><strong>Alternate Cover Test:</strong> Dist: ${escapeHtml(coverTestWithoutGlass.alternate?.dist || '')}, Near: ${escapeHtml(coverTestWithoutGlass.alternate?.near || '')}</div>
  </div>

  <!-- PAGE BREAK -->
  <div class="page-break"></div>

  <!-- ADDITIONAL TESTS -->
  <div class="section">
    <div class="section-title">Tests</div>
    <div class="field"><strong>Fixation:</strong> ${escapeHtml(tests.fixation || '')}</div>
    <div class="field"><strong>Stereopsis:</strong> ${escapeHtml(tests.stereopsis || '')}</div>
    <div class="field"><strong>A/V pattern:</strong> ${escapeHtml(tests.av_pattern || '')}</div>
    <div class="field"><strong>Worth Four Dot Test:</strong> ${escapeHtml(tests.worth_four_dot || '')}</div>
    <div class="field"><strong>Bagolini's test:</strong> ${escapeHtml(tests.bagolini || '')}</div>
    <div class="field"><strong>Face / External Eye Exam:</strong> ${escapeHtml(tests.external_exam || '')}</div>
  </div>

  <!-- COLOUR VISION -->
  <div class="section">
    <div class="section-title">Colour Vision</div>
    <div class="field"><strong>OD:</strong> ${escapeHtml(colourVision.od || colourVision.rightEye || '')}</div>
    <div class="field"><strong>OS:</strong> ${escapeHtml(colourVision.os || colourVision.leftEye || '')}</div>
  </div>

  <!-- AMSLER'S TEST -->
  <div class="section">
    <div class="section-title">Amsler's Test</div>
    <div class="field"><strong>OD:</strong> ${escapeHtml(amslersTest.od || amslersTest.rightEye || '')}</div>
    <div class="field"><strong>OS:</strong> ${escapeHtml(amslersTest.os || amslersTest.leftEye || '')}</div>
  </div>

  <!-- DRY EYE ASSESSMENT -->
  <div class="section">
    <div class="section-title">Dry Eye</div>
    <div class="field"><strong>OSDI Questionnaire:</strong> ${escapeHtml(dryEye.osdi || '')}</div>
    <div class="field"><strong>Schirmer's test I (without Paracaine):</strong> OD: ${escapeHtml(dryEye.schirmer_i?.od || '')}, OS: ${escapeHtml(dryEye.schirmer_i?.os || '')}</div>
    <div class="field"><strong>Schirmer's test II (with Paracaine):</strong> OD: ${escapeHtml(dryEye.schirmer_ii?.od || '')}, OS: ${escapeHtml(dryEye.schirmer_ii?.os || '')}</div>
    <div class="field"><strong>Tear Film Break Up Time:</strong> OD: ${escapeHtml(dryEye.tbut?.od || '')}, OS: ${escapeHtml(dryEye.tbut?.os || '')}</div>
    <div class="field"><strong>Fluorescein Staining:</strong> OD: ${escapeHtml(dryEye.fluorescein?.od || '')}, OS: ${escapeHtml(dryEye.fluorescein?.os || '')}</div>
    <div class="field"><strong>Lissamine Green Staining:</strong> OD: ${escapeHtml(dryEye.lissamine?.od || '')}, OS: ${escapeHtml(dryEye.lissamine?.os || '')}</div>
  </div>

  <!-- SLIT LAMP EXAMINATION -->
  <div class="section">
    <div class="section-title">Slit Lamp Examination</div>
    <table class="bilateral-table">
      <thead>
        <tr>
          <th style="width: 25%;">Component</th>
          <th>RIGHT</th>
          <th>LEFT</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>LIDS</strong></td>
          <td>${escapeHtml(slitLamp.rightEye?.lidsAndLashes || slitLamp.rightEye?.lids || '')}</td>
          <td>${escapeHtml(slitLamp.leftEye?.lidsAndLashes || slitLamp.leftEye?.lids || '')}</td>
        </tr>
        <tr>
          <td><strong>CONJUNCTIVA</strong></td>
          <td>${escapeHtml(slitLamp.rightEye?.conjunctiva || '')}</td>
          <td>${escapeHtml(slitLamp.leftEye?.conjunctiva || '')}</td>
        </tr>
        <tr>
          <td><strong>CORNEA</strong></td>
          <td>${escapeHtml(slitLamp.rightEye?.cornea || '')}</td>
          <td>${escapeHtml(slitLamp.leftEye?.cornea || '')}</td>
        </tr>
        <tr>
          <td><strong>ANTERIOR CHAMBER</strong></td>
          <td>${escapeHtml(slitLamp.rightEye?.anteriorChamber || slitLamp.rightEye?.anterior_chamber || '')}</td>
          <td>${escapeHtml(slitLamp.leftEye?.anteriorChamber || slitLamp.leftEye?.anterior_chamber || '')}</td>
        </tr>
        <tr>
          <td><strong>IRIS</strong></td>
          <td>${escapeHtml(slitLamp.rightEye?.iris || '')}</td>
          <td>${escapeHtml(slitLamp.leftEye?.iris || '')}</td>
        </tr>
        <tr>
          <td><strong>LENS</strong></td>
          <td>${escapeHtml(slitLamp.rightEye?.lens || '')}</td>
          <td>${escapeHtml(slitLamp.leftEye?.lens || '')}</td>
        </tr>
        <tr>
          <td><strong>PUPIL</strong></td>
          <td>${escapeHtml(slitLamp.rightEye?.pupil || '')}</td>
          <td>${escapeHtml(slitLamp.leftEye?.pupil || '')}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- PAGE BREAK -->
  <div class="page-break"></div>

  <!-- INTRA OCULAR PRESSURE -->
  <div class="section">
    <div class="section-title">Intra Ocular Pressure</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Method</th>
          <th>Time</th>
          <th>Right Eye</th>
          <th>Left Eye</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Applanation</td>
          <td>${escapeHtml(iop.time || '')}</td>
          <td>${escapeHtml(formatIOP(iop.rightEye || iop.right_eye))}</td>
          <td>${escapeHtml(formatIOP(iop.leftEye || iop.left_eye))}</td>
        </tr>
        <tr>
          <td>Pachymetry</td>
          <td></td>
          <td>${escapeHtml(iop.pachymetry?.right || iop.pachymetry?.rightEye || '')}</td>
          <td>${escapeHtml(iop.pachymetry?.left || iop.pachymetry?.leftEye || '')}</td>
        </tr>
        <tr>
          <td>Pachymetry Adjusted</td>
          <td></td>
          <td>${escapeHtml(iop.pachymetry_adjusted?.right || '')}</td>
          <td>${escapeHtml(iop.pachymetry_adjusted?.left || '')}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- GONIOSCOPY -->
  <div class="section">
    <div class="section-title">Gonioscopy</div>
    <div class="text-content">${escapeHtml(gonioscopy.findings || gonioscopy.notes || 'Not performed')}</div>
  </div>

  <!-- FUNDUS -->
  <div class="section">
    <div class="section-title">Fundus</div>
    <div class="field"><strong>FUNDUS:</strong> ${escapeHtml(fundus.dilated ? 'Dilated' : 'Undilated')}</div>

    <div style="margin-top: 10px;">
      <strong>OD (Right Eye)</strong>
      <div class="field">DISC: ${escapeHtml(fundus.rightEye?.opticDisc?.cdRatio || fundus.rightEye?.disc || '')}</div>
      <div class="field">Macula: ${escapeHtml(fundus.rightEye?.macula?.findings || fundus.rightEye?.macula || '')}</div>
      <div class="field">General Fundus: ${escapeHtml(fundus.rightEye?.vessels?.findings || fundus.rightEye?.general_fundus || '')}</div>
    </div>

    <div style="margin-top: 10px;">
      <strong>OS (Left Eye)</strong>
      <div class="field">DISC: ${escapeHtml(fundus.leftEye?.opticDisc?.cdRatio || fundus.leftEye?.disc || '')}</div>
      <div class="field">Macula: ${escapeHtml(fundus.leftEye?.macula?.findings || fundus.leftEye?.macula || '')}</div>
      <div class="field">General Fundus: ${escapeHtml(fundus.leftEye?.vessels?.findings || fundus.leftEye?.general_fundus || '')}</div>
    </div>
  </div>

  <!-- DIURNAL VARIATION OF IOP -->
  ${Array.isArray(diurnalIOP) && diurnalIOP.length > 0 ? `
  <div class="section">
    <div class="section-title">Diurnal Variation of Intra Ocular Pressure (IOP)</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Method</th>
          <th>Time</th>
          <th>Right Eye IOP (mm Hg)</th>
          <th>Left Eye IOP (mm Hg)</th>
        </tr>
      </thead>
      <tbody>
        ${diurnalIOP.map((reading: any) => `
          <tr>
            <td>${escapeHtml(reading.method || 'Applanation')}</td>
            <td>${escapeHtml(reading.time || '')}</td>
            <td>${escapeHtml(reading.right || reading.rightEye || '')}</td>
            <td>${escapeHtml(reading.left || reading.leftEye || '')}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  </div>
  ` : ''}

  <!-- PAGE BREAK -->
  <div class="page-break"></div>

  <!-- HVF (HUMPHREY VISUAL FIELD) -->
  <div class="section">
    <div class="section-title">HVF (Humphrey Visual Field)</div>
    <div class="field"><strong>Strategy:</strong> ${escapeHtml(hvf.strategy || '')}</div>
    <div class="field"><strong>Interpretation:</strong> ${escapeHtml(hvf.interpretation || '')}</div>
    <div class="field"><strong>Mean Deviation:</strong> ${escapeHtml(hvf.mean_deviation || '')}</div>
    <div class="field"><strong>Pattern Deviation:</strong> ${escapeHtml(hvf.pattern_deviation || '')}</div>
    <div class="field"><strong>GHT:</strong> ${escapeHtml(hvf.ght || '')}</div>
    <div class="field"><strong>VFI:</strong> ${escapeHtml(hvf.vfi || '')}</div>
    <div class="field"><strong>OCT:</strong> ${escapeHtml(hvf.oct || '')}</div>
    <div class="field"><strong>TARGET IOP:</strong> ${escapeHtml(hvf.target_iop || '')}</div>
  </div>

  <!-- DIAGNOSIS -->
  <div class="section">
    <div class="section-title">Diagnosis</div>
    <div class="text-content">${
      Array.isArray(diagnosis)
        ? diagnosis.map(d => escapeHtml(d)).join('<br>')
        : escapeHtml(diagnosis || 'To be determined')
    }</div>
  </div>

  <!-- PROCEDURES -->
  <div class="section">
    <div class="section-title">Procedures</div>
    <div class="text-content">${escapeHtml(procedures || 'None performed')}</div>
  </div>

  <!-- DOCTOR RECOMMENDATION -->
  <div class="section">
    <div class="section-title">Counsellor Recommendation</div>
    <div class="text-content">${escapeHtml(doctorRecommendation || 'Follow up as needed')}</div>
  </div>

  <!-- DOCTOR NOTES -->
  <div class="section">
    <div class="section-title">Counsellor Notes</div>
    <div class="text-content">${escapeHtml(doctorNotes || '')}</div>
  </div>

  <!-- INVESTIGATION -->
  <div class="section">
    <div class="section-title">Investigation</div>
    <div class="text-content">${escapeHtml(investigation || '')}</div>
  </div>

  <!-- SIGNATURE -->
  <div style="margin-top: 40px; border-top: 1px solid #000; padding-top: 20px;">
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div>
        <div><strong>Counsellor Name:</strong> _______________________</div>
        <div style="margin-top: 15px;"><strong>Date:</strong> ${new Date().toLocaleDateString()}</div>
      </div>
      <div>
        <div><strong>Signature:</strong></div>
        <div style="margin-top: 30px;">_______________________</div>
      </div>
    </div>
  </div>

</body>
</html>
  `.trim();
}

/**
 * Generate HTML for ophthalmology discharge summary
 * Based on OPHTHALMOLOGY_DISCHARGE_REFERENCE.md
 */
function generateDischargeHtml(
  data: Record<string, any>,
  template: ActivatedTemplate | null
): string {
  const patientDetails = data.patient_details || data.patient_information || data.patientDemographics || {};

  // Handle diagnosis - can be string, object with leftEye/rightEye, or array
  let diagnosisText = '';
  if (typeof data.diagnosis === 'string') {
    diagnosisText = data.diagnosis;
  } else if (data.diagnosis && typeof data.diagnosis === 'object') {
    const diagnosisParts: string[] = [];
    if (data.diagnosis.leftEye || data.diagnosis.os) {
      diagnosisParts.push(`OS (Left Eye): ${data.diagnosis.leftEye || data.diagnosis.os}`);
    }
    if (data.diagnosis.rightEye || data.diagnosis.od) {
      diagnosisParts.push(`OD (Right Eye): ${data.diagnosis.rightEye || data.diagnosis.od}`);
    }
    if (data.diagnosis.bilateral || data.diagnosis.both) {
      diagnosisParts.push(`Both Eyes: ${data.diagnosis.bilateral || data.diagnosis.both}`);
    }
    diagnosisText = diagnosisParts.join('; ') || 'Not specified';
  } else {
    diagnosisText = 'Not specified';
  }

  // Handle treatment given - can be string or object with procedure details
  let treatmentText = '';
  if (typeof data.treatmentGiven === 'object' && data.treatmentGiven !== null) {
    const tg = data.treatmentGiven;
    const parts: string[] = [];
    if (tg.procedure) parts.push(tg.procedure);
    if (tg.technique) parts.push(tg.technique);
    if (tg.eye) parts.push(`(${tg.eye})`);
    if (tg.date) parts.push(`on ${tg.date}`);
    treatmentText = parts.join(' ');
  } else {
    treatmentText = data.treatment_given || data.treatmentGiven || data.procedure || '';
  }

  // Admission/discharge status
  const conditionOnAdmission = data.admissionStatus?.conditionOnAdmission || data.condition_on_admission || 'Fair';
  const conditionOnDischarge = data.dischargeStatus?.conditionOnDischarge || data.condition_on_discharge || 'Good';
  const nutritionalStatus = data.admissionStatus?.nutritionalStatus || data.nutritional_status || 'Normal';

  // Medications
  const dischargeMedication = data.discharge_medication || data.dischargeMedication || data.medications || [];

  // Advice and instructions
  const advice = data.advice || data.advice_on_discharge || data.dischargeAdvice?.advice || '';
  const emergencySymptoms = data.emergency_symptoms || data.emergencyContact?.emergencySymptoms || [];
  const diet = data.diet || data.dischargeAdvice?.diet || 'Normal';
  const physicalActivity = data.physical_activity || data.dischargeAdvice?.physicalActivity || 'Normal';
  const specialInstructions = data.special_instructions || data.dischargeAdvice?.specialInstructions || [];
  const reviewDate = data.review_date || data.next_review || data.dischargeAdvice?.reviewDate || '';

  // Admission/procedure dates
  const dateOfAdmission = data.date_of_admission || data.admissionDetails?.dateOfAdmission || '';
  const dateOfProcedure = data.date_of_procedure || data.admissionDetails?.dateOfProcedure || data.treatmentGiven?.date || '';

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ophthalmology Discharge Summary</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Times New Roman', Times, serif;
      font-size: 12pt;
      line-height: 1.4;
      padding: 0.75in;
      max-width: 8.5in;
      margin: 0 auto;
      background: white;
      color: #000;
    }
    .header {
      text-align: center;
      margin-bottom: 20px;
      border-bottom: 3px solid #000;
      padding-bottom: 10px;
    }
    .header h1 {
      font-size: 20pt;
      font-weight: bold;
      text-transform: uppercase;
      margin-bottom: 5px;
    }
    .patient-box {
      border: 2px solid #000;
      padding: 15px;
      margin-bottom: 20px;
      background: #f5f5f5;
    }
    .patient-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .field {
      margin-bottom: 8px;
    }
    .field-label {
      font-weight: bold;
      display: inline-block;
      min-width: 120px;
    }
    .section {
      margin-bottom: 18px;
      page-break-inside: avoid;
    }
    .section-title {
      font-weight: bold;
      font-size: 13pt;
      margin-bottom: 8px;
      text-decoration: underline;
    }
    .text-content {
      white-space: pre-wrap;
      line-height: 1.6;
    }
    .medication-table {
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0;
    }
    .medication-table th,
    .medication-table td {
      border: 1px solid #000;
      padding: 8px;
      text-align: left;
    }
    .medication-table th {
      background: #d0d0d0;
      font-weight: bold;
    }
    .instructions-list {
      list-style-type: disc;
      margin-left: 25px;
      line-height: 1.8;
    }
    .emergency-box {
      border: 2px solid #c00;
      background: #fff0f0;
      padding: 15px;
      margin: 15px 0;
    }
    .emergency-box .section-title {
      color: #c00;
    }
    @media print {
      body { padding: 0.5in; }
      .section { page-break-inside: avoid; }
    }
  </style>
</head>
<body>

  <!-- HEADER -->
  <div class="header">
    <h1>Discharge Summary</h1>
  </div>

  <!-- PATIENT DETAILS -->
  <div class="patient-box">
    <div style="font-weight: bold; font-size: 14pt; margin-bottom: 12px; border-bottom: 1px solid #333; padding-bottom: 5px;">
      STUDENT DETAILS
    </div>
    <div class="patient-grid">
      <div class="field">
        <span class="field-label">Name:</span>
        <span>${escapeHtml(patientDetails.name || patientDetails.patient_name || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">Visit ID:</span>
        <span>${escapeHtml(patientDetails.visit_id || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">MRNO:</span>
        <span>${escapeHtml(patientDetails.mrno || patientDetails.mr_no || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">Date:</span>
        <span>${escapeHtml(patientDetails.date || new Date().toLocaleDateString())}</span>
      </div>
      <div class="field">
        <span class="field-label">Age:</span>
        <span>${escapeHtml(patientDetails.age || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">Gender:</span>
        <span>${escapeHtml(patientDetails.gender || 'N/A')}</span>
      </div>
    </div>
  </div>

  <!-- ADMISSION & PROCEDURE DATES -->
  <div class="section">
    <div class="patient-grid">
      <div class="field">
        <span class="field-label">Date of Admission:</span>
        <span>${escapeHtml(dateOfAdmission || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">Date of Procedure:</span>
        <span>${escapeHtml(dateOfProcedure || 'N/A')}</span>
      </div>
    </div>
  </div>

  <!-- DIAGNOSIS -->
  <div class="section">
    <div class="section-title">Diagnosis:</div>
    <div class="text-content">${escapeHtml(diagnosisText)}</div>
  </div>

  <div class="section">
    <div class="field">
      <span class="field-label">Condition of the student on admission:</span>
      <span>${escapeHtml(conditionOnAdmission)}</span>
    </div>
    <div class="field">
      <span class="field-label">Nutritional Status:</span>
      <span>${escapeHtml(nutritionalStatus)}</span>
    </div>
  </div>

  <!-- TREATMENT GIVEN -->
  <div class="section">
    <div class="section-title">Treatment given with dates:</div>
    <div class="text-content">${escapeHtml(treatmentText || 'Not specified')}</div>
  </div>

  <!-- CONDITION ON DISCHARGE -->
  <div class="section">
    <div class="field">
      <span class="field-label">Condition of the student on discharge:</span>
      <span>${escapeHtml(conditionOnDischarge)}</span>
    </div>
  </div>

  <!-- DISCHARGE MEDICATION & ADVICE -->
  <div class="section">
    <div class="section-title">Discharge Medication & Advice on Discharge:</div>

    <div style="margin: 15px 0;">
      <div class="field">
        <span class="field-label">Diet:</span>
        <span>${escapeHtml(diet)}</span>
      </div>
      <div class="field">
        <span class="field-label">Physical Activity:</span>
        <span>${escapeHtml(physicalActivity)}</span>
      </div>
    </div>

    ${Array.isArray(dischargeMedication) && dischargeMedication.length > 0 ? `
    <div style="margin: 15px 0;">
      <strong>Medications:</strong>
      <table class="medication-table">
        <thead>
          <tr>
            <th style="width: 5%;">#</th>
            <th style="width: 25%;">Medicine</th>
            <th style="width: 10%;">Eye</th>
            <th style="width: 15%;">Dosage</th>
            <th style="width: 12%;">Frequency</th>
            <th style="width: 12%;">Duration</th>
            <th style="width: 21%;">Instructions</th>
          </tr>
        </thead>
        <tbody>
          ${dischargeMedication.map((med: any, idx: number) => `
            <tr>
              <td>${idx + 1}</td>
              <td>${escapeHtml(med.medicationName || med.name || med.medication || '')}</td>
              <td>${escapeHtml(med.eye || med.route || '')}</td>
              <td>${escapeHtml(med.dosage || med.strength || '')}</td>
              <td>${escapeHtml(med.frequency || '')}</td>
              <td>${escapeHtml(med.duration || '')}</td>
              <td style="font-size: 9pt;">${escapeHtml(med.instructions || med.timing || '')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
    ` : ''}

    ${Array.isArray(specialInstructions) && specialInstructions.length > 0 ? `
    <div style="margin: 15px 0;">
      <strong>Special Instructions:</strong>
      <ul class="instructions-list">
        ${specialInstructions.map((instruction: string) => `
          <li>${escapeHtml(instruction)}</li>
        `).join('')}
      </ul>
    </div>
    ` : ''}

    ${reviewDate ? `
    <div class="field" style="margin-top: 15px;">
      <span class="field-label">Next Review:</span>
      <span>${escapeHtml(reviewDate)}</span>
    </div>
    ` : ''}
  </div>

  <!-- EMERGENCY CONTACT INFORMATION -->
  ${Array.isArray(emergencySymptoms) && emergencySymptoms.length > 0 ? `
  <div class="emergency-box">
    <div class="section-title">Please Contact the school immediately if student has the following symptoms:</div>
    <ul class="instructions-list">
      ${emergencySymptoms.map((symptom: string) => `
        <li>${escapeHtml(symptom)}</li>
      `).join('')}
    </ul>
  </div>
  ` : ''}

  <!-- SIGNATURE -->
  <div style="margin-top: 50px; border-top: 1px solid #000; padding-top: 20px;">
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div>
        <div><strong>Telephone No.:</strong> _______________________</div>
        <div style="margin-top: 10px;"><strong>Name:</strong> _______________________</div>
      </div>
      <div>
        <div><strong>Mobile No.:</strong> _______________________</div>
        <div style="margin-top: 10px;"><strong>Signature:</strong> _______________________</div>
      </div>
    </div>
    <div style="margin-top: 15px;">
      <strong>Reg. No.:</strong> _______________________
    </div>
  </div>

</body>
</html>
  `.trim();
}

/**
 * Generate HTML for optometry consultation
 * Based on OPTOMETRIST_EXAMINATION_REFERENCE.md
 */
function generateOptometryHtml(
  data: Record<string, any>,
  template: ActivatedTemplate | null
): string {
  const patientDetails = data.patient_details || data.patient_information || data.patientDemographics || {};
  const referralInfo = data.referral_information || data.referralInformation || {};
  const referralType = referralInfo.referralType || data.referral_type || data.referralType || 'Routine';
  const clinicalNotes = data.clinical_notes || data.clinicalNotes || data.notes || '';

  // Vision measurements - support both nested and top-level structures
  const vision = data.vision || data.visualAcuity || {};
  const refraction = data.refraction || {};

  // Support direct rightEye/leftEye at top level (optometry extraction format)
  const rightEye = data.rightEye || {};
  const leftEye = data.leftEye || {};

  // Glaucoma assessment - support nested structure
  const glaucomaAssessment = data.glaucomaAssessment || data.glaucoma_assessment || {};
  const cdRatio = glaucomaAssessment.cdRatio || data.cd_ratio || data.cdRatio || data.cup_disc_ratio || {};
  const iop = glaucomaAssessment.iop || data.iop || data.intraocularPressure || {};
  const visualField = glaucomaAssessment.visualField || data.visual_field || data.visualField || {};

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Optometrist Examination Form</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: Arial, sans-serif;
      font-size: 11pt;
      line-height: 1.4;
      padding: 0.5in;
      max-width: 8.5in;
      margin: 0 auto;
      background: white;
      color: #000;
    }
    .header {
      text-align: center;
      margin-bottom: 20px;
      border-bottom: 2px solid #000;
      padding-bottom: 10px;
    }
    .header h1 {
      font-size: 16pt;
      font-weight: bold;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .header .subtitle {
      font-size: 12pt;
      font-weight: bold;
    }
    .section {
      margin-bottom: 15px;
      page-break-inside: avoid;
    }
    .section-title {
      font-weight: bold;
      margin-bottom: 8px;
      font-size: 12pt;
    }
    .patient-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 15px;
    }
    .field {
      margin-bottom: 6px;
    }
    .field-label {
      font-weight: bold;
      display: inline-block;
      min-width: 100px;
    }
    .referral-options {
      display: flex;
      gap: 15px;
      margin: 10px 0;
    }
    .checkbox-option {
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .checkbox {
      width: 15px;
      height: 15px;
      border: 2px solid #000;
      display: inline-block;
    }
    .checkbox.checked::after {
      content: '✓';
      display: block;
      text-align: center;
      font-weight: bold;
      line-height: 11px;
    }
    .vision-table {
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0;
    }
    .vision-table th,
    .vision-table td {
      border: 1px solid #000;
      padding: 8px;
      text-align: center;
    }
    .vision-table th {
      background: #e0e0e0;
      font-weight: bold;
    }
    .vision-table td:first-child {
      text-align: left;
      font-weight: bold;
      background: #f5f5f5;
    }
    .glaucoma-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 15px;
      margin: 10px 0;
    }
    .glaucoma-item {
      border: 1px solid #ddd;
      padding: 10px;
      background: #f9f9f9;
    }
    .glaucoma-item .label {
      font-weight: bold;
      margin-bottom: 5px;
    }
    .clinical-notes {
      border: 1px solid #000;
      padding: 15px;
      min-height: 150px;
      background: #fff;
      white-space: pre-wrap;
    }
    .signature-line {
      margin-top: 40px;
      border-top: 1px solid #000;
      padding-top: 10px;
    }
    @media print {
      body { padding: 0.25in; }
      .section { page-break-inside: avoid; }
    }
  </style>
</head>
<body>

  <!-- HEADER -->
  <div class="header">
    <h1>Optometrist Examination Form</h1>
    <div class="subtitle">To the Ophthalmologist:</div>
  </div>

  <!-- PATIENT DEMOGRAPHICS -->
  <div class="section">
    <div class="patient-grid">
      <div class="field">
        <span class="field-label">Date:</span>
        <span>${escapeHtml(patientDetails.date || new Date().toLocaleDateString())}</span>
      </div>
      <div class="field">
        <span class="field-label">MR. No.:</span>
        <span>${escapeHtml(patientDetails.mr_no || patientDetails.mrno || patientDetails.student_id || 'N/A')}</span>
      </div>
    </div>

    <!-- Referral Type -->
    <div class="section-title">Referral Type:</div>
    <div class="referral-options">
      <div class="checkbox-option">
        <span class="checkbox ${referralType.toLowerCase() === 'routine' ? 'checked' : ''}"></span>
        <span>Routine</span>
      </div>
      <div class="checkbox-option">
        <span class="checkbox ${referralType.toLowerCase() === 'asap' ? 'checked' : ''}"></span>
        <span>ASAP</span>
      </div>
      <div class="checkbox-option">
        <span class="checkbox ${referralType.toLowerCase() === 'urgent' ? 'checked' : ''}"></span>
        <span>Urgent</span>
      </div>
      <div class="checkbox-option">
        <span class="checkbox ${referralType.toLowerCase() === 'emergency' ? 'checked' : ''}"></span>
        <span>Emergency</span>
      </div>
    </div>

    <!-- Student Information -->
    <div class="patient-grid" style="margin-top: 15px;">
      <div class="field">
        <span class="field-label">Title:</span>
        <span>${escapeHtml(patientDetails.title || 'Mr.')}</span>
      </div>
      <div class="field">
        <span class="field-label">DOB:</span>
        <span>${escapeHtml(patientDetails.dob || patientDetails.date_of_birth || 'N/A')}</span>
      </div>
      <div class="field">
        <span class="field-label">Surname:</span>
        <span>${escapeHtml(patientDetails.surname || patientDetails.last_name || '')}</span>
      </div>
      <div class="field">
        <span class="field-label">Name:</span>
        <span>${escapeHtml(patientDetails.name || patientDetails.first_name || patientDetails.patient_name || 'N/A')}</span>
      </div>
    </div>
    <div class="field">
      <span class="field-label">Address:</span>
      <span>${escapeHtml(patientDetails.address || 'N/A')}</span>
    </div>
  </div>

  <!-- VISION MEASUREMENTS -->
  <div class="section">
    <div class="section-title">Vision Measurements</div>
    <table class="vision-table">
      <thead>
        <tr>
          <th style="width: 10%;">Eye</th>
          <th style="width: 18%;">Vision</th>
          <th style="width: 24%;">Refraction</th>
          <th style="width: 16%;">VA (dist)</th>
          <th style="width: 16%;">Add</th>
          <th style="width: 16%;">VA (near)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>RE</td>
          <td>${escapeHtml(
            rightEye.vision ||
            vision.rightEye?.unaided || vision.right_eye?.unaided || vision.re?.vision ||
            ''
          )}</td>
          <td>${escapeHtml(
            formatRefraction(rightEye.refraction) ||
            formatRefraction(refraction.rightEye || refraction.right_eye || refraction.re)
          )}</td>
          <td>${escapeHtml(
            rightEye.vaDistance ||
            vision.rightEye?.distance || vision.right_eye?.distance || vision.re?.distance ||
            ''
          )}</td>
          <td>${escapeHtml(
            rightEye.add ||
            vision.rightEye?.add || vision.right_eye?.add || refraction.rightEye?.add ||
            ''
          )}</td>
          <td>${escapeHtml(
            rightEye.vaNear ||
            vision.rightEye?.near || vision.right_eye?.near || vision.re?.near ||
            ''
          )}</td>
        </tr>
        <tr>
          <td>LE</td>
          <td>${escapeHtml(
            leftEye.vision ||
            vision.leftEye?.unaided || vision.left_eye?.unaided || vision.le?.vision ||
            ''
          )}</td>
          <td>${escapeHtml(
            formatRefraction(leftEye.refraction) ||
            formatRefraction(refraction.leftEye || refraction.left_eye || refraction.le)
          )}</td>
          <td>${escapeHtml(
            leftEye.vaDistance ||
            vision.leftEye?.distance || vision.left_eye?.distance || vision.le?.distance ||
            ''
          )}</td>
          <td>${escapeHtml(
            leftEye.add ||
            vision.leftEye?.add || vision.left_eye?.add || refraction.leftEye?.add ||
            ''
          )}</td>
          <td>${escapeHtml(
            leftEye.vaNear ||
            vision.leftEye?.near || vision.left_eye?.near || vision.le?.near ||
            ''
          )}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- GLAUCOMA ASSESSMENT -->
  <div class="section">
    <div class="section-title">Glaucoma Assessment</div>
    <div class="glaucoma-grid">
      <!-- C/D Ratio -->
      <div class="glaucoma-item">
        <div class="label">Cup-to-Disc Ratio (C/D ratio)</div>
        <div class="field">
          <span class="field-label">R:</span>
          <span>${escapeHtml(
            glaucomaAssessment.cdRatioRight ||
            cdRatio.right || cdRatio.rightEye || cdRatio.od || cdRatio.r ||
            'N/A'
          )}</span>
        </div>
        <div class="field">
          <span class="field-label">L:</span>
          <span>${escapeHtml(
            glaucomaAssessment.cdRatioLeft ||
            cdRatio.left || cdRatio.leftEye || cdRatio.os || cdRatio.l ||
            'N/A'
          )}</span>
        </div>
      </div>

      <!-- IOP -->
      <div class="glaucoma-item">
        <div class="label">Intraocular Pressure (IOP mmHg)</div>
        <div class="field">
          <span class="field-label">R:</span>
          <span>${escapeHtml(
            formatIOP(glaucomaAssessment.iopRight) ||
            formatIOP(iop.rightEye || iop.right_eye || iop.od || iop.r)
          )}</span>
        </div>
        <div class="field">
          <span class="field-label">L:</span>
          <span>${escapeHtml(
            formatIOP(glaucomaAssessment.iopLeft) ||
            formatIOP(iop.leftEye || iop.left_eye || iop.os || iop.l)
          )}</span>
        </div>
      </div>

      <!-- Visual Field -->
      <div class="glaucoma-item" style="grid-column: 1 / -1;">
        <div class="label">Visual Field</div>
        <div class="field">
          <span class="field-label">R:</span>
          <span>${escapeHtml(
            glaucomaAssessment.visualFieldRight ||
            visualField.right || visualField.rightEye || visualField.od ||
            'Full'
          )}</span>
        </div>
        <div class="field">
          <span class="field-label">L:</span>
          <span>${escapeHtml(
            glaucomaAssessment.visualFieldLeft ||
            visualField.left || visualField.leftEye || visualField.os ||
            'Full'
          )}</span>
        </div>
      </div>
    </div>
  </div>

  <!-- CLINICAL NOTES -->
  <div class="section">
    <div class="section-title">Clinical Notes</div>
    <div class="clinical-notes">${escapeHtml(clinicalNotes || 'No clinical notes provided.')}</div>
  </div>

  <!-- SIGNATURE -->
  <div class="signature-line">
    <div class="field">
      <span class="field-label">Signature:</span>
      <span>_______________________________</span>
    </div>
  </div>

</body>
</html>
  `.trim();
}

/**
 * Generate generic ophthalmology HTML when specific type is not matched
 */
function generateGenericOphthalHtml(
  data: Record<string, any>,
  template: ActivatedTemplate | null
): string {
  const entries = Object.entries(data);

  if (entries.length === 0) {
    return `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="UTF-8">
          <title>Medical Record</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 20px; }
          </style>
        </head>
        <body>
          <p style="color: #999;">No structured data available to render.</p>
        </body>
      </html>
    `;
  }

  const renderValueAsHtml = (value: any): string => {
    if (value == null) {
      return '<span style="color: #999;">Not documented</span>';
    }

    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      return `<span>${escapeHtml(String(value))}</span>`;
    }

    if (Array.isArray(value)) {
      if (value.length === 0) {
        return '<span style="color: #999;">No items</span>';
      }

      if (typeof value[0] === 'string' || typeof value[0] === 'number' || typeof value[0] === 'boolean') {
        return `<ul style="margin: 0; padding-left: 20px;">${value.map(item => `<li>${escapeHtml(String(item))}</li>`).join('')}</ul>`;
      }

      return `<div style="display: flex; flex-direction: column; gap: 8px;">${value.map(item =>
        `<div style="border: 1px solid #ddd; border-radius: 4px; padding: 8px; background: white;">${renderObjectAsHtml(item)}</div>`
      ).join('')}</div>`;
    }

    if (typeof value === 'object') {
      return renderObjectAsHtml(value as Record<string, any>);
    }

    return `<span>${escapeHtml(String(value))}</span>`;
  };

  const renderObjectAsHtml = (obj: Record<string, any>): string => {
    const entries = Object.entries(obj || {});
    if (entries.length === 0) {
      return '<span style="color: #999;">No details</span>';
    }

    return `<dl style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; font-size: 14px;">${entries.map(([k, v]) => `
      <div style="display: flex; flex-direction: column; margin-bottom: 4px;">
        <dt style="font-size: 11px; font-weight: 500; color: #666; text-transform: uppercase; letter-spacing: 0.5px;">
          ${formatSectionTitle(k)}
        </dt>
        <dd style="color: #111; margin: 4px 0 0 0;">
          ${typeof v === 'object' && v !== null ? renderValueAsHtml(v) : escapeHtml(String(v))}
        </dd>
      </div>
    `).join('')}</dl>`;
  };

  const sectionsHtml = entries.map(([key, value]) => `
    <section style="border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; background: #f9fafb; margin-bottom: 12px;">
      <h4 style="font-size: 11px; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">
        ${formatSectionTitle(key)}
      </h4>
      <div style="font-size: 14px; color: #111;">
        ${renderValueAsHtml(value)}
      </div>
    </section>
  `).join('');

  return `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>${template?.consultation_type_name || 'Medical Record'} - ${template?.template_name || 'Consultation Summary'}</title>
        <style>
          * { box-sizing: border-box; }
          body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            padding: 20px;
            background: #fff;
            color: #111;
            max-width: 1000px;
            margin: 0 auto;
          }
          @media print {
            body { padding: 10px; }
            section { page-break-inside: avoid; }
          }
        </style>
      </head>
      <body>
        <div style="border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; margin-bottom: 16px;">
          <div style="font-size: 11px; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.5px;">
            ${template?.consultation_type_name || 'Ophthalmology'}
          </div>
          <div style="font-size: 18px; font-weight: 600; color: #111; margin-top: 4px;">
            ${template?.template_name || 'Consultation Summary'}
          </div>
        </div>
        <div>
          ${sectionsHtml}
        </div>
      </body>
    </html>
  `;
}

/**
 * Generate HTML for ophthalmology prescription (general prescription form)
 * Based on PRESCRIPTION FORM screenshot with numbered medication list
 */
function generatePrescriptionHtml(
  data: Record<string, any>,
  template: ActivatedTemplate | null
): string {
  // Student details
  const patientDetails = data.patientDetails || data.patient_details || {};
  const prescriptionItems = data.prescriptionItems || data.prescription_items || [];
  const continuingMedications = data.continuingMedications || data.continuing_medications || [];
  const additionalNotes = data.additionalNotes || data.additional_notes || '';
  const doctorDetails = data.doctorDetails || data.doctor_details || {};
  const followUp = data.followUp || data.follow_up || {};
  const pharmacyNote = data.pharmacyNote || data.pharmacy_note || 'If the medications prescribed are unavailable, please call us immediately';

  // Build medication items HTML
  const medicationsHtml = prescriptionItems.map((item: any) => {
    const serialNumber = item.serialNumber || item.serial_number || '';
    const medicationName = item.medicationName || item.medication_name || '';
    const dosage = item.dosage || '';
    const frequency = item.frequency || '';
    const duration = item.duration || '';
    const specialInstructions = item.specialInstructions || item.special_instructions || '';
    const eye = item.eye || '';
    const isContinuing = item.isContinuing || item.is_continuing || false;

    // Build instruction string
    const instructionParts: string[] = [];
    if (dosage) instructionParts.push(dosage);
    if (frequency) instructionParts.push(frequency);
    if (eye && eye !== 'N/A') instructionParts.push(`to ${eye}`);
    if (duration) instructionParts.push(`for ${duration}`);
    if (specialInstructions) instructionParts.push(specialInstructions);

    const instructionStr = instructionParts.join(' ');

    return `
      <div class="prescription-item${isContinuing ? ' continuing' : ''}">
        <span class="item-number">${serialNumber}.</span>
        <span class="item-content">${escapeHtml(medicationName)} : ${escapeHtml(instructionStr)}.</span>
      </div>
    `;
  }).join('');

  // Build continuing medications HTML (in parentheses format)
  let continuingHtml = '';
  if (continuingMedications.length > 0) {
    const medStrings = continuingMedications.map((med: any) => {
      const name = med.medicationName || med.medication_name || '';
      const eye = med.eye || '';
      const frequency = med.frequency || '';
      const notes = med.notes || '';

      const parts: string[] = [];
      if (eye) parts.push(`${eye.toLowerCase()}`);
      if (frequency) parts.push(frequency);
      if (notes) parts.push(notes);

      return `${name}${parts.length > 0 ? ' ' + parts.join(' ') : ''}`;
    });

    continuingHtml = `
      <div class="continuing-section">
        <p>(Both eyes-continue ${escapeHtml(medStrings.join(',\n                '))})</p>
      </div>
    `;
  }

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Prescription Form</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Times New Roman', Times, serif;
      font-size: 12pt;
      line-height: 1.5;
      padding: 0.75in;
      max-width: 8.5in;
      margin: 0 auto;
      background: white;
      color: #000;
    }
    .header {
      text-align: center;
      margin-bottom: 30px;
      border-bottom: 2px solid #000;
      padding-bottom: 15px;
    }
    .header h1 {
      font-size: 20pt;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 2px;
    }
    .patient-info {
      margin-bottom: 25px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .field {
      margin-bottom: 8px;
      display: flex;
      align-items: baseline;
    }
    .field-label {
      font-weight: bold;
      min-width: 120px;
    }
    .field-value {
      flex: 1;
      border-bottom: 1px solid #ccc;
      padding-bottom: 2px;
      min-height: 18px;
    }
    .prescription-section {
      margin-top: 30px;
    }
    .prescription-section h2 {
      font-size: 12pt;
      font-weight: bold;
      margin-bottom: 15px;
      text-decoration: underline;
    }
    .prescription-item {
      margin-bottom: 12px;
      display: flex;
      align-items: flex-start;
    }
    .prescription-item.continuing {
      font-style: italic;
    }
    .item-number {
      font-weight: bold;
      min-width: 25px;
    }
    .item-content {
      flex: 1;
    }
    .continuing-section {
      margin-top: 25px;
      padding: 15px;
      background: #f5f5f5;
      border-left: 3px solid #666;
    }
    .continuing-section p {
      white-space: pre-line;
      line-height: 1.6;
    }
    .pharmacy-note {
      margin-top: 30px;
      padding: 15px;
      border: 1px solid #999;
      background: #fff9e6;
      font-size: 11pt;
    }
    .signature-section {
      margin-top: 50px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 50px;
    }
    .signature-box {
      text-align: center;
    }
    .signature-line {
      border-top: 1px solid #000;
      margin-top: 50px;
      padding-top: 5px;
    }
    .stamp-box {
      border: 1px dashed #999;
      min-height: 80px;
      margin-top: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #999;
      font-size: 10pt;
    }
    @media print {
      body { padding: 0.5in; }
      .pharmacy-note { border: 1px solid #666; }
    }
  </style>
</head>
<body>

  <!-- HEADER -->
  <div class="header">
    <h1>Prescription Form</h1>
  </div>

  <!-- PATIENT INFORMATION -->
  <div class="patient-info">
    <div class="field">
      <span class="field-label">Date</span>
      <span>:</span>
      <span class="field-value">${escapeHtml(patientDetails.date || new Date().toLocaleDateString())}</span>
    </div>
    <div class="field">
      <span class="field-label">Visit Id</span>
      <span>:</span>
      <span class="field-value">${escapeHtml(patientDetails.visitId || patientDetails.visit_id || '')}</span>
    </div>
    <div class="field" style="grid-column: 1 / -1;">
      <span class="field-label">Student Name</span>
      <span>:</span>
      <span class="field-value">${escapeHtml(patientDetails.name || '')}</span>
    </div>
    <div class="field">
      <span class="field-label">NIN</span>
      <span>:</span>
      <span class="field-value">${escapeHtml(patientDetails.nin || '')}</span>
    </div>
    <div class="field">
      <span class="field-label">Age</span>
      <span>:</span>
      <span class="field-value">${escapeHtml(patientDetails.age || '')}</span>
    </div>
    <div class="field">
      <span class="field-label">Sex</span>
      <span>:</span>
      <span class="field-value">${escapeHtml(patientDetails.gender || '')}</span>
    </div>
    <div class="field">
      <span class="field-label">MR.No</span>
      <span>:</span>
      <span class="field-value">${escapeHtml(patientDetails.mrNumber || patientDetails.mr_number || '')}</span>
    </div>
    <div class="field" style="grid-column: 1 / -1;">
      <span class="field-label">Address</span>
      <span>:</span>
      <span class="field-value">${escapeHtml(patientDetails.address || '')}</span>
    </div>
  </div>

  <!-- PRESCRIPTION ITEMS -->
  <div class="prescription-section">
    <h2>Please supply the following :</h2>
    ${medicationsHtml}
  </div>

  <!-- CONTINUING MEDICATIONS -->
  ${continuingHtml}

  <!-- ADDITIONAL NOTES -->
  ${additionalNotes ? `
    <div style="margin-top: 20px;">
      <strong>Additional Instructions:</strong>
      <p>${escapeHtml(additionalNotes)}</p>
    </div>
  ` : ''}

  <!-- PHARMACY NOTE -->
  <div class="pharmacy-note">
    <strong>Contact us :</strong>
    <p>${escapeHtml(pharmacyNote)}</p>
  </div>

  <!-- SIGNATURE & STAMP -->
  <div class="signature-section">
    <div class="signature-box">
      <div><strong>Counsellor's Name:</strong></div>
      <div class="signature-line">${escapeHtml(doctorDetails.name || '')}</div>
    </div>
    <div class="signature-box">
      <div><strong>Signature:</strong></div>
      <div class="signature-line"></div>
    </div>
  </div>

  <div style="margin-top: 20px;">
    <div><strong>Stamp:</strong></div>
    <div class="stamp-box">[School Stamp]</div>
  </div>

  <!-- FOLLOW-UP -->
  ${followUp.date || followUp.instructions ? `
    <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #ccc;">
      <strong>Follow-up:</strong>
      ${followUp.date ? `<span>Date: ${escapeHtml(followUp.date)}</span>` : ''}
      ${followUp.instructions ? `<p>${escapeHtml(followUp.instructions)}</p>` : ''}
    </div>
  ` : ''}

</body>
</html>
  `.trim();
}

/**
 * Generate HTML for post-operative medication schedule (table format)
 * Based on POST OPERATIVE MEDICATION screenshot with timing columns
 */
function generatePostOpRxHtml(
  data: Record<string, any>,
  template: ActivatedTemplate | null
): string {
  // Student details
  const patientDetails = data.patientDetails || data.patient_details || {};
  const surgeryDetails = data.surgeryDetails || data.surgery_details || {};
  const medications = data.medications || [];
  const generalInstructions = data.generalInstructions || data.general_instructions || [];
  const followUp = data.followUp || data.follow_up || {};

  // Build medication rows
  const medicationRowsHtml = medications.map((med: any, idx: number) => {
    const serialNumber = med.serialNumber || med.serial_number || (idx + 1).toString();
    const medicationName = med.medicationName || med.medication_name || '';
    const eye = med.eye || '';
    const durationText = med.durationText || med.duration_text || '';
    const dateRange = med.dateRange || med.date_range || '';
    const frequency = med.frequency || 0;
    const specialInstructions = med.specialInstructions || med.special_instructions || '';

    // Get timings
    const timing1 = med.timing1 || '';
    const timing2 = med.timing2 || '';
    const timing3 = med.timing3 || '';
    const timing4 = med.timing4 || '';
    const timing5 = med.timing5 || '';
    const timing6 = med.timing6 || '';

    // Format the days/date column
    const daysDateValue = durationText && dateRange
      ? `${durationText}<br><small>${dateRange}</small>`
      : durationText || dateRange || '';

    // Check if this is a sub-row (e.g., "2a", "2b")
    const isSubRow = /^\d+[a-z]$/.test(serialNumber.toString());
    const rowClass = isSubRow ? 'sub-row' : '';

    return `
      <tr class="${rowClass}">
        <td class="serial-col">${escapeHtml(serialNumber.toString())}</td>
        <td class="med-col">
          ${escapeHtml(medicationName)}
          ${eye ? `<br><small class="eye-spec">${escapeHtml(eye)}</small>` : ''}
        </td>
        <td class="days-col">${daysDateValue}</td>
        <td class="timing-col">${escapeHtml(timing1)}</td>
        <td class="timing-col">${escapeHtml(timing2)}</td>
        <td class="timing-col">${escapeHtml(timing3)}</td>
        <td class="timing-col">${escapeHtml(timing4)}</td>
        <td class="timing-col">${escapeHtml(timing5)}</td>
        <td class="timing-col">${escapeHtml(timing6)}</td>
      </tr>
      ${specialInstructions ? `
        <tr class="instruction-row">
          <td colspan="9" class="special-instructions">${escapeHtml(specialInstructions)}</td>
        </tr>
      ` : ''}
    `;
  }).join('');

  // Build general instructions list
  const instructionsHtml = generalInstructions.length > 0
    ? `<ul>${generalInstructions.map((inst: string) => `<li>${escapeHtml(inst)}</li>`).join('')}</ul>`
    : '';

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Post Operative Medication</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: Arial, sans-serif;
      font-size: 10pt;
      line-height: 1.4;
      padding: 0.5in;
      max-width: 11in;
      margin: 0 auto;
      background: white;
      color: #000;
    }
    .header {
      text-align: center;
      margin-bottom: 20px;
      border-bottom: 3px solid #000;
      padding-bottom: 10px;
    }
    .header h1 {
      font-size: 18pt;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .patient-section {
      margin-bottom: 20px;
      border: 1px solid #ccc;
      padding: 15px;
      background: #f9f9f9;
    }
    .patient-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    .field {
      display: flex;
      align-items: baseline;
    }
    .field-label {
      font-weight: bold;
      min-width: 80px;
    }
    .field-value {
      flex: 1;
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
      padding: 5px 10px;
    }
    .special-instructions {
      text-align: center;
      color: #666;
    }
    .timing-header-group {
      text-align: center;
    }
    .timing-numbers {
      display: flex;
      justify-content: center;
    }
    .timing-numbers span {
      flex: 1;
      padding: 5px;
      border-left: 1px solid #666;
    }
    .timing-numbers span:first-child {
      border-left: none;
    }
    .general-instructions {
      margin-top: 20px;
      padding: 15px;
      background: #f5f5f5;
      border-left: 4px solid #333;
    }
    .general-instructions h3 {
      font-size: 11pt;
      margin-bottom: 10px;
    }
    .general-instructions ul {
      margin-left: 20px;
    }
    .general-instructions li {
      margin-bottom: 5px;
    }
    .followup-section {
      margin-top: 20px;
      padding: 15px;
      border: 2px solid #333;
      background: #fff;
    }
    .followup-section h3 {
      font-size: 11pt;
      margin-bottom: 10px;
    }
    @media print {
      body {
        padding: 0.25in;
        font-size: 9pt;
      }
      .medication-table th { font-size: 8pt; padding: 6px 3px; }
      .medication-table td { font-size: 8pt; padding: 5px 3px; }
    }
  </style>
</head>
<body>

  <!-- HEADER -->
  <div class="header">
    <h1>Post Operative Medication</h1>
  </div>

  <!-- PATIENT DETAILS -->
  <div class="patient-section">
    <div class="patient-grid">
      <div class="field">
        <span class="field-label">Name</span>
        <span class="field-value">: ${escapeHtml(patientDetails.name || '')}</span>
      </div>
      <div class="field">
        <span class="field-label">Visit ID</span>
        <span class="field-value">: ${escapeHtml(patientDetails.visitId || patientDetails.visit_id || '')}</span>
      </div>
      <div class="field">
        <span class="field-label">Date</span>
        <span class="field-value">: ${escapeHtml(patientDetails.date || new Date().toLocaleDateString())}</span>
      </div>
      <div class="field">
        <span class="field-label">MRNO</span>
        <span class="field-value">: ${escapeHtml(patientDetails.mrNumber || patientDetails.mr_number || '')}</span>
      </div>
      <div class="field">
        <span class="field-label">Age / Gender</span>
        <span class="field-value">: ${escapeHtml(patientDetails.age || '')}${patientDetails.gender ? ' / ' + escapeHtml(patientDetails.gender) : ''}</span>
      </div>
    </div>
    ${surgeryDetails.procedure || surgeryDetails.eyeOperated ? `
      <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #ddd;">
        <strong>Surgery:</strong> ${escapeHtml(surgeryDetails.procedure || '')}
        ${surgeryDetails.eyeOperated ? ` (${escapeHtml(surgeryDetails.eyeOperated)})` : ''}
        ${surgeryDetails.surgeryDate ? ` on ${escapeHtml(surgeryDetails.surgeryDate)}` : ''}
      </div>
    ` : ''}
  </div>

  <!-- MEDICATION TABLE -->
  <table class="medication-table">
    <thead>
      <tr>
        <th rowspan="2" class="serial-col">S<br>NO</th>
        <th rowspan="2" class="med-col">EYE DROP</th>
        <th rowspan="2" class="days-col">DAYS /<br>DATE</th>
        <th colspan="6" class="timing-header-group">TIMING</th>
      </tr>
      <tr>
        <th class="timing-col">1</th>
        <th class="timing-col">2</th>
        <th class="timing-col">3</th>
        <th class="timing-col">4</th>
        <th class="timing-col">5</th>
        <th class="timing-col">6</th>
      </tr>
    </thead>
    <tbody>
      ${medicationRowsHtml || `
        <tr>
          <td colspan="9" style="text-align: center; color: #999; padding: 20px;">
            No medications prescribed
          </td>
        </tr>
      `}
    </tbody>
  </table>

  <!-- GENERAL INSTRUCTIONS -->
  ${instructionsHtml ? `
    <div class="general-instructions">
      <h3>General Instructions:</h3>
      ${instructionsHtml}
    </div>
  ` : ''}

  <!-- FOLLOW-UP -->
  ${followUp.date || followUp.instructions ? `
    <div class="followup-section">
      <h3>Follow-up:</h3>
      ${followUp.date ? `<p><strong>Date:</strong> ${escapeHtml(followUp.date)}</p>` : ''}
      ${followUp.instructions ? `<p>${escapeHtml(followUp.instructions)}</p>` : ''}
    </div>
  ` : ''}

</body>
</html>
  `.trim();
}

// Helper Functions

/**
 * Escape HTML special characters
 */
function escapeHtml(text: string): string {
  if (typeof text !== 'string') return String(text);

  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };

  return text.replace(/[&<>"']/g, (m) => map[m]);
}

/**
 * Format section title from camelCase or snake_case
 */
function formatSectionTitle(key: string): string {
  const normalized = key.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

/**
 * Format refraction data (Sphere / Cylinder × Axis)
 */
function formatRefraction(refraction: any): string {
  if (!refraction) return 'N/A';

  if (typeof refraction === 'string') return refraction;

  const sphere = refraction.sphere || refraction.sph || '';
  const cylinder = refraction.cylinder || refraction.cyl || '';
  const axis = refraction.axis || '';

  if (!sphere && !cylinder && !axis) return 'N/A';

  const parts: string[] = [];
  if (sphere) parts.push(sphere);
  if (cylinder) parts.push(` / ${cylinder}`);
  if (axis) parts.push(` × ${axis}`);

  return parts.join('') || 'N/A';
}

/**
 * Format IOP data (value + time)
 */
function formatIOP(iop: any): string {
  if (!iop) return 'N/A';

  if (typeof iop === 'string' || typeof iop === 'number') {
    return `${iop} mmHg`;
  }

  const value = iop.value || iop.measurement || iop.mmhg || '';
  const time = iop.time || '';

  if (!value) return 'N/A';

  return time ? `${value} mmHg (${time})` : `${value} mmHg`;
}

/**
 * Format slit lamp findings (structured breakdown by component)
 */
function formatSlitLampFindings(findings: any): string {
  if (!findings) return '<p style="color: #999;">Not examined</p>';

  if (typeof findings === 'string') {
    return `<p>${escapeHtml(findings)}</p>`;
  }

  const components = [
    { keys: ['lids', 'lidsAndLashes', 'lids_and_lashes'], label: 'Lids & Lashes' },
    { keys: ['conjunctiva'], label: 'Conjunctiva' },
    { keys: ['cornea'], label: 'Cornea' },
    { keys: ['anterior_chamber', 'anteriorChamber'], label: 'Anterior Chamber' },
    { keys: ['iris'], label: 'Iris' },
    { keys: ['lens'], label: 'Lens' },
    { keys: ['pupil'], label: 'Pupil' }
  ];

  const html = components
    .filter(comp => comp.keys.some(key => findings[key]))
    .map(comp => {
      const value = comp.keys.find(key => findings[key]);
      return value ? `<p><strong>${comp.label}:</strong> ${escapeHtml(findings[value])}</p>` : '';
    })
    .join('');

  return html || '<p style="color: #999;">Not documented</p>';
}

/**
 * Format fundus findings (structured breakdown by component)
 */
function formatFundusFindings(findings: any): string {
  if (!findings) return '<p style="color: #999;">Not examined</p>';

  if (typeof findings === 'string') {
    return `<p>${escapeHtml(findings)}</p>`;
  }

  const components = [
    { keys: ['disc', 'opticDisc', 'optic_disc'], label: 'Optic Disc', subKeys: ['cdRatio', 'cd_ratio', 'cdr'] },
    { keys: ['cdr', 'cdRatio', 'cd_ratio'], label: 'C/D Ratio' },
    { keys: ['macula'], label: 'Macula', subKeys: ['findings', 'fovealReflex', 'foveal_reflex'] },
    { keys: ['vessels'], label: 'Vessels', subKeys: ['findings'] },
    { keys: ['general_fundus', 'generalFundus'], label: 'General Fundus' },
    { keys: ['periphery'], label: 'Periphery' },
    { keys: ['vitreous'], label: 'Vitreous' }
  ];

  const htmlParts: string[] = [];

  for (const comp of components) {
    const foundKey = comp.keys.find(key => findings[key]);
    if (foundKey) {
      const value = findings[foundKey];

      // Handle nested objects with subKeys
      if (typeof value === 'object' && value !== null && comp.subKeys) {
        const subParts: string[] = [];
        for (const subKey of comp.subKeys) {
          if (value[subKey]) {
            subParts.push(escapeHtml(String(value[subKey])));
          }
        }
        if (subParts.length > 0) {
          htmlParts.push(`<p><strong>${comp.label}:</strong> ${subParts.join(', ')}</p>`);
        }
      } else if (typeof value === 'string' || typeof value === 'number') {
        htmlParts.push(`<p><strong>${comp.label}:</strong> ${escapeHtml(String(value))}</p>`);
      }
    }
  }

  return htmlParts.length > 0 ? htmlParts.join('') : '<p style="color: #999;">Not documented</p>';
}

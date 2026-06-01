"""
Structured Insights Mapper

Dynamically extracts clinical information from extraction JSON for triage analysis.
Handles different template structures where segments may be in different locations:
- OP: chiefComplaints at top level
- OP_SHORT: history.chief_complaints nested inside history object

Uses existing history_extraction_utils for consistent parsing.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime

# Import existing utilities
from services.history_extraction_utils import (
    get_extraction_data,
    extract_chief_complaints,
    extract_vitals,
    extract_diagnosis_list,
    extract_complaints_list,
    find_segment_value,
    find_prescription_in_extraction,
    normalize_prescription_data,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Specialty Mapping
# =============================================================================

CONSULTATION_TYPE_TO_SPECIALTY = {
    # General / Internal Medicine
    "OP": "general_medicine",
    "OP_SHORT": "general_medicine",
    "OP_CONCISE": "general_medicine",
    "OP_ULTRA_CONCISE": "general_medicine",
    "DISCHARGE": "general_medicine",

    # Cardiology
    "GKNM_CARDIAC": "cardiology",

    # Obstetrics & Gynecology
    "GKNM_OBG": "obstetrics",

    # Ophthalmology
    "OPHTHALMOLOGY": "ophthalmology",
    "OPHTHAL_DISCHARGE": "ophthalmology",
    "OPHTHAL_FULL": "ophthalmology",
    "OPHTHAL_PRESCRIPTION": "ophthalmology",
    "OPHTHAL_POSTOP_RX": "ophthalmology",
    "OPTOMETRY": "ophthalmology",

    # Psychiatry (to be added)
    "PSYCHIATRY": "psychiatry",

    # Pediatrics (to be added)
    "PEDIATRIC": "pediatrics",

    # Orthopedics
    "ORTHO": "orthopedics",
    "ORTHOPEDICS": "orthopedics",
    "ORTHOPAEDICS": "orthopedics",

    # Gastroenterology
    "GASTRO": "gastroenterology",

    # Fertility
    "FERTILITY": "fertility",
}


# =============================================================================
# Structured Insights Dataclass
# =============================================================================

@dataclass
class StructuredInsights:
    """
    Triage-ready structured representation of a clinical consultation.

    Attributes:
        specialty: Clinical specialty (general_medicine, psychiatry, etc.)
        consultation_type_code: Original consultation type code
        patient_age: Student age as string
        patient_gender: Student gender
        age_group: Derived age group (neonate, infant, child, adolescent, adult, elderly)

        chief_complaints: List of chief complaint strings
        history_of_present_illness: HPI details as dict
        past_medical_history: List of past conditions
        past_surgical_history: List of past surgeries
        family_history: Family history string
        social_history: Social history dict
        drug_allergies: List of known allergies
        current_medications: List of current medication dicts

        vital_signs: Vital signs dict
        examination_findings: Physical exam findings dict

        investigations_ordered: List of ordered tests
        investigations_results: List of result dicts

        diagnoses_discussed: List of diagnosis dicts
        prescription: List of prescription medication dicts
        treatment_plan: Treatment plan dict
        follow_up: Follow-up instructions dict

        # Psychosocial factors
        patient_anxiety_level: Anxiety level if detected
        financial_concerns: Financial concerns if detected
        compliance_likelihood: Treatment compliance likelihood

        # Metadata
        extraction_id: UUID of the extraction
        created_at: When extraction was created
        raw_extraction: Original extraction JSON for reference
    """

    # Core identifiers
    specialty: str = "general_medicine"
    consultation_type_code: str = ""
    extraction_id: str = ""

    # Student demographics
    patient_age: str = ""
    patient_gender: str = ""
    age_group: str = "adult"

    # Chief complaints & History
    chief_complaints: List[str] = field(default_factory=list)
    history_of_present_illness: Dict[str, Any] = field(default_factory=dict)
    past_medical_history: List[str] = field(default_factory=list)
    past_surgical_history: List[str] = field(default_factory=list)
    family_history: str = ""
    social_history: Dict[str, Any] = field(default_factory=dict)
    birth_history: str = ""
    drug_allergies: List[str] = field(default_factory=list)
    current_medications: List[Dict[str, Any]] = field(default_factory=list)

    # Vitals & Examination
    vital_signs: Dict[str, Any] = field(default_factory=dict)
    examination_findings: Dict[str, Any] = field(default_factory=dict)

    # Investigations
    investigations_ordered: List[str] = field(default_factory=list)
    investigations_results: List[Dict[str, Any]] = field(default_factory=list)

    # Diagnosis & Treatment
    diagnoses_discussed: List[Dict[str, Any]] = field(default_factory=list)
    prescription: List[Dict[str, Any]] = field(default_factory=list)
    treatment_plan: Dict[str, Any] = field(default_factory=dict)
    follow_up: Dict[str, Any] = field(default_factory=dict)

    # Psychosocial factors
    patient_anxiety_level: str = ""
    financial_concerns: str = ""
    compliance_likelihood: str = ""
    other_emotions: List[str] = field(default_factory=list)

    # Red flags detected
    warnings: Dict[str, Any] = field(default_factory=dict)
    caution: str = ""

    # Summary
    summary: str = ""

    # Metadata
    created_at: Optional[str] = None
    raw_extraction: Dict[str, Any] = field(default_factory=dict)

    # Student historical context (populated by with_student_history)
    known_allergies: List[str] = field(default_factory=list)
    chronic_conditions: List[str] = field(default_factory=list)
    prior_intervention_outcomes: List[Dict[str, Any]] = field(default_factory=list)
    historical_anxiety_pattern: Optional[Dict[str, Any]] = None
    financial_concerns_history: str = ""
    compliance_history: str = ""
    historical_emotions: List[str] = field(default_factory=list)
    total_consultations: int = 0
    student_id: Optional[str] = None

    def derive_age_group(self) -> str:
        """Derive age group from patient_age string."""
        if not self.patient_age:
            return "adult"

        try:
            age_str = self.patient_age.lower().strip()

            # Handle "N/A" or empty
            if age_str in ("n/a", "na", "", "unknown"):
                return "adult"

            # Handle days
            if "day" in age_str:
                return "neonate"

            # Handle months
            if "month" in age_str:
                # Extract number
                import re
                nums = re.findall(r'\d+', age_str)
                if nums:
                    months = int(nums[0])
                    return "infant" if months <= 12 else "toddler"
                return "infant"

            # Handle weeks (for neonates)
            if "week" in age_str:
                return "neonate"

            # Handle years
            import re
            nums = re.findall(r'\d+', age_str)
            if nums:
                years = int(nums[0])
                if years < 1:
                    return "infant"
                elif years < 3:
                    return "toddler"
                elif years < 12:
                    return "child"
                elif years < 18:
                    return "adolescent"
                elif years < 60:
                    return "adult"
                else:
                    return "elderly"

            return "adult"

        except Exception as e:
            logger.warning(f"[STRUCTURED_INSIGHTS] Error deriving age group from '{self.patient_age}': {e}")
            return "adult"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "specialty": self.specialty,
            "consultation_type_code": self.consultation_type_code,
            "extraction_id": self.extraction_id,
            "patient_age": self.patient_age,
            "patient_gender": self.patient_gender,
            "age_group": self.age_group,
            "chief_complaints": self.chief_complaints,
            "history_of_present_illness": self.history_of_present_illness,
            "past_medical_history": self.past_medical_history,
            "past_surgical_history": self.past_surgical_history,
            "family_history": self.family_history,
            "social_history": self.social_history,
            "birth_history": self.birth_history,
            "drug_allergies": self.drug_allergies,
            "current_medications": self.current_medications,
            "vital_signs": self.vital_signs,
            "examination_findings": self.examination_findings,
            "investigations_ordered": self.investigations_ordered,
            "investigations_results": self.investigations_results,
            "diagnoses_discussed": self.diagnoses_discussed,
            "prescription": self.prescription,
            "treatment_plan": self.treatment_plan,
            "follow_up": self.follow_up,
            "patient_anxiety_level": self.patient_anxiety_level,
            "financial_concerns": self.financial_concerns,
            "compliance_likelihood": self.compliance_likelihood,
            "other_emotions": self.other_emotions,
            "warnings": self.warnings,
            "caution": self.caution,
            "summary": self.summary,
            "created_at": self.created_at,
            # Student historical context
            "known_allergies": self.known_allergies,
            "chronic_conditions": self.chronic_conditions,
            "prior_intervention_outcomes": self.prior_intervention_outcomes,
            "historical_anxiety_pattern": self.historical_anxiety_pattern,
            "financial_concerns_history": self.financial_concerns_history,
            "compliance_history": self.compliance_history,
            "historical_emotions": self.historical_emotions,
            "total_consultations": self.total_consultations,
            "student_id": self.student_id,
        }


# =============================================================================
# Structured Insights Mapper
# =============================================================================

class StructuredInsightsMapper:
    """
    Maps extraction JSON to StructuredInsights for triage analysis.

    Handles multiple template structures dynamically by checking
    various possible locations for each clinical data element.
    """

    def __init__(self, supabase_client=None):
        """
        Initialize mapper.

        Args:
            supabase_client: Optional Supabase client for fetching segment configs
        """
        self.supabase = supabase_client

    def map_extraction(
        self,
        extraction: Dict[str, Any],
        consultation_type_code: Optional[str] = None
    ) -> StructuredInsights:
        """
        Map extraction record to StructuredInsights.

        Args:
            extraction: Full extraction record from database (includes id, consultation_type_id, etc.)
            consultation_type_code: Optional type code (fetched from DB if not provided)

        Returns:
            StructuredInsights object ready for triage analysis
        """
        # Get extraction data (edited or original)
        ext_data = get_extraction_data(extraction)

        if not ext_data:
            logger.warning(f"[MAPPER] No extraction data found")
            return StructuredInsights()

        # Determine consultation type code
        type_code = consultation_type_code or self._get_consultation_type_code(extraction)

        # Map to specialty
        specialty = CONSULTATION_TYPE_TO_SPECIALTY.get(type_code, "general_medicine")

        # Create insights object
        insights = StructuredInsights(
            specialty=specialty,
            consultation_type_code=type_code,
            extraction_id=str(extraction.get("id", "")),
            created_at=extraction.get("created_at"),
            raw_extraction=ext_data,
        )

        # Extract all fields dynamically
        self._extract_student_info(insights, ext_data)
        self._extract_chief_complaints(insights, ext_data)
        self._extract_history(insights, ext_data)
        self._extract_examination(insights, ext_data)
        self._extract_investigations(insights, ext_data)
        self._extract_diagnosis(insights, ext_data)
        self._extract_treatment(insights, ext_data)
        self._extract_psychosocial(insights, ext_data)
        self._extract_warnings(insights, ext_data)
        self._extract_summary(insights, ext_data)

        # Derive age group
        insights.age_group = insights.derive_age_group()

        return insights

    def map_extraction_json(
        self,
        extraction_json: Dict[str, Any],
        consultation_type_code: str
    ) -> StructuredInsights:
        """
        Map raw extraction JSON to StructuredInsights.

        Args:
            extraction_json: Raw extraction JSON (original_extraction_json content)
            consultation_type_code: Consultation type code

        Returns:
            StructuredInsights object
        """
        # Wrap in extraction record format
        extraction = {
            "original_extraction_json": extraction_json,
        }
        return self.map_extraction(extraction, consultation_type_code)

    def _get_consultation_type_code(self, extraction: Dict[str, Any]) -> str:
        """Get consultation type code from extraction or DB."""
        # Check if consultation_types is joined
        ct = extraction.get("consultation_types")
        if ct:
            if isinstance(ct, dict):
                return ct.get("type_code", "OP")
            elif isinstance(ct, list) and ct:
                return ct[0].get("type_code", "OP")

        # Default
        return "OP"

    def _extract_student_info(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract student demographic information."""

        # Try patientInformation segment
        patient_info = find_segment_value(
            data,
            'patientInformation', 'patient_information', 'patientInfo'
        )

        if patient_info and isinstance(patient_info, dict):
            insights.patient_age = str(patient_info.get('age', '') or '')
            insights.patient_gender = str(patient_info.get('gender', '') or patient_info.get('sex', '') or '')

        # Also check examination for age/gender (some templates put it there)
        examination = find_segment_value(data, 'examination', 'physicalExamination')
        if examination and isinstance(examination, dict):
            if not insights.patient_age:
                insights.patient_age = str(examination.get('age', '') or '')
            if not insights.patient_gender:
                insights.patient_gender = str(examination.get('gender', '') or examination.get('sex', '') or '')

    def _extract_chief_complaints(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract chief complaints from various possible locations."""

        # Use existing utility which handles multiple locations
        complaints_raw = extract_chief_complaints(data)

        if complaints_raw:
            # Normalize to list of strings
            insights.chief_complaints = extract_complaints_list(complaints_raw)

        # If still empty, check history segment for chief_complaints
        if not insights.chief_complaints:
            history = find_segment_value(data, 'history', 'historyOp', 'historyDischarge')
            if history and isinstance(history, dict):
                cc = history.get('chief_complaints') or history.get('chiefComplaints')
                if cc:
                    insights.chief_complaints = extract_complaints_list(cc)

    def _extract_history(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract history sections."""

        # History of Present Illness
        hpi = find_segment_value(
            data,
            'historyOfPresentIllness', 'history_of_present_illness', 'hpi'
        )
        if hpi:
            if isinstance(hpi, dict):
                insights.history_of_present_illness = hpi
            elif isinstance(hpi, str):
                insights.history_of_present_illness = {"description": hpi}

        # Also check if HPI is nested in history segment
        history = find_segment_value(data, 'history', 'historyOp', 'historyDischarge')
        if history and isinstance(history, dict):
            # Extract individual components
            if not insights.history_of_present_illness:
                nested_hpi = history.get('history_of_present_illness') or history.get('historyOfPresentIllness')
                if nested_hpi:
                    if isinstance(nested_hpi, dict):
                        insights.history_of_present_illness = nested_hpi
                    elif isinstance(nested_hpi, str):
                        insights.history_of_present_illness = {"description": nested_hpi}

            # Past Medical History
            pmh = history.get('past_medical_history') or history.get('pastMedicalHistory')
            if pmh:
                if isinstance(pmh, list):
                    insights.past_medical_history = [str(x) for x in pmh if x and str(x).lower() != 'n/a']
                elif isinstance(pmh, str) and pmh.lower() != 'n/a':
                    insights.past_medical_history = [pmh]

            # Past Surgical History
            psh = history.get('past_surgical_history') or history.get('pastSurgicalHistory')
            if psh:
                if isinstance(psh, list):
                    insights.past_surgical_history = [str(x) for x in psh if x and str(x).lower() != 'n/a']
                elif isinstance(psh, str) and psh.lower() != 'n/a':
                    insights.past_surgical_history = [psh]

            # Family History
            fh = history.get('family_history') or history.get('familyHistory')
            if fh and str(fh).lower() != 'n/a':
                insights.family_history = str(fh)

            # Social History
            sh = history.get('social_history') or history.get('socialHistory')
            if sh:
                if isinstance(sh, dict):
                    insights.social_history = sh
                elif isinstance(sh, str) and sh.lower() != 'n/a':
                    insights.social_history = {"description": sh}

            # Birth History (for pediatrics/neonates)
            bh = history.get('birth_history') or history.get('birthHistory')
            if bh and str(bh).lower() != 'n/a':
                insights.birth_history = str(bh)

            # Drug Allergies
            allergies = history.get('drug_allergies') or history.get('drugAllergies') or history.get('allergies')
            if allergies:
                if isinstance(allergies, list):
                    insights.drug_allergies = [str(x) for x in allergies if x and str(x).lower() != 'n/a']
                elif isinstance(allergies, str) and allergies.lower() != 'n/a':
                    insights.drug_allergies = [allergies]

            # Current Medications
            current_meds = history.get('current_medications') or history.get('currentMedications')
            if current_meds:
                insights.current_medications = normalize_prescription_data(current_meds)

    def _extract_examination(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract examination findings."""

        # Vitals
        vitals = extract_vitals(data)
        if vitals:
            insights.vital_signs = vitals

        # Full examination
        examination = find_segment_value(
            data,
            'examination', 'physicalExamination', 'physicalExaminationOp'
        )
        if examination and isinstance(examination, dict):
            # Store full examination
            insights.examination_findings = examination


    def _extract_investigations(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract investigations ordered and results."""

        investigations = find_segment_value(
            data,
            'investigations', 'investigationsOp', 'investigationsDischarge',
            'orderedLabs', 'orderedRadiology'
        )

        if investigations:
            if isinstance(investigations, str):
                # Text description of investigations
                if investigations.lower() != 'n/a':
                    insights.investigations_ordered = [investigations]
            elif isinstance(investigations, dict):
                # Legacy nested format: {laboratory_tests: [...], imaging_studies: [...], other_tests: [...]}
                all_tests = []
                for sub_key in ['laboratory_tests', 'labTests', 'imaging_studies', 'imaging', 'other_tests']:
                    sub_val = investigations.get(sub_key) or []
                    if isinstance(sub_val, str):
                        try:
                            import json
                            sub_val = json.loads(sub_val)
                        except:
                            sub_val = []
                    if isinstance(sub_val, list):
                        all_tests.extend(sub_val)

                ordered = []
                results = []
                for test in all_tests:
                    if isinstance(test, dict):
                        name = test.get('name') or test.get('test_name') or test.get('study_name', '')
                        if name:
                            ordered.append(name)
                            if test.get('result') and test.get('result') != 'N/A':
                                results.append(test)
                    elif isinstance(test, str):
                        ordered.append(test)

                insights.investigations_ordered = ordered
                insights.investigations_results = results
            elif isinstance(investigations, list):
                # New flat format: [{name, type, date}, ...]
                insights.investigations_ordered = [
                    (x.get('name') or x.get('test_name') or str(x)) if isinstance(x, dict) else str(x)
                    for x in investigations
                ]

    def _extract_diagnosis(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract diagnoses."""

        diagnosis = find_segment_value(
            data,
            'diagnosis', 'diagnosisOp', 'diagnosisDischarge'
        )

        if diagnosis:
            insights.diagnoses_discussed = extract_diagnosis_list(diagnosis)

    def _extract_treatment(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract treatment plan and prescription."""

        # Prescription
        prescription_data = find_prescription_in_extraction(data)
        if prescription_data:
            insights.prescription = normalize_prescription_data(prescription_data)

        # Treatment Plan
        treatment_plan = find_segment_value(
            data,
            'treatmentPlan', 'treatment_plan', 'treatmentPlanAdvice',
            'treatmentPlanAdviceOp', 'treatmentPlanAdviceDischarge'
        )
        if treatment_plan:
            if isinstance(treatment_plan, list):
                insights.treatment_plan = {"instructions": treatment_plan}
            elif isinstance(treatment_plan, dict):
                insights.treatment_plan = treatment_plan
            elif isinstance(treatment_plan, str):
                insights.treatment_plan = {"description": treatment_plan}

        # Follow-up
        follow_up = find_segment_value(
            data,
            'followUp', 'follow_up', 'followUpOp'
        )
        if follow_up:
            if isinstance(follow_up, dict):
                insights.follow_up = follow_up
            elif isinstance(follow_up, str):
                insights.follow_up = {"instructions": follow_up}

    def _extract_psychosocial(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract psychosocial factors."""

        # Pre-consultation anxiety
        anxiety_pre = find_segment_value(
            data,
            'anxietyPreConsultation', 'anxiety_pre_consultation',
            'preConsultationAnxietyLevel'
        )
        if anxiety_pre and str(anxiety_pre).lower() != 'n/a':
            if isinstance(anxiety_pre, dict):
                insights.patient_anxiety_level = anxiety_pre.get('level', str(anxiety_pre))
            else:
                insights.patient_anxiety_level = str(anxiety_pre)

        # Post-consultation anxiety (for comparison)
        anxiety_post = find_segment_value(
            data,
            'anxietyPostConsultation', 'anxiety_post_consultation',
            'postConsultationAnxietyLevel'
        )

        # Financial concerns
        financial = find_segment_value(
            data,
            'financialConcerns', 'financial_concerns', 'financialConcernsDetected'
        )
        if financial and str(financial).lower() != 'n/a':
            if isinstance(financial, dict):
                insights.financial_concerns = financial.get('concerns', str(financial))
            else:
                insights.financial_concerns = str(financial)

        # Compliance likelihood
        compliance = find_segment_value(
            data,
            'treatmentComplianceLikelihood', 'treatment_compliance_likelihood',
            'complianceLikelihood'
        )
        if compliance and str(compliance).lower() != 'n/a':
            if isinstance(compliance, dict):
                insights.compliance_likelihood = compliance.get('likelihood', str(compliance))
            else:
                insights.compliance_likelihood = str(compliance)

        # Other emotions
        other_emotions = find_segment_value(
            data,
            'otherEmotionsDetected', 'other_emotions_detected', 'otherEmotions'
        )
        if other_emotions:
            if isinstance(other_emotions, list):
                insights.other_emotions = [str(e) for e in other_emotions if str(e).lower() != 'n/a']
            elif isinstance(other_emotions, str) and other_emotions.lower() != 'n/a':
                insights.other_emotions = [other_emotions]

    def _extract_warnings(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract warnings and cautions."""

        # Warnings (allergy checks, safety summary, etc.)
        warnings = find_segment_value(data, 'warnings', 'warningsOp')
        if warnings and isinstance(warnings, dict):
            insights.warnings = warnings

        # Caution
        caution = find_segment_value(data, 'caution', 'cautionOp')
        if caution and str(caution).lower() != 'n/a':
            insights.caution = str(caution)

    def _extract_summary(self, insights: StructuredInsights, data: Dict[str, Any]):
        """Extract consultation summary."""

        summary = find_segment_value(data, 'summary', 'summaryOp', 'consultationSummary')
        if summary and str(summary).lower() != 'n/a':
            insights.summary = str(summary)


# =============================================================================
# Convenience Functions
# =============================================================================

def map_extraction_to_insights(
    extraction: Dict[str, Any],
    consultation_type_code: Optional[str] = None
) -> StructuredInsights:
    """
    Convenience function to map extraction to StructuredInsights.

    Args:
        extraction: Extraction record from database
        consultation_type_code: Optional consultation type code

    Returns:
        StructuredInsights object
    """
    mapper = StructuredInsightsMapper()
    return mapper.map_extraction(extraction, consultation_type_code)


async def map_extraction_with_student_history(
    extraction: Dict[str, Any],
    student_id: str,
    supabase_client,
    consultation_type_code: Optional[str] = None
) -> StructuredInsights:
    """
    Map extraction to StructuredInsights enriched with student's historical context.

    This function queries historical student data from:
    - ALLERGIES, CAUTION segments → known_allergies
    - HISTORY segments → chronic_conditions
    - student_interventions table → prior_intervention_outcomes
    - ANXIETY_POST_CONSULTATION (combined mode with nested pre/post) → historical_anxiety_pattern
    - FINANCIAL_CONCERNS (combined mode) → financial_concerns_history
    - TREATMENT_COMPLIANCE_LIKELIHOOD (combined mode) → compliance_history
    - OTHER_EMOTIONS_DETECTED (combined mode) → historical_emotions

    Args:
        extraction: Extraction record from database
        student_id: UUID of the student
        supabase_client: Supabase client instance
        consultation_type_code: Optional consultation type code

    Returns:
        StructuredInsights object enriched with historical student context
    """
    # First, get base insights from extraction
    mapper = StructuredInsightsMapper()
    insights = mapper.map_extraction(extraction, consultation_type_code)
    insights.student_id = student_id

    if not student_id:
        logger.warning("[STRUCTURED_INSIGHTS] No student_id provided, skipping history enrichment")
        return insights

    try:
        # Call RPC function to aggregate student context from historical extractions
        result = supabase_client.rpc(
            'get_student_triage_context',
            {'p_student_id': student_id}
        ).execute()

        history = result.data if result.data else {}

        if not history:
            logger.info(f"[STRUCTURED_INSIGHTS] No historical context found for student {student_id}")
            return insights

        logger.info(f"[STRUCTURED_INSIGHTS] Enriching with student history: {list(history.keys())}")

        # Enrich with historical data from segments
        # - ALLERGIES, CAUTION → known_allergies
        allergies = history.get('allergies', [])
        if isinstance(allergies, list):
            insights.known_allergies = [str(a) for a in allergies if a]
        elif allergies:
            insights.known_allergies = [str(allergies)]

        # - HISTORY → chronic_conditions
        chronic = history.get('chronic_conditions', [])
        if isinstance(chronic, list):
            insights.chronic_conditions = [str(c) for c in chronic if c]
        elif chronic:
            insights.chronic_conditions = [str(chronic)]

        # - student_interventions → prior_intervention_outcomes
        interventions = history.get('intervention_outcomes', [])
        if isinstance(interventions, list):
            insights.prior_intervention_outcomes = interventions

        # - ANXIETY_POST_CONSULTATION (combined mode) → historical_anxiety_pattern
        anxiety = history.get('anxiety_pattern')
        if isinstance(anxiety, dict):
            insights.historical_anxiety_pattern = anxiety

        # - FINANCIAL_CONCERNS (combined mode) → financial_concerns_history
        financial = history.get('financial_concerns_trend')
        if financial:
            insights.financial_concerns_history = str(financial)

        # - TREATMENT_COMPLIANCE_LIKELIHOOD (combined mode) → compliance_history
        compliance = history.get('compliance_likelihood')
        if compliance:
            insights.compliance_history = str(compliance)

        # - OTHER_EMOTIONS_DETECTED (combined mode) → historical_emotions
        emotions = history.get('other_emotions', [])
        if isinstance(emotions, list):
            insights.historical_emotions = [str(e) for e in emotions if e]

        # Total consultations count
        total = history.get('total_consultations', 0)
        insights.total_consultations = int(total) if total else 0

        logger.info(f"[STRUCTURED_INSIGHTS] Student history enriched: {insights.total_consultations} consultations, "
                   f"{len(insights.known_allergies)} allergies, {len(insights.chronic_conditions)} chronic conditions")

    except Exception as e:
        logger.error(f"[STRUCTURED_INSIGHTS] Error fetching student history for {student_id}: {e}")
        # Continue without history - don't fail the whole process

    return insights

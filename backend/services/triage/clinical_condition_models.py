"""
Clinical Condition Pydantic Models

Validators for the 3 STG document types:
1. Narrative Guidelines (e.g., Hypertension)
2. Visual Workflows (e.g., Rhinosinusitis)
3. Step Protocols (e.g., Epistaxis)

These models validate incoming JSON before ingestion into the clinical_conditions table.
"""

import re
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class DocumentType(str, Enum):
    NARRATIVE_GUIDELINE = "narrative_guideline"
    VISUAL_WORKFLOW = "visual_workflow"
    STEP_PROTOCOL = "step_protocol"


class UrgencyLevel(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class CareLevel(str, Enum):
    PHC = "phc"
    DISTRICT = "district"
    TERTIARY = "tertiary"


class SymptomFrequency(str, Enum):
    MOST_COMMON = "most_common"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    ASSOCIATED = "associated"


class EvidenceLevel(str, Enum):
    LEVEL_A = "Level A"
    LEVEL_B = "Level B"
    LEVEL_C = "Level C"
    EXPERT_CONSENSUS = "Expert Consensus"


# =============================================================================
# Shared Models
# =============================================================================

class DocumentMeta(BaseModel):
    """Metadata about the source document."""
    source: str = Field(..., description="Source organization (e.g., Ministry of Health STG)")
    specialty: str = Field(..., description="Medical specialty (e.g., cardiology, ent)")
    document_type: Optional[DocumentType] = None
    version: Optional[str] = None
    language: str = Field(default="en")
    icd_codes: List[str] = Field(default_factory=list)

    @field_validator('specialty')
    @classmethod
    def normalize_specialty(cls, v: str) -> str:
        return v.lower().replace(' ', '_').replace('-', '_')


class SymptomEntry(BaseModel):
    """A symptom with frequency and optional notes."""
    symptom: str
    frequency: Optional[SymptomFrequency] = None
    note: Optional[str] = None


class ExaminationFinding(BaseModel):
    """Examination finding - can be string or structured."""
    finding: str
    significance: Optional[str] = None


class RedFlag(BaseModel):
    """A clinical red flag with action."""
    flag: str
    definition: Optional[str] = None
    clues: List[str] = Field(default_factory=list)
    signs: List[str] = Field(default_factory=list)
    action: Optional[str] = None
    consider: Optional[str] = None


class EmergencyTrigger(BaseModel):
    """An emergency trigger condition."""
    trigger: str
    symptoms: List[str] = Field(default_factory=list)
    mnemonic: Optional[str] = None


class ReferralTrigger(BaseModel):
    """Referral criteria."""
    condition: str
    refer_to: str


class InvestigationTest(BaseModel):
    """A diagnostic test."""
    test: str
    abnormal: Optional[str] = None
    significance: Optional[str] = None
    indication: Optional[str] = None
    purpose: Optional[str] = None


class DrugEntry(BaseModel):
    """Drug information for formulary."""
    drug: Optional[str] = None
    drug_class: Optional[str] = None
    representative: Optional[str] = None
    initial_dose: Optional[str] = None
    max_dose: Optional[str] = None
    low_dose: Optional[str] = None
    low_dose_situations: List[str] = Field(default_factory=list)
    side_effects: List[str] = Field(default_factory=list)
    contraindications: List[str] = Field(default_factory=list)
    pregnancy_category: Optional[str] = None
    monitoring: Optional[str] = None
    special_notes: Optional[str] = None
    duration: Optional[str] = None
    indication: Optional[str] = None
    benefit: Optional[str] = None
    first_line: Optional[bool] = None
    dose: Optional[str] = None
    onset: Optional[str] = None


class ManagementStep(BaseModel):
    """A step in step-wise management."""
    step: int
    description: Optional[str] = None
    action: Optional[str] = None
    options: List[str] = Field(default_factory=list)
    methods: List[str] = Field(default_factory=list)
    duration_before_escalation: Optional[str] = None
    applies_to: List[str] = Field(default_factory=list)
    avoid_combinations: List[str] = Field(default_factory=list)
    recommended: Optional[str] = None


class ComorbidityPathway(BaseModel):
    """Management pathway for a specific comorbidity."""
    comorbidity: str
    preferred_drugs: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    target_bp: Optional[str] = None
    monitoring: Optional[str] = None
    special_notes: Optional[str] = None


class ComplicationEntry(BaseModel):
    """A potential complication."""
    complication: str
    urgency: Optional[UrgencyLevel] = None
    frequency: Optional[str] = None


class FollowUp(BaseModel):
    """Follow-up and monitoring information."""
    frequency: Optional[Dict[str, str]] = None
    annual_review_components: List[str] = Field(default_factory=list)
    quality_metrics: List[str] = Field(default_factory=list)
    interventions: List[str] = Field(default_factory=list)


class PatientEducation(BaseModel):
    """Patient education content."""
    key_messages: List[str] = Field(default_factory=list)
    self_monitoring: Optional[Dict[str, Any]] = None


# =============================================================================
# Triage Metadata (Common to all document types)
# =============================================================================

class TriageMetadata(BaseModel):
    """Triage-critical metadata."""
    urgency_levels: List[UrgencyLevel] = Field(default_factory=lambda: [UrgencyLevel.ROUTINE, UrgencyLevel.URGENT, UrgencyLevel.EMERGENCY])
    default_urgency: UrgencyLevel = UrgencyLevel.ROUTINE
    emergency_triggers: List[Union[str, EmergencyTrigger]] = Field(default_factory=list)
    red_flags: List[Union[str, RedFlag]] = Field(default_factory=list)
    red_flags_for_referral: List[RedFlag] = Field(default_factory=list)
    referral_triggers: List[ReferralTrigger] = Field(default_factory=list)


# =============================================================================
# Classification (for graded conditions like HTN)
# =============================================================================

class GradeCriteria(BaseModel):
    """Criteria for a classification grade."""
    sbp_range: Optional[List[int]] = None
    dbp_range: Optional[List[int]] = None
    sbp_min: Optional[int] = None
    dbp_min: Optional[int] = None
    operator: Optional[str] = None
    additional: Optional[str] = None


class ClassificationGrade(BaseModel):
    """A classification grade."""
    grade: str
    criteria: GradeCriteria
    default_urgency: Optional[UrgencyLevel] = None
    symptoms_mnemonic: Optional[str] = None


class Classification(BaseModel):
    """Classification system for a condition."""
    type: str = "graded"
    grades: List[ClassificationGrade] = Field(default_factory=list)


# =============================================================================
# Clinical Presentation
# =============================================================================

class ClinicalPresentation(BaseModel):
    """Clinical presentation information."""
    symptoms: List[Union[str, SymptomEntry]] = Field(default_factory=list)
    examination_findings: List[str] = Field(default_factory=list)
    when_to_suspect: Optional[str] = None


# =============================================================================
# Differential Diagnosis
# =============================================================================

class DifferentialDiagnosis(BaseModel):
    """A differential diagnosis entry."""
    condition: str
    distinguishing_feature: Optional[str] = None
    prevalence: Optional[str] = None
    causes: List[str] = Field(default_factory=list)


# =============================================================================
# Investigations
# =============================================================================

class InvestigationTier(BaseModel):
    """Investigations at a specific tier."""
    description: Optional[str] = None
    tests: List[Union[str, InvestigationTest]] = Field(default_factory=list)
    indication: Optional[str] = None


class Investigations(BaseModel):
    """Investigation recommendations by tier."""
    # Common format
    baseline: List[Union[str, InvestigationTest]] = Field(default_factory=list)
    confirmatory: List[Union[str, InvestigationTest]] = Field(default_factory=list)
    advanced: List[Union[str, InvestigationTest]] = Field(default_factory=list)

    # Alternative format (narrative guidelines)
    essential: Optional[InvestigationTier] = None
    desirable: Optional[Union[InvestigationTier, Dict[str, Any]]] = None
    comprehensive: Optional[InvestigationTier] = None

    # Simple format
    tests: List[Union[str, InvestigationTest]] = Field(default_factory=list)
    indication: Optional[str] = None


# =============================================================================
# Treatment by Care Level
# =============================================================================

class PHCTreatment(BaseModel):
    """PHC/Primary level treatment."""
    lifestyle_modifications: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)
    drug_therapy: Optional[Dict[str, Any]] = None
    medications: List[DrugEntry] = Field(default_factory=list)
    supportive: List[str] = Field(default_factory=list)
    duration: Optional[str] = None

    # Simple formats
    conservative: List[str] = Field(default_factory=list)
    medical: List[str] = Field(default_factory=list)
    surgical: List[str] = Field(default_factory=list)


class DistrictTreatment(BaseModel):
    """District hospital level treatment."""
    additional_capabilities: List[str] = Field(default_factory=list)
    surgical_indications: List[str] = Field(default_factory=list)
    referrals: List[Dict[str, str]] = Field(default_factory=list)
    fungal_sinusitis: Optional[Dict[str, Any]] = None


class TertiaryTreatment(BaseModel):
    """Tertiary/medical college level treatment."""
    referral_indications: List[str] = Field(default_factory=list)
    additional_capabilities: List[str] = Field(default_factory=list)
    additional_options: List[str] = Field(default_factory=list)
    indications: List[str] = Field(default_factory=list)


class TreatmentByCareLevel(BaseModel):
    """Treatment organized by healthcare facility level."""
    phc_primary: Optional[PHCTreatment] = None
    district_hospital: Optional[DistrictTreatment] = None
    tertiary_medical_college: Optional[TertiaryTreatment] = None
    tertiary: Optional[TertiaryTreatment] = None

    # Alternative format (ObGyn style)
    secondary_hospital: Optional[Dict[str, Any]] = None


# =============================================================================
# Emergency Protocols
# =============================================================================

class EmergencyDrug(BaseModel):
    """Drug for emergency use."""
    drug: str
    dose: Optional[str] = None  # Optional for urgency drugs that may just be "restart therapy"
    onset: Optional[str] = None
    indication: Optional[str] = None


class EmergencyProtocol(BaseModel):
    """An emergency protocol."""
    definition: Optional[str] = None
    target: Optional[str] = None
    drugs: List[EmergencyDrug] = Field(default_factory=list)
    avoid: Optional[str] = None
    management: Optional[str] = None


class StrokeProtocol(BaseModel):
    """Stroke-specific protocol."""
    ischemic_stroke: Optional[Dict[str, str]] = None
    hemorrhagic_stroke: Optional[Dict[str, str]] = None


class EmergencyProtocols(BaseModel):
    """Emergency protocols section."""
    hypertensive_emergency: Optional[EmergencyProtocol] = None
    hypertensive_urgency: Optional[EmergencyProtocol] = None
    stroke_specific: Optional[StrokeProtocol] = None


# =============================================================================
# Step-wise Management
# =============================================================================

class StepWiseManagement(BaseModel):
    """Step-wise management protocol."""
    description: Optional[str] = None
    steps: List[ManagementStep] = Field(default_factory=list)


# =============================================================================
# Main Condition Model
# =============================================================================

class ClinicalCondition(BaseModel):
    """
    Main clinical condition model.
    Supports all 3 document types: narrative_guideline, visual_workflow, step_protocol.
    """
    # Identity
    condition_id: str = Field(..., pattern=r'^[a-z]+_[a-z_]+_\d{3}$')
    name: str
    aliases: List[str] = Field(default_factory=list)
    icd_codes: List[str] = Field(default_factory=list)

    # Classification (optional, for graded conditions)
    classification: Optional[Classification] = None

    # Triage metadata (required)
    triage_metadata: TriageMetadata

    # Clinical presentation
    clinical_presentation: Optional[ClinicalPresentation] = None
    when_to_suspect: Optional[Dict[str, Any]] = None  # Visual workflow format
    related_scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    alternative_diagnoses: Optional[Dict[str, Any]] = None
    clinical_scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    clinical_pearls: List[str] = Field(default_factory=list)
    clinical_examination: Optional[Dict[str, Any]] = None

    # Differential diagnosis
    differential_diagnosis: List[Union[str, DifferentialDiagnosis]] = Field(default_factory=list)

    # Investigations
    investigations: Optional[Investigations] = None

    # Treatment
    treatment_by_care_level: Optional[TreatmentByCareLevel] = None
    treatment_tiers: Optional[Dict[str, Any]] = None  # Alternative format
    parenteral_antibiotic_indications: List[str] = Field(default_factory=list)

    # Comorbidity pathways
    comorbidity_pathways: List[ComorbidityPathway] = Field(default_factory=list)

    # Drug formulary
    drug_formulary: List[DrugEntry] = Field(default_factory=list)

    # Step-wise management
    step_wise_management: Optional[StepWiseManagement] = None

    # Emergency protocols
    emergency_protocols: Optional[EmergencyProtocols] = None

    # Referral criteria
    referral_criteria: List[str] = Field(default_factory=list)

    # Complications
    complications: List[ComplicationEntry] = Field(default_factory=list)

    # Follow-up
    follow_up: Optional[FollowUp] = None

    # Patient education
    patient_education: Optional[PatientEducation] = None

    @field_validator('icd_codes')
    @classmethod
    def validate_icd_codes(cls, v: List[str]) -> List[str]:
        """Validate ICD-10 code format."""
        pattern = r'^[A-Z]\d{2}(\.\d{1,2})?$'
        for code in v:
            if not re.match(pattern, code):
                raise ValueError(f'Invalid ICD-10 code format: {code}')
        return v

    @field_validator('condition_id')
    @classmethod
    def validate_condition_id(cls, v: str) -> str:
        """Validate condition_id format."""
        if not re.match(r'^[a-z]+_[a-z_]+_\d{3}$', v):
            raise ValueError(f'condition_id must match pattern: specialty_name_NNN (e.g., cardio_htn_001)')
        return v


# =============================================================================
# Root Document Model
# =============================================================================

class ClinicalGuidelineDocument(BaseModel):
    """
    Root model for a clinical guideline document.
    Contains metadata and one or more conditions.
    """
    document_meta: DocumentMeta
    conditions: List[ClinicalCondition]

    @model_validator(mode='after')
    def validate_document(self) -> 'ClinicalGuidelineDocument':
        """Cross-field validation."""
        # Ensure at least one condition
        if not self.conditions:
            raise ValueError('Document must contain at least one condition')

        # Check condition_id uniqueness
        ids = [c.condition_id for c in self.conditions]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate condition_id found in document')

        return self


# =============================================================================
# Validation Helper Functions
# =============================================================================

def validate_guideline_json(json_data: Dict[str, Any]) -> ClinicalGuidelineDocument:
    """
    Validate a clinical guideline JSON against the schema.

    Args:
        json_data: Raw JSON data

    Returns:
        Validated ClinicalGuidelineDocument

    Raises:
        ValidationError: If validation fails
    """
    return ClinicalGuidelineDocument(**json_data)


def get_validation_errors(json_data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Get validation errors for a clinical guideline JSON.

    Args:
        json_data: Raw JSON data

    Returns:
        List of error details, or None if valid
    """
    try:
        ClinicalGuidelineDocument(**json_data)
        return None
    except Exception as e:
        if hasattr(e, 'errors'):
            return e.errors()
        return [{"error": str(e)}]

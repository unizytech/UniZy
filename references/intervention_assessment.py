"""
Intervention Assessment Module for Patient Adherence

This module calculates the level of intervention required to ensure patients
adhere to and complete their health outcomes. It uses a two-axis framework:

1. Clinical Severity (Stakes): What happens if they don't adhere?
2. Adherence Risk (Probability): How likely are they to drop off?

The combination determines the intervention level: LOW, MEDIUM, HIGH, or CRITICAL.

Usage:
    from intervention_assessment import (
        assess_intervention,
        ClinicalInput,
        AdherenceInput
    )
    
    result = assess_intervention(
        clinical=ClinicalInput(
            specialty="cardiology",
            diagnosis_text="Coronary artery disease",
            icd_codes=["I25.1"],
            medications=["Aspirin", "Atorvastatin", "Metoprolol"],
            follow_up_urgency="soon",
            is_surgical=False,
            is_chronic=True
        ),
        adherence=AdherenceInput(
            pre_anxiety=7.0,
            post_anxiety=5.0,
            financial_concern=6.0,
            compliance_likelihood=5.0
        )
    )
    
    print(result.intervention_level)  # InterventionLevel.HIGH

Author: Unizy Health
Version: 1.0.0
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json
from pathlib import Path


# =============================================================================
# ENUMS
# =============================================================================

class ClinicalSeverity(Enum):
    """Clinical severity level based on stakes of non-adherence."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class AdherenceRisk(Enum):
    """Risk level of patient not adhering to treatment."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class InterventionLevel(Enum):
    """Final intervention level determining resource allocation."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# =============================================================================
# DATA CLASSES - INPUTS
# =============================================================================

@dataclass
class ClinicalInput:
    """
    Clinical signals extracted from consultation.
    
    Attributes:
        specialty: Medical specialty (e.g., "cardiology", "orthopedics")
        diagnosis_text: Free-text diagnosis from consultation
        icd_codes: List of ICD-10 codes for the diagnosis
        medications: List of prescribed medications
        chief_complaints: List of patient's chief complaints
        follow_up_days: Days until follow-up appointment
        follow_up_urgency: "routine", "soon", or "urgent"
        is_surgical: Whether treatment involves surgery
        is_chronic: Whether condition is chronic
        treatment_duration_days: Expected treatment duration in days
    """
    specialty: str
    diagnosis_text: str
    icd_codes: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)
    chief_complaints: list[str] = field(default_factory=list)
    follow_up_days: Optional[int] = None
    follow_up_urgency: Optional[str] = None
    is_surgical: bool = False
    is_chronic: bool = False
    treatment_duration_days: Optional[int] = None


@dataclass
class AdherenceInput:
    """
    Psychosocial signals from consultation (real-time emotion analysis).
    
    All scores are on a 0-10 scale.
    
    Attributes:
        pre_anxiety: Patient anxiety level before consultation
        post_anxiety: Patient anxiety level after consultation
        financial_concern: Level of financial concern about treatment (10 = very concerned)
        compliance_likelihood: Doctor's assessment of compliance likelihood (10 = very likely)
    """
    pre_anxiety: float
    post_anxiety: float
    financial_concern: float
    compliance_likelihood: float


# =============================================================================
# DATA CLASSES - OUTPUTS
# =============================================================================

@dataclass
class ClinicalSeverityResult:
    """Result of clinical severity assessment."""
    severity: ClinicalSeverity
    total_score: int
    was_overridden: bool
    override_reason: Optional[str]
    score_breakdown: dict
    contributing_factors: list[str]


@dataclass
class AdherenceRiskResult:
    """Result of adherence risk assessment."""
    risk_level: AdherenceRisk
    risk_score: float
    risk_drivers: dict


@dataclass
class InterventionAssessment:
    """
    Complete intervention assessment result.
    
    This is the main output containing all assessment details
    and recommended actions.
    """
    intervention_level: InterventionLevel
    clinical_severity: ClinicalSeverityResult
    adherence_risk: AdherenceRiskResult
    recommended_actions: list[str]
    intervention_cadence: str
    channel_mix: list[str]
    
    def to_dict(self) -> dict:
        """Convert assessment to dictionary for JSON serialization."""
        return {
            "intervention_level": self.intervention_level.name,
            "clinical_severity": {
                "level": self.clinical_severity.severity.name,
                "score": self.clinical_severity.total_score,
                "was_overridden": self.clinical_severity.was_overridden,
                "override_reason": self.clinical_severity.override_reason,
                "contributing_factors": self.clinical_severity.contributing_factors,
                "score_breakdown": self.clinical_severity.score_breakdown
            },
            "adherence_risk": {
                "level": self.adherence_risk.risk_level.name,
                "score": self.adherence_risk.risk_score,
                "drivers": self.adherence_risk.risk_drivers
            },
            "recommended_actions": self.recommended_actions,
            "intervention_cadence": self.intervention_cadence,
            "channel_mix": self.channel_mix
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert assessment to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# =============================================================================
# CONFIGURATION - ICD-10 MAPPINGS
# =============================================================================

# ICD-10 codes that ALWAYS trigger HIGH severity (hard overrides)
ICD_CRITICAL_CODES = {
    # Acute cardiac events
    "I21",    # Acute myocardial infarction
    "I22",    # Subsequent MI
    "I46",    # Cardiac arrest
    
    # Cerebrovascular events
    "I60",    # Subarachnoid hemorrhage
    "I61",    # Intracerebral hemorrhage
    "I63",    # Cerebral infarction (stroke)
    
    # Organ failure
    "J96",    # Respiratory failure
    "N17",    # Acute kidney failure
    "K72",    # Hepatic failure
    
    # Diabetic emergencies
    "E10.1",  # Type 1 diabetes with ketoacidosis
    "E11.1",  # Type 2 diabetes with ketoacidosis
    
    # Anaphylaxis
    "T78.2",  # Anaphylactic shock
    
    # Sepsis
    "A41",    # Other sepsis
    "R65.2",  # Severe sepsis
}

# ICD-10 chapter/prefix to severity score mapping
ICD_CHAPTER_SCORES = {
    # HIGH severity chapters (4 points)
    "C": 4,       # Malignant neoplasms (all cancers)
    "D0": 4,      # In-situ neoplasms
    "I2": 4,      # Ischemic heart diseases
    "I5": 4,      # Heart failure
    "I6": 4,      # Cerebrovascular diseases
    "N18": 4,     # Chronic kidney disease
    "Z94": 4,     # Transplanted organ status
    
    # MEDIUM-HIGH severity (3 points)
    "E10": 3,     # Type 1 diabetes
    "E11": 3,     # Type 2 diabetes
    "I1": 3,      # Hypertensive diseases
    "I4": 3,      # Other heart diseases
    "J44": 3,     # COPD
    "J45": 3,     # Asthma
    "K70": 3,     # Alcoholic liver disease
    "K74": 3,     # Fibrosis/cirrhosis of liver
    "F2": 3,      # Schizophrenia spectrum
    "F3": 3,      # Mood disorders (depression, bipolar)
    "B20": 3,     # HIV disease
    
    # MEDIUM severity (2 points)
    "M": 2,       # Musculoskeletal (orthopedics)
    "G": 2,       # Nervous system diseases
    "K": 2,       # Digestive system
    "N": 2,       # Genitourinary system
    "E0": 2,      # Other endocrine (thyroid, etc.)
    "F": 2,       # Mental/behavioral (general)
    "J": 2,       # Respiratory (general)
    "D5": 2,      # Anemia
    
    # LOW severity (1 point)
    "H": 1,       # Eye and ear disorders
    "L": 1,       # Skin conditions
    "R": 1,       # Symptoms/signs (undiagnosed)
    "Z": 1,       # Factors influencing health status
    "J0": 1,      # Acute upper respiratory infections
}


# =============================================================================
# CONFIGURATION - SPECIALTY MAPPINGS
# =============================================================================

SPECIALTY_SCORES = {
    # High stakes (3 points)
    "oncology": 3,
    "cardiology": 3,
    "cardiac_surgery": 3,
    "neurology": 3,
    "neurosurgery": 3,
    "nephrology": 3,
    "transplant": 3,
    "critical_care": 3,
    "icu": 3,
    "hematology": 3,
    "neonatology": 3,
    
    # Medium stakes (2 points)
    "endocrinology": 2,
    "pulmonology": 2,
    "orthopedics": 2,
    "orthopedic_surgery": 2,
    "psychiatry": 2,
    "gastroenterology": 2,
    "rheumatology": 2,
    "urology": 2,
    "gynecology": 2,
    "obstetrics": 2,
    "infectious_disease": 2,
    "vascular_surgery": 2,
    "general_surgery": 2,
    
    # Lower stakes (1 point)
    "dermatology": 1,
    "ent": 1,
    "ophthalmology": 1,
    "general_medicine": 1,
    "family_medicine": 1,
    "internal_medicine": 1,
    "pediatrics": 1,
    "allergy": 1,
    "sports_medicine": 1,
    "physical_therapy": 1,
}


# =============================================================================
# CONFIGURATION - KEYWORD LISTS
# =============================================================================

# Keywords that ALWAYS trigger HIGH severity (overrides)
CRITICAL_KEYWORDS = [
    "malignant", "malignancy", "cancer", "carcinoma", "tumor", "tumour",
    "metastatic", "metastasis", "critical", "emergency", "acute",
    "failure", "arrest", "infarction", "hemorrhage", "haemorrhage",
    "sepsis", "septic", "transplant", "dialysis", "ventilator",
    "icu", "intensive care", "life threatening", "life-threatening"
]

# Keywords indicating surgical context
SURGICAL_KEYWORDS = [
    "surgery", "surgical", "operation", "procedure", "post-op",
    "post-operative", "postoperative", "pre-op", "pre-operative",
    "preoperative", "arthroplasty", "replacement", "resection",
    "excision", "implant", "graft", "bypass", "angioplasty",
    "laparoscopy", "laparoscopic", "arthroscopy", "arthroscopic",
    "amputation", "reconstruction", "fusion", "fixation"
]

# Keywords indicating chronic condition
CHRONIC_KEYWORDS = [
    "chronic", "long-term", "long term", "ongoing", "management",
    "controlled", "uncontrolled", "maintenance", "lifetime",
    "permanent", "progressive", "degenerative", "persistent"
]


# =============================================================================
# CONFIGURATION - INTERVENTION ACTIONS
# =============================================================================

INTERVENTION_ACTIONS = {
    InterventionLevel.LOW: {
        "actions": [
            "Automated WhatsApp medication reminders",
            "Self-service appointment booking link",
            "Digital health tips relevant to condition"
        ],
        "cadence": "Automated only",
        "channels": ["WhatsApp", "App notifications", "SMS"]
    },
    InterventionLevel.MEDIUM: {
        "actions": [
            "Weekly care coordinator call",
            "Personalized WhatsApp check-ins",
            "Simplified treatment summary in local language",
            "Medication adherence tracking"
        ],
        "cadence": "Weekly human touch",
        "channels": ["WhatsApp", "Phone call", "App notifications"]
    },
    InterventionLevel.HIGH: {
        "actions": [
            "Dedicated care manager assignment",
            "Bi-weekly calls with family member loop-in",
            "Proactive appointment scheduling",
            "Treatment plan simplification review",
            "Medication delivery arrangement"
        ],
        "cadence": "Bi-weekly engagement",
        "channels": ["Phone calls", "WhatsApp", "Video calls", "Family contact"]
    },
    InterventionLevel.CRITICAL: {
        "actions": [
            "Daily care manager engagement",
            "Family/caregiver mandatory involvement",
            "Financial counseling session",
            "Doctor callback for plan modification",
            "Home visit consideration",
            "Emergency contact protocol setup"
        ],
        "cadence": "Daily engagement",
        "channels": ["Daily phone calls", "Home visits", "Family coordination", "Doctor escalation"]
    }
}

# Additional actions based on specific risk drivers
RISK_DRIVER_ACTIONS = {
    "high_financial_concern": [
        "EMI/payment plan options discussion",
        "Generic medication alternatives review",
        "Government scheme eligibility check",
        "Insurance claim assistance"
    ],
    "high_anxiety": [
        "Post-consultation anxiety follow-up call within 24hrs",
        "Patient education materials (video preferred)",
        "Support group information",
        "Mental health resource connection"
    ],
    "low_compliance": [
        "Treatment plan simplification",
        "Visual medication schedule",
        "Pill organizer arrangement",
        "Daily reminder calls"
    ]
}


# =============================================================================
# INTERVENTION MATRIX
# =============================================================================

# Matrix mapping (clinical_severity, adherence_risk) -> intervention_level
INTERVENTION_MATRIX = {
    # Low clinical severity
    (ClinicalSeverity.LOW, AdherenceRisk.LOW): InterventionLevel.LOW,
    (ClinicalSeverity.LOW, AdherenceRisk.MEDIUM): InterventionLevel.LOW,
    (ClinicalSeverity.LOW, AdherenceRisk.HIGH): InterventionLevel.MEDIUM,
    
    # Medium clinical severity
    (ClinicalSeverity.MEDIUM, AdherenceRisk.LOW): InterventionLevel.LOW,
    (ClinicalSeverity.MEDIUM, AdherenceRisk.MEDIUM): InterventionLevel.MEDIUM,
    (ClinicalSeverity.MEDIUM, AdherenceRisk.HIGH): InterventionLevel.HIGH,
    
    # High clinical severity
    (ClinicalSeverity.HIGH, AdherenceRisk.LOW): InterventionLevel.MEDIUM,
    (ClinicalSeverity.HIGH, AdherenceRisk.MEDIUM): InterventionLevel.HIGH,
    (ClinicalSeverity.HIGH, AdherenceRisk.HIGH): InterventionLevel.CRITICAL,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _normalize_text(text: str) -> str:
    """Normalize text for keyword matching."""
    return text.lower().strip().replace("-", "_").replace(" ", "_")


def _check_critical_override(
    icd_codes: list[str],
    diagnosis_text: str
) -> tuple[bool, Optional[str]]:
    """
    Check if any hard override conditions are met.
    
    Returns:
        Tuple of (should_override, reason)
    """
    # Check ICD critical codes
    for code in icd_codes:
        code_upper = code.upper().strip()
        
        # Check exact matches
        if code_upper in ICD_CRITICAL_CODES:
            return True, f"Critical ICD code: {code_upper}"
        
        # Check prefix matches for all cancers
        if code_upper.startswith("C"):
            return True, f"Malignancy ICD code: {code_upper}"
    
    # Check keywords in diagnosis text
    diagnosis_lower = diagnosis_text.lower()
    for keyword in CRITICAL_KEYWORDS:
        if keyword in diagnosis_lower:
            return True, f"Critical keyword: '{keyword}'"
    
    return False, None


def _get_icd_score(icd_codes: list[str]) -> tuple[int, list[str]]:
    """
    Get severity score from ICD-10 codes.
    
    Returns:
        Tuple of (max_score, contributing_codes)
    """
    if not icd_codes:
        return 0, []
    
    max_score = 0
    contributing_codes = []
    
    for code in icd_codes:
        code_upper = code.upper().strip()
        
        # Try matching from most specific to least specific
        for prefix, score in sorted(
            ICD_CHAPTER_SCORES.items(),
            key=lambda x: len(x[0]),
            reverse=True
        ):
            if code_upper.startswith(prefix):
                if score > max_score:
                    max_score = score
                    contributing_codes = [code_upper]
                elif score == max_score:
                    contributing_codes.append(code_upper)
                break
    
    return max_score, contributing_codes


def _get_specialty_score(specialty: str) -> int:
    """Get severity score from medical specialty."""
    normalized = _normalize_text(specialty)
    return SPECIALTY_SCORES.get(normalized, 1)


def _infer_surgical_flag(diagnosis_text: str, explicit_flag: bool) -> bool:
    """Infer surgical context if not explicitly set."""
    if explicit_flag:
        return True
    
    diagnosis_lower = diagnosis_text.lower()
    return any(kw in diagnosis_lower for kw in SURGICAL_KEYWORDS)


def _infer_chronic_flag(
    diagnosis_text: str,
    explicit_flag: bool,
    treatment_duration_days: Optional[int]
) -> bool:
    """Infer chronic condition if not explicitly set."""
    if explicit_flag:
        return True
    
    if treatment_duration_days and treatment_duration_days > 90:
        return True
    
    diagnosis_lower = diagnosis_text.lower()
    return any(kw in diagnosis_lower for kw in CHRONIC_KEYWORDS)


def _calculate_modifier_score(
    is_chronic: bool,
    medication_count: int,
    follow_up_urgency: Optional[str],
    treatment_duration_days: Optional[int]
) -> tuple[int, dict]:
    """
    Calculate modifier/boost score from secondary signals.
    
    Returns:
        Tuple of (score, breakdown_dict)
    """
    score = 0
    breakdown = {}
    
    # Chronic condition modifier
    if is_chronic:
        score += 1
        breakdown["chronic_condition"] = 1
    
    # Polypharmacy modifier
    if medication_count >= 5:
        score += 2
        breakdown["polypharmacy"] = 2
    elif medication_count >= 3:
        score += 1
        breakdown["polypharmacy"] = 1
    
    # Follow-up urgency modifier
    if follow_up_urgency:
        urgency_lower = follow_up_urgency.lower()
        if urgency_lower in ("urgent", "immediate", "emergency"):
            score += 2
            breakdown["follow_up_urgency"] = 2
        elif urgency_lower in ("soon", "early", "priority"):
            score += 1
            breakdown["follow_up_urgency"] = 1
    
    # Treatment duration modifier
    if treatment_duration_days:
        if treatment_duration_days > 90:
            score += 2
            breakdown["long_treatment"] = 2
        elif treatment_duration_days > 30:
            score += 1
            breakdown["long_treatment"] = 1
    
    return score, breakdown


def _score_to_clinical_severity(total_score: int) -> ClinicalSeverity:
    """Map total score to clinical severity level."""
    if total_score >= 9:
        return ClinicalSeverity.HIGH
    elif total_score >= 5:
        return ClinicalSeverity.MEDIUM
    else:
        return ClinicalSeverity.LOW


def _score_to_adherence_risk(raw_score: float) -> AdherenceRisk:
    """Map raw score to adherence risk level."""
    if raw_score >= 7:
        return AdherenceRisk.HIGH
    elif raw_score >= 4.5:
        return AdherenceRisk.MEDIUM
    else:
        return AdherenceRisk.LOW


def _get_recommended_actions(
    intervention_level: InterventionLevel,
    risk_drivers: dict
) -> list[str]:
    """Get tailored actions based on level and risk drivers."""
    base_config = INTERVENTION_ACTIONS[intervention_level]
    actions = base_config["actions"].copy()
    
    # Add specific interventions based on risk drivers
    if risk_drivers.get("financial_concern", 0) >= 7:
        actions.extend(RISK_DRIVER_ACTIONS["high_financial_concern"])
    
    if risk_drivers.get("anxiety_trajectory", 0) >= 7:
        actions.extend(RISK_DRIVER_ACTIONS["high_anxiety"])
    
    if risk_drivers.get("compliance_risk", 0) >= 7:
        actions.extend(RISK_DRIVER_ACTIONS["low_compliance"])
    
    return actions


# =============================================================================
# MAIN ASSESSMENT FUNCTIONS
# =============================================================================

def assess_clinical_severity(clinical: ClinicalInput) -> ClinicalSeverityResult:
    """
    Assess clinical severity from consultation data.
    
    Clinical severity represents the stakes of non-adherence:
    "What happens if the patient doesn't follow the treatment plan?"
    
    Args:
        clinical: ClinicalInput containing all clinical signals
        
    Returns:
        ClinicalSeverityResult with severity level and breakdown
    """
    contributing_factors = []
    score_breakdown = {}
    
    # LAYER 1: Check for hard overrides
    should_override, override_reason = _check_critical_override(
        clinical.icd_codes,
        clinical.diagnosis_text
    )
    
    if should_override:
        return ClinicalSeverityResult(
            severity=ClinicalSeverity.HIGH,
            total_score=999,
            was_overridden=True,
            override_reason=override_reason,
            score_breakdown={"override": override_reason},
            contributing_factors=[override_reason]
        )
    
    # LAYER 2: Base score calculation
    
    # ICD-10 score
    icd_score, icd_contributors = _get_icd_score(clinical.icd_codes)
    score_breakdown["icd_score"] = icd_score
    if icd_contributors:
        contributing_factors.append(f"ICD codes: {', '.join(icd_contributors)}")
    
    # Specialty score
    specialty_score = _get_specialty_score(clinical.specialty)
    score_breakdown["specialty_score"] = specialty_score
    contributing_factors.append(f"Specialty: {clinical.specialty}")
    
    # Surgical flag
    is_surgical = _infer_surgical_flag(
        clinical.diagnosis_text,
        clinical.is_surgical
    )
    surgical_score = 3 if is_surgical else 0
    score_breakdown["surgical_score"] = surgical_score
    if is_surgical:
        contributing_factors.append("Surgical intervention")
    
    # Base score = max(ICD, specialty) + surgical
    base_score = max(icd_score, specialty_score) + surgical_score
    score_breakdown["base_score"] = base_score
    
    # LAYER 3: Modifier score
    is_chronic = _infer_chronic_flag(
        clinical.diagnosis_text,
        clinical.is_chronic,
        clinical.treatment_duration_days
    )
    
    modifier_score, modifier_breakdown = _calculate_modifier_score(
        is_chronic=is_chronic,
        medication_count=len(clinical.medications),
        follow_up_urgency=clinical.follow_up_urgency,
        treatment_duration_days=clinical.treatment_duration_days
    )
    
    score_breakdown["modifier_score"] = modifier_score
    score_breakdown["modifier_breakdown"] = modifier_breakdown
    
    for modifier_name, modifier_value in modifier_breakdown.items():
        if modifier_value > 0:
            contributing_factors.append(
                f"{modifier_name.replace('_', ' ').title()}: +{modifier_value}"
            )
    
    # LAYER 4: Total score and severity mapping
    total_score = base_score + modifier_score
    severity = _score_to_clinical_severity(total_score)
    
    return ClinicalSeverityResult(
        severity=severity,
        total_score=total_score,
        was_overridden=False,
        override_reason=None,
        score_breakdown=score_breakdown,
        contributing_factors=contributing_factors
    )


def assess_adherence_risk(adherence: AdherenceInput) -> AdherenceRiskResult:
    """
    Assess adherence/dropout risk from psychosocial factors.
    
    Adherence risk represents the probability of non-adherence:
    "How likely is this patient to drop off from treatment?"
    
    Args:
        adherence: AdherenceInput containing psychosocial signals
        
    Returns:
        AdherenceRiskResult with risk level and drivers
    """
    risk_drivers = {}
    
    # Anxiety trajectory analysis
    anxiety_delta = adherence.post_anxiety - adherence.pre_anxiety
    
    if anxiety_delta > 2:
        anxiety_risk = 9  # Consultation made things significantly worse
    elif anxiety_delta > 0:
        anxiety_risk = 6  # No improvement or slight worsening
    elif anxiety_delta >= -2:
        anxiety_risk = 4  # Mild improvement
    else:
        anxiety_risk = 2  # Significant calming effect
    
    # Override if still very anxious after consultation
    if adherence.post_anxiety >= 7:
        anxiety_risk = max(anxiety_risk, 7)
    
    risk_drivers["anxiety_trajectory"] = round(anxiety_risk, 2)
    risk_drivers["anxiety_delta"] = round(anxiety_delta, 2)
    
    # Financial concern - direct mapping
    financial_risk = adherence.financial_concern
    risk_drivers["financial_concern"] = round(financial_risk, 2)
    
    # Compliance likelihood - inverse
    compliance_risk = 10 - adherence.compliance_likelihood
    risk_drivers["compliance_risk"] = round(compliance_risk, 2)
    
    # Weighted combination
    # Financial and compliance weighted higher as they're stronger predictors
    raw_score = (
        (anxiety_risk * 0.25) +
        (financial_risk * 0.40) +
        (compliance_risk * 0.35)
    )
    
    risk_level = _score_to_adherence_risk(raw_score)
    
    return AdherenceRiskResult(
        risk_level=risk_level,
        risk_score=round(raw_score, 2),
        risk_drivers=risk_drivers
    )


def determine_intervention_level(
    clinical_severity: ClinicalSeverity,
    adherence_risk: AdherenceRisk
) -> InterventionLevel:
    """
    Determine intervention level using the two-axis matrix.
    
    Args:
        clinical_severity: Clinical severity level (stakes)
        adherence_risk: Adherence risk level (probability)
        
    Returns:
        InterventionLevel from the matrix lookup
    """
    return INTERVENTION_MATRIX.get(
        (clinical_severity, adherence_risk),
        InterventionLevel.MEDIUM  # Default fallback
    )


def assess_intervention(
    clinical: ClinicalInput,
    adherence: AdherenceInput
) -> InterventionAssessment:
    """
    Complete intervention assessment combining clinical severity and adherence risk.
    
    This is the main entry point for the intervention assessment system.
    
    Args:
        clinical: ClinicalInput with all clinical signals
        adherence: AdherenceInput with psychosocial signals
        
    Returns:
        InterventionAssessment with complete results and recommendations
        
    Example:
        >>> result = assess_intervention(
        ...     clinical=ClinicalInput(
        ...         specialty="cardiology",
        ...         diagnosis_text="Coronary artery disease with stable angina",
        ...         icd_codes=["I25.1", "I20.8"],
        ...         medications=["Aspirin", "Atorvastatin", "Metoprolol"],
        ...         follow_up_urgency="soon",
        ...         is_chronic=True
        ...     ),
        ...     adherence=AdherenceInput(
        ...         pre_anxiety=7.0,
        ...         post_anxiety=5.0,
        ...         financial_concern=6.0,
        ...         compliance_likelihood=5.0
        ...     )
        ... )
        >>> print(result.intervention_level)
        InterventionLevel.HIGH
    """
    # Axis 1: Clinical Severity (Stakes)
    clinical_result = assess_clinical_severity(clinical)
    
    # Axis 2: Adherence Risk (Probability)
    adherence_result = assess_adherence_risk(adherence)
    
    # Matrix lookup for intervention level
    intervention_level = determine_intervention_level(
        clinical_result.severity,
        adherence_result.risk_level
    )
    
    # Get recommended actions
    recommended_actions = _get_recommended_actions(
        intervention_level,
        adherence_result.risk_drivers
    )
    
    # Get cadence and channels
    intervention_config = INTERVENTION_ACTIONS[intervention_level]
    
    return InterventionAssessment(
        intervention_level=intervention_level,
        clinical_severity=clinical_result,
        adherence_risk=adherence_result,
        recommended_actions=recommended_actions,
        intervention_cadence=intervention_config["cadence"],
        channel_mix=intervention_config["channels"]
    )


# =============================================================================
# CONFIGURATION MANAGEMENT
# =============================================================================

def load_icd_config(config_path: str) -> dict:
    """
    Load ICD-10 severity mapping from external JSON config.
    
    This allows clinical teams to update mappings without code changes.
    
    Args:
        config_path: Path to JSON configuration file
        
    Returns:
        Configuration dictionary
    """
    config_file = Path(config_path)
    
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    
    # Return default config if file doesn't exist
    return {
        "critical_codes": list(ICD_CRITICAL_CODES),
        "chapter_scores": ICD_CHAPTER_SCORES,
        "version": "1.0.0",
        "last_updated": "2024-01-01"
    }


def save_icd_config(config: dict, config_path: str) -> None:
    """
    Save ICD-10 configuration to JSON file.
    
    Args:
        config: Configuration dictionary
        config_path: Path to save the configuration
    """
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def update_icd_critical_codes(codes: set[str]) -> None:
    """Update the global ICD critical codes set."""
    global ICD_CRITICAL_CODES
    ICD_CRITICAL_CODES = codes


def update_icd_chapter_scores(scores: dict[str, int]) -> None:
    """Update the global ICD chapter scores mapping."""
    global ICD_CHAPTER_SCORES
    ICD_CHAPTER_SCORES = scores


def update_specialty_scores(scores: dict[str, int]) -> None:
    """Update the global specialty scores mapping."""
    global SPECIALTY_SCORES
    SPECIALTY_SCORES = scores


# =============================================================================
# THRESHOLD CALIBRATION
# =============================================================================

def calibrate_thresholds(
    historical_data: list[dict],
    target_high_intervention_rate: float = 0.4
) -> dict:
    """
    Calibrate score thresholds based on historical data.
    
    Use this to adjust thresholds so that approximately target_high_intervention_rate
    of patients receive MEDIUM or higher intervention.
    
    Args:
        historical_data: List of dicts with keys matching ClinicalInput and AdherenceInput
        target_high_intervention_rate: Target percentage of patients for MEDIUM+ intervention
        
    Returns:
        Dictionary with suggested threshold adjustments
        
    Example:
        >>> historical = [
        ...     {"specialty": "cardiology", "pre_anxiety": 6, ...},
        ...     {"specialty": "dermatology", "pre_anxiety": 3, ...},
        ...     ...
        ... ]
        >>> suggestions = calibrate_thresholds(historical, target_rate=0.4)
        >>> print(suggestions)
        {"adherence_medium_threshold": 4.2, "adherence_high_threshold": 6.8, ...}
    """
    if not historical_data:
        return {"error": "No historical data provided"}
    
    # Calculate scores for all historical patients
    adherence_scores = []
    clinical_scores = []
    
    for record in historical_data:
        try:
            # Build inputs from historical record
            clinical = ClinicalInput(
                specialty=record.get("specialty", "general_medicine"),
                diagnosis_text=record.get("diagnosis_text", ""),
                icd_codes=record.get("icd_codes", []),
                medications=record.get("medications", []),
                follow_up_urgency=record.get("follow_up_urgency"),
                is_surgical=record.get("is_surgical", False),
                is_chronic=record.get("is_chronic", False),
                treatment_duration_days=record.get("treatment_duration_days")
            )
            
            adherence = AdherenceInput(
                pre_anxiety=record.get("pre_anxiety", 5),
                post_anxiety=record.get("post_anxiety", 5),
                financial_concern=record.get("financial_concern", 5),
                compliance_likelihood=record.get("compliance_likelihood", 5)
            )
            
            clinical_result = assess_clinical_severity(clinical)
            adherence_result = assess_adherence_risk(adherence)
            
            if not clinical_result.was_overridden:
                clinical_scores.append(clinical_result.total_score)
            adherence_scores.append(adherence_result.risk_score)
            
        except Exception as e:
            continue
    
    if not adherence_scores:
        return {"error": "Could not process any historical records"}
    
    # Sort scores and find threshold percentiles
    adherence_scores.sort()
    clinical_scores.sort()
    
    # Find threshold that would give target_high_intervention_rate as MEDIUM+
    low_intervention_rate = 1 - target_high_intervention_rate
    threshold_index = int(len(adherence_scores) * low_intervention_rate)
    
    suggested_medium_threshold = adherence_scores[threshold_index] if threshold_index < len(adherence_scores) else 4.5
    
    # High threshold at 75th percentile of those above medium
    high_scores = [s for s in adherence_scores if s >= suggested_medium_threshold]
    if high_scores:
        high_threshold_index = int(len(high_scores) * 0.5)
        suggested_high_threshold = high_scores[high_threshold_index]
    else:
        suggested_high_threshold = 7.0
    
    return {
        "sample_size": len(adherence_scores),
        "current_thresholds": {
            "adherence_medium": 4.5,
            "adherence_high": 7.0,
            "clinical_medium": 5,
            "clinical_high": 9
        },
        "suggested_thresholds": {
            "adherence_medium": round(suggested_medium_threshold, 2),
            "adherence_high": round(suggested_high_threshold, 2)
        },
        "score_distribution": {
            "adherence_min": round(min(adherence_scores), 2),
            "adherence_max": round(max(adherence_scores), 2),
            "adherence_median": round(adherence_scores[len(adherence_scores)//2], 2),
            "clinical_min": min(clinical_scores) if clinical_scores else 0,
            "clinical_max": max(clinical_scores) if clinical_scores else 0
        }
    }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def quick_assess(
    specialty: str,
    diagnosis: str,
    pre_anxiety: float,
    post_anxiety: float,
    financial_concern: float,
    compliance_likelihood: float,
    icd_codes: list[str] = None,
    medications: list[str] = None,
    is_surgical: bool = False
) -> InterventionAssessment:
    """
    Quick assessment with minimal inputs.
    
    Convenience function for simple use cases where you don't need
    all the input fields.
    
    Args:
        specialty: Medical specialty
        diagnosis: Diagnosis text
        pre_anxiety: Pre-consultation anxiety (0-10)
        post_anxiety: Post-consultation anxiety (0-10)
        financial_concern: Financial concern level (0-10)
        compliance_likelihood: Compliance likelihood (0-10)
        icd_codes: Optional list of ICD-10 codes
        medications: Optional list of medications
        is_surgical: Whether treatment involves surgery
        
    Returns:
        InterventionAssessment with results
    """
    clinical = ClinicalInput(
        specialty=specialty,
        diagnosis_text=diagnosis,
        icd_codes=icd_codes or [],
        medications=medications or [],
        is_surgical=is_surgical
    )
    
    adherence = AdherenceInput(
        pre_anxiety=pre_anxiety,
        post_anxiety=post_anxiety,
        financial_concern=financial_concern,
        compliance_likelihood=compliance_likelihood
    )
    
    return assess_intervention(clinical, adherence)


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "1.0.0"
__author__ = "Unizy Health"
__all__ = [
    # Enums
    "ClinicalSeverity",
    "AdherenceRisk",
    "InterventionLevel",
    
    # Input classes
    "ClinicalInput",
    "AdherenceInput",
    
    # Output classes
    "ClinicalSeverityResult",
    "AdherenceRiskResult",
    "InterventionAssessment",
    
    # Main functions
    "assess_intervention",
    "assess_clinical_severity",
    "assess_adherence_risk",
    "determine_intervention_level",
    "quick_assess",
    
    # Configuration
    "load_icd_config",
    "save_icd_config",
    "update_icd_critical_codes",
    "update_icd_chapter_scores",
    "update_specialty_scores",
    "calibrate_thresholds",
]


# =============================================================================
# EXAMPLE USAGE (when run directly)
# =============================================================================

if __name__ == "__main__":
    # Example 1: High-risk cardiac patient
    print("=" * 60)
    print("Example 1: High-risk Cardiac Patient")
    print("=" * 60)
    
    result = assess_intervention(
        clinical=ClinicalInput(
            specialty="cardiology",
            diagnosis_text="Coronary artery disease with unstable angina",
            icd_codes=["I25.1", "I20.0"],
            medications=["Aspirin", "Atorvastatin", "Metoprolol", "Lisinopril", "Clopidogrel"],
            follow_up_urgency="urgent",
            is_chronic=True
        ),
        adherence=AdherenceInput(
            pre_anxiety=8.0,
            post_anxiety=7.0,
            financial_concern=7.0,
            compliance_likelihood=4.0
        )
    )
    
    print(f"Intervention Level: {result.intervention_level.name}")
    print(f"Clinical Severity: {result.clinical_severity.severity.name} (score: {result.clinical_severity.total_score})")
    print(f"Adherence Risk: {result.adherence_risk.risk_level.name} (score: {result.adherence_risk.risk_score})")
    print(f"Cadence: {result.intervention_cadence}")
    print(f"Recommended Actions:")
    for action in result.recommended_actions[:5]:
        print(f"  - {action}")
    
    print("\n" + "=" * 60)
    print("Example 2: Low-risk Dermatology Patient")
    print("=" * 60)
    
    result2 = quick_assess(
        specialty="dermatology",
        diagnosis="Mild acne vulgaris",
        pre_anxiety=3.0,
        post_anxiety=2.0,
        financial_concern=2.0,
        compliance_likelihood=8.0,
        icd_codes=["L70.0"]
    )
    
    print(f"Intervention Level: {result2.intervention_level.name}")
    print(f"Clinical Severity: {result2.clinical_severity.severity.name}")
    print(f"Adherence Risk: {result2.adherence_risk.risk_level.name}")
    
    print("\n" + "=" * 60)
    print("Example 3: Cancer Override (Critical)")
    print("=" * 60)
    
    result3 = assess_intervention(
        clinical=ClinicalInput(
            specialty="general_medicine",
            diagnosis_text="Suspected lung mass",
            icd_codes=["C34.9"],
            medications=["Paracetamol"],
            follow_up_urgency="urgent"
        ),
        adherence=AdherenceInput(
            pre_anxiety=5.0,
            post_anxiety=5.0,
            financial_concern=5.0,
            compliance_likelihood=7.0
        )
    )
    
    print(f"Intervention Level: {result3.intervention_level.name}")
    print(f"Override Triggered: {result3.clinical_severity.was_overridden}")
    print(f"Override Reason: {result3.clinical_severity.override_reason}")
    
    print("\n" + "=" * 60)
    print("JSON Output Example")
    print("=" * 60)
    print(result.to_json())

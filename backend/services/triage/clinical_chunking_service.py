"""
Clinical Chunking Service

Extracts semantic chunks from validated clinical conditions based on document type.
Each chunk is tagged with metadata for filtered retrieval.

Chunk Types:
- triage_criteria: Red flags, emergency triggers, urgency thresholds
- classification: Grades, staging, severity criteria
- presentation: Symptoms, when to suspect, exam findings
- differential: DDx with distinguishing features
- investigation: Labs, imaging by tier
- treatment_primary: PHC-level management
- treatment_district: District hospital options
- treatment_tertiary: Tertiary/referral options
- comorbidity_pathway: Per-comorbidity drug preferences
- drug_formulary: Dosing, contraindications, monitoring
- emergency_protocol: Urgency/emergency handling
- step_protocol: Ordered steps
- follow_up: Monitoring frequency, quality metrics
"""

import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from .clinical_condition_models import (
    ClinicalCondition,
    ClinicalGuidelineDocument,
    DocumentType,
    UrgencyLevel,
)

logger = logging.getLogger(__name__)


class ChunkType(str, Enum):
    """Semantic chunk types."""
    TRIAGE_CRITERIA = "triage_criteria"
    CLASSIFICATION = "classification"
    PRESENTATION = "presentation"
    DIFFERENTIAL = "differential"
    INVESTIGATION = "investigation"
    TREATMENT_PRIMARY = "treatment_primary"
    TREATMENT_DISTRICT = "treatment_district"
    TREATMENT_TERTIARY = "treatment_tertiary"
    TREATMENT_ESCALATION = "treatment_escalation"
    COMORBIDITY_PATHWAY = "comorbidity_pathway"
    DRUG_FORMULARY = "drug_formulary"
    EMERGENCY_PROTOCOL = "emergency_protocol"
    FOLLOW_UP = "follow_up"
    PATIENT_EDUCATION = "patient_education"
    STEP_PROTOCOL = "step_protocol"
    DECISION_NODE = "decision_node"


@dataclass
class ClinicalChunk:
    """A semantic chunk extracted from a clinical condition."""
    chunk_type: ChunkType
    chunk_index: int
    content_json: Dict[str, Any]
    content_text: str

    # Triage-critical metadata
    urgency_default: Optional[str] = None
    has_emergency_triggers: bool = False
    has_red_flags: bool = False
    care_levels: List[str] = field(default_factory=list)

    # Comorbidity context
    comorbidity: Optional[str] = None

    # Numeric thresholds
    numeric_thresholds: Optional[Dict[str, Any]] = None

    # Drug context
    drug_classes: List[str] = field(default_factory=list)
    drug_names: List[str] = field(default_factory=list)
    contraindications: List[str] = field(default_factory=list)

    # Source tracking
    source_section: Optional[str] = None


class ClinicalChunkingService:
    """
    Extracts semantic chunks from clinical conditions.

    Usage:
        service = ClinicalChunkingService()
        chunks = service.chunk_condition(condition, document_type)
    """

    def __init__(self):
        """Initialize the chunking service."""
        pass

    def chunk_condition(
        self,
        condition: ClinicalCondition,
        document_type: DocumentType
    ) -> List[ClinicalChunk]:
        """
        Extract all semantic chunks from a clinical condition.

        Args:
            condition: Validated ClinicalCondition
            document_type: Type of source document

        Returns:
            List of ClinicalChunk objects
        """
        chunks = []

        # Always extract triage criteria
        chunks.extend(self._extract_triage_criteria(condition))

        # Classification (if present)
        if condition.classification:
            chunks.extend(self._extract_classification(condition))

        # Clinical presentation
        if condition.clinical_presentation or condition.when_to_suspect or condition.clinical_examination:
            chunks.extend(self._extract_presentation(condition))

        # Differential diagnosis
        if condition.differential_diagnosis:
            chunks.extend(self._extract_differential(condition))

        # Investigations
        if condition.investigations:
            chunks.extend(self._extract_investigations(condition))

        # Treatment by care level
        if condition.treatment_by_care_level:
            chunks.extend(self._extract_treatment_by_level(condition))
        elif condition.treatment_tiers:
            chunks.extend(self._extract_treatment_tiers(condition))

        # Comorbidity pathways
        if condition.comorbidity_pathways:
            chunks.extend(self._extract_comorbidity_pathways(condition))

        # Drug formulary
        if condition.drug_formulary:
            chunks.extend(self._extract_drug_formulary(condition))

        # Step-wise management
        if condition.step_wise_management:
            chunks.extend(self._extract_step_protocol(condition))

        # Emergency protocols
        if condition.emergency_protocols:
            chunks.extend(self._extract_emergency_protocols(condition))

        # Follow-up
        if condition.follow_up:
            chunks.extend(self._extract_follow_up(condition))

        # Patient education
        if condition.patient_education:
            chunks.extend(self._extract_patient_education(condition))

        logger.info(f"[CHUNKING] Extracted {len(chunks)} chunks from condition {condition.condition_id}")
        return chunks

    def _extract_triage_criteria(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract triage criteria chunk (red flags, emergency triggers)."""
        chunks = []
        triage = condition.triage_metadata

        # Build content
        content = {
            "condition_name": condition.name,
            "urgency_levels": [u.value for u in triage.urgency_levels],
            "default_urgency": triage.default_urgency.value,
        }

        text_parts = [f"Triage criteria for {condition.name}:"]
        text_parts.append(f"Default urgency: {triage.default_urgency.value}")

        # Emergency triggers
        if triage.emergency_triggers:
            triggers = []
            for t in triage.emergency_triggers:
                if isinstance(t, str):
                    triggers.append({"trigger": t})
                    text_parts.append(f"Emergency trigger: {t}")
                else:
                    triggers.append(t.model_dump() if hasattr(t, 'model_dump') else t)
                    text_parts.append(f"Emergency trigger: {t.trigger}")
                    if hasattr(t, 'symptoms') and t.symptoms:
                        text_parts.append(f"  Symptoms: {', '.join(t.symptoms)}")
            content["emergency_triggers"] = triggers

        # Red flags
        red_flags = []
        if triage.red_flags:
            for rf in triage.red_flags:
                if isinstance(rf, str):
                    red_flags.append({"flag": rf})
                    text_parts.append(f"Red flag: {rf}")
                else:
                    red_flags.append(rf.model_dump() if hasattr(rf, 'model_dump') else rf)
                    text_parts.append(f"Red flag: {rf.flag}")
                    if hasattr(rf, 'action') and rf.action:
                        text_parts.append(f"  Action: {rf.action}")

        if triage.red_flags_for_referral:
            for rf in triage.red_flags_for_referral:
                red_flags.append(rf.model_dump() if hasattr(rf, 'model_dump') else rf)
                text_parts.append(f"Red flag for referral: {rf.flag}")
                if rf.action:
                    text_parts.append(f"  Action: {rf.action}")

        if red_flags:
            content["red_flags"] = red_flags

        # Referral triggers
        if triage.referral_triggers:
            content["referral_triggers"] = [
                rt.model_dump() if hasattr(rt, 'model_dump') else rt
                for rt in triage.referral_triggers
            ]
            for rt in triage.referral_triggers:
                text_parts.append(f"Referral: {rt.condition} -> {rt.refer_to}")

        chunks.append(ClinicalChunk(
            chunk_type=ChunkType.TRIAGE_CRITERIA,
            chunk_index=0,
            content_json=content,
            content_text="\n".join(text_parts),
            urgency_default=triage.default_urgency.value,
            has_emergency_triggers=bool(triage.emergency_triggers),
            has_red_flags=bool(red_flags),
            source_section="triage_metadata",
        ))

        return chunks

    def _extract_classification(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract classification/grading chunk."""
        chunks = []
        classification = condition.classification

        content = {
            "condition_name": condition.name,
            "classification_type": classification.type,
            "grades": [],
        }

        text_parts = [f"Classification for {condition.name}:"]
        text_parts.append(f"Type: {classification.type}")

        numeric_thresholds = {}

        for grade in classification.grades:
            grade_data = {
                "grade": grade.grade,
                "criteria": grade.criteria.model_dump() if hasattr(grade.criteria, 'model_dump') else grade.criteria,
            }
            if grade.default_urgency:
                grade_data["default_urgency"] = grade.default_urgency.value

            content["grades"].append(grade_data)

            # Build text
            text_parts.append(f"\n{grade.grade}:")
            criteria = grade.criteria
            if criteria.sbp_range:
                text_parts.append(f"  SBP: {criteria.sbp_range[0]}-{criteria.sbp_range[1]} mmHg")
            if criteria.dbp_range:
                text_parts.append(f"  DBP: {criteria.dbp_range[0]}-{criteria.dbp_range[1]} mmHg")
            if criteria.sbp_min:
                text_parts.append(f"  SBP >= {criteria.sbp_min} mmHg")
                numeric_thresholds["sbp_min"] = criteria.sbp_min
            if criteria.dbp_min:
                text_parts.append(f"  DBP >= {criteria.dbp_min} mmHg")
                numeric_thresholds["dbp_min"] = criteria.dbp_min
            if grade.default_urgency:
                text_parts.append(f"  Urgency: {grade.default_urgency.value}")

        # Determine urgency from highest grade
        highest_urgency = None
        for grade in classification.grades:
            if grade.default_urgency:
                if grade.default_urgency == UrgencyLevel.EMERGENCY:
                    highest_urgency = "emergency"
                elif grade.default_urgency == UrgencyLevel.URGENT and highest_urgency != "emergency":
                    highest_urgency = "urgent"

        chunks.append(ClinicalChunk(
            chunk_type=ChunkType.CLASSIFICATION,
            chunk_index=0,
            content_json=content,
            content_text="\n".join(text_parts),
            urgency_default=highest_urgency,
            has_emergency_triggers="emergency" in [g.default_urgency.value for g in classification.grades if g.default_urgency],
            numeric_thresholds=numeric_thresholds if numeric_thresholds else None,
            source_section="classification",
        ))

        return chunks

    def _extract_presentation(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract clinical presentation chunk."""
        chunks = []

        content = {"condition_name": condition.name}
        text_parts = [f"Clinical presentation of {condition.name}:"]

        # From clinical_presentation
        if condition.clinical_presentation:
            pres = condition.clinical_presentation

            if pres.symptoms:
                symptoms = []
                for s in pres.symptoms:
                    if isinstance(s, str):
                        symptoms.append({"symptom": s})
                        text_parts.append(f"Symptom: {s}")
                    else:
                        symptoms.append(s.model_dump() if hasattr(s, 'model_dump') else s)
                        freq = f" ({s.frequency.value})" if hasattr(s, 'frequency') and s.frequency else ""
                        note = f" - {s.note}" if hasattr(s, 'note') and s.note else ""
                        text_parts.append(f"Symptom: {s.symptom}{freq}{note}")
                content["symptoms"] = symptoms

            if pres.examination_findings:
                content["examination_findings"] = pres.examination_findings
                for finding in pres.examination_findings:
                    text_parts.append(f"Examination: {finding}")

            if pres.when_to_suspect:
                content["when_to_suspect"] = pres.when_to_suspect
                text_parts.append(f"When to suspect: {pres.when_to_suspect}")

        # From when_to_suspect (visual workflow format)
        if condition.when_to_suspect:
            content["when_to_suspect_details"] = condition.when_to_suspect
            if "description" in condition.when_to_suspect:
                text_parts.append(f"Description: {condition.when_to_suspect['description']}")
            if "diagnostic_criteria" in condition.when_to_suspect:
                text_parts.append(f"Diagnostic criteria: {condition.when_to_suspect['diagnostic_criteria']}")

        # Clinical pearls
        if condition.clinical_pearls:
            content["clinical_pearls"] = condition.clinical_pearls
            for pearl in condition.clinical_pearls:
                text_parts.append(f"Clinical pearl: {pearl}")

        # Clinical examination (visual workflow)
        if condition.clinical_examination:
            content["clinical_examination"] = condition.clinical_examination
            if "preliminary" in condition.clinical_examination:
                for item in condition.clinical_examination["preliminary"]:
                    text_parts.append(f"Examination: {item}")

        chunks.append(ClinicalChunk(
            chunk_type=ChunkType.PRESENTATION,
            chunk_index=0,
            content_json=content,
            content_text="\n".join(text_parts),
            source_section="clinical_presentation",
        ))

        return chunks

    def _extract_differential(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract differential diagnosis chunk."""
        chunks = []

        content = {
            "condition_name": condition.name,
            "differentials": [],
        }
        text_parts = [f"Differential diagnosis for {condition.name}:"]

        for ddx in condition.differential_diagnosis:
            if isinstance(ddx, str):
                content["differentials"].append({"condition": ddx})
                text_parts.append(f"- {ddx}")
            else:
                ddx_data = ddx.model_dump() if hasattr(ddx, 'model_dump') else ddx
                content["differentials"].append(ddx_data)
                text_parts.append(f"- {ddx.condition}")
                if hasattr(ddx, 'distinguishing_feature') and ddx.distinguishing_feature:
                    text_parts.append(f"  Distinguishing: {ddx.distinguishing_feature}")
                if hasattr(ddx, 'causes') and ddx.causes:
                    text_parts.append(f"  Causes: {', '.join(ddx.causes)}")

        chunks.append(ClinicalChunk(
            chunk_type=ChunkType.DIFFERENTIAL,
            chunk_index=0,
            content_json=content,
            content_text="\n".join(text_parts),
            source_section="differential_diagnosis",
        ))

        return chunks

    def _extract_investigations(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract investigations chunk."""
        chunks = []
        inv = condition.investigations

        content = {"condition_name": condition.name}
        text_parts = [f"Investigations for {condition.name}:"]

        def process_tests(tests, tier_name):
            result = []
            for t in tests:
                if isinstance(t, str):
                    result.append({"test": t})
                    text_parts.append(f"{tier_name}: {t}")
                else:
                    t_data = t.model_dump() if hasattr(t, 'model_dump') else t
                    result.append(t_data)
                    text_parts.append(f"{tier_name}: {t.test}")
                    if hasattr(t, 'abnormal') and t.abnormal:
                        text_parts.append(f"  Abnormal: {t.abnormal}")
            return result

        # Handle different formats
        if inv.baseline:
            content["baseline"] = process_tests(inv.baseline, "Baseline")
        if inv.confirmatory:
            content["confirmatory"] = process_tests(inv.confirmatory, "Confirmatory")
        if inv.advanced:
            content["advanced"] = process_tests(inv.advanced, "Advanced")

        # Alternative format (essential/desirable/comprehensive)
        if inv.essential:
            tier = inv.essential
            if tier.description:
                text_parts.append(f"\nEssential ({tier.description}):")
            content["essential"] = process_tests(tier.tests, "Essential")

        if inv.desirable:
            if isinstance(inv.desirable, dict):
                if "tests" in inv.desirable:
                    content["desirable"] = process_tests(inv.desirable["tests"], "Desirable")
            else:
                tier = inv.desirable
                if tier.description:
                    text_parts.append(f"\nDesirable ({tier.description}):")
                content["desirable"] = process_tests(tier.tests, "Desirable")

        if inv.comprehensive:
            tier = inv.comprehensive
            if tier.description:
                text_parts.append(f"\nComprehensive ({tier.description}):")
            content["comprehensive"] = process_tests(tier.tests, "Comprehensive")

        # Simple format
        if inv.tests:
            content["tests"] = process_tests(inv.tests, "Test")

        chunks.append(ClinicalChunk(
            chunk_type=ChunkType.INVESTIGATION,
            chunk_index=0,
            content_json=content,
            content_text="\n".join(text_parts),
            source_section="investigations",
        ))

        return chunks

    def _extract_treatment_by_level(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract treatment chunks by care level."""
        chunks = []
        treatment = condition.treatment_by_care_level

        # PHC/Primary treatment
        if treatment.phc_primary:
            phc = treatment.phc_primary
            content = {"condition_name": condition.name, "care_level": "phc"}
            text_parts = [f"PHC treatment for {condition.name}:"]
            drug_names = []
            drug_classes = []

            if phc.lifestyle_modifications:
                content["lifestyle_modifications"] = []
                for lm in phc.lifestyle_modifications:
                    if isinstance(lm, str):
                        content["lifestyle_modifications"].append({"intervention": lm})
                        text_parts.append(f"Lifestyle: {lm}")
                    else:
                        content["lifestyle_modifications"].append(lm)
                        text_parts.append(f"Lifestyle: {lm.get('intervention', lm)}")

            if phc.drug_therapy:
                content["drug_therapy"] = phc.drug_therapy
                if "first_line" in phc.drug_therapy:
                    for drug in phc.drug_therapy["first_line"]:
                        text_parts.append(f"First-line drug: {drug}")
                        drug_names.append(drug.split('(')[0].strip().lower())

            if phc.medications:
                content["medications"] = [m.model_dump() if hasattr(m, 'model_dump') else m for m in phc.medications]
                for med in phc.medications:
                    drug_name = med.drug if hasattr(med, 'drug') and med.drug else (med.representative if hasattr(med, 'representative') else "")
                    if drug_name:
                        text_parts.append(f"Medication: {drug_name}")
                        drug_names.append(drug_name.lower())

            if phc.conservative:
                content["conservative"] = phc.conservative
                for item in phc.conservative:
                    text_parts.append(f"Conservative: {item}")

            if phc.medical:
                content["medical"] = phc.medical
                for item in phc.medical:
                    text_parts.append(f"Medical: {item}")

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.TREATMENT_PRIMARY,
                chunk_index=0,
                content_json=content,
                content_text="\n".join(text_parts),
                care_levels=["phc"],
                drug_names=drug_names,
                drug_classes=drug_classes,
                source_section="treatment_by_care_level.phc_primary",
            ))

        # District hospital treatment
        if treatment.district_hospital:
            dist = treatment.district_hospital
            content = {"condition_name": condition.name, "care_level": "district"}
            text_parts = [f"District hospital treatment for {condition.name}:"]

            if dist.additional_capabilities:
                content["additional_capabilities"] = dist.additional_capabilities
                for cap in dist.additional_capabilities:
                    text_parts.append(f"Capability: {cap}")

            if dist.surgical_indications:
                content["surgical_indications"] = dist.surgical_indications
                for ind in dist.surgical_indications:
                    text_parts.append(f"Surgical indication: {ind}")

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.TREATMENT_DISTRICT,
                chunk_index=0,
                content_json=content,
                content_text="\n".join(text_parts),
                care_levels=["district"],
                source_section="treatment_by_care_level.district_hospital",
            ))

        # Tertiary treatment
        tertiary = treatment.tertiary_medical_college or treatment.tertiary
        if tertiary:
            content = {"condition_name": condition.name, "care_level": "tertiary"}
            text_parts = [f"Tertiary treatment for {condition.name}:"]

            if tertiary.referral_indications:
                content["referral_indications"] = tertiary.referral_indications
                for ind in tertiary.referral_indications:
                    text_parts.append(f"Referral indication: {ind}")

            if tertiary.additional_capabilities:
                content["additional_capabilities"] = tertiary.additional_capabilities
                for cap in tertiary.additional_capabilities:
                    text_parts.append(f"Capability: {cap}")

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.TREATMENT_TERTIARY,
                chunk_index=0,
                content_json=content,
                content_text="\n".join(text_parts),
                care_levels=["tertiary"],
                source_section="treatment_by_care_level.tertiary",
            ))

        return chunks

    def _extract_treatment_tiers(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract treatment from alternative tier format (ObGyn style)."""
        chunks = []
        tiers = condition.treatment_tiers

        if "secondary_hospital" in tiers:
            secondary = tiers["secondary_hospital"]
            content = {"condition_name": condition.name, "care_level": "secondary"}
            text_parts = [f"Secondary hospital treatment for {condition.name}:"]

            for category in ["conservative", "medical", "surgical"]:
                if category in secondary:
                    content[category] = secondary[category]
                    for item in secondary[category]:
                        text_parts.append(f"{category.title()}: {item}")

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.TREATMENT_PRIMARY,
                chunk_index=0,
                content_json=content,
                content_text="\n".join(text_parts),
                care_levels=["district"],  # Map secondary to district
                source_section="treatment_tiers.secondary_hospital",
            ))

        if "tertiary_hospital" in tiers:
            tertiary = tiers["tertiary_hospital"]
            content = {"condition_name": condition.name, "care_level": "tertiary"}
            text_parts = [f"Tertiary hospital treatment for {condition.name}:"]

            if "additional_options" in tertiary:
                content["additional_options"] = tertiary["additional_options"]
                for opt in tertiary["additional_options"]:
                    text_parts.append(f"Option: {opt}")

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.TREATMENT_TERTIARY,
                chunk_index=0,
                content_json=content,
                content_text="\n".join(text_parts),
                care_levels=["tertiary"],
                source_section="treatment_tiers.tertiary_hospital",
            ))

        return chunks

    def _extract_comorbidity_pathways(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract comorbidity pathway chunks (one per comorbidity)."""
        chunks = []

        for idx, pathway in enumerate(condition.comorbidity_pathways):
            content = {
                "condition_name": condition.name,
                "comorbidity": pathway.comorbidity,
                "preferred_drugs": pathway.preferred_drugs,
                "avoid": pathway.avoid,
            }

            text_parts = [f"Comorbidity pathway: {condition.name} with {pathway.comorbidity}"]
            text_parts.append(f"Preferred drugs: {', '.join(pathway.preferred_drugs)}")

            if pathway.avoid:
                content["avoid"] = pathway.avoid
                text_parts.append(f"Avoid: {', '.join(pathway.avoid)}")

            if pathway.target_bp:
                content["target_bp"] = pathway.target_bp
                text_parts.append(f"Target BP: {pathway.target_bp}")

            if pathway.special_notes:
                content["special_notes"] = pathway.special_notes
                text_parts.append(f"Note: {pathway.special_notes}")

            # Extract drug classes and names
            drug_classes = []
            drug_names = []
            for drug in pathway.preferred_drugs:
                # Extract class from parentheses: "ACE inhibitor (enalapril)"
                if "(" in drug:
                    parts = drug.split("(")
                    drug_classes.append(parts[0].strip().lower().replace(" ", "_"))
                    drug_names.append(parts[1].replace(")", "").strip().lower())
                else:
                    drug_names.append(drug.lower())

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.COMORBIDITY_PATHWAY,
                chunk_index=idx,
                content_json=content,
                content_text="\n".join(text_parts),
                comorbidity=pathway.comorbidity,
                drug_classes=drug_classes,
                drug_names=drug_names,
                contraindications=[a.lower() for a in pathway.avoid] if pathway.avoid else [],
                source_section=f"comorbidity_pathways[{idx}]",
            ))

        return chunks

    def _extract_drug_formulary(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract drug formulary chunks (one per drug class)."""
        chunks = []

        for idx, drug in enumerate(condition.drug_formulary):
            drug_class = drug.drug_class or "unknown"
            drug_name = drug.representative or drug.drug or "unknown"

            content = {
                "condition_name": condition.name,
                "drug_class": drug_class,
                "drug_name": drug_name,
            }

            text_parts = [f"Drug formulary: {drug_class} ({drug_name})"]

            if drug.initial_dose:
                content["initial_dose"] = drug.initial_dose
                text_parts.append(f"Initial dose: {drug.initial_dose}")

            if drug.max_dose:
                content["max_dose"] = drug.max_dose
                text_parts.append(f"Max dose: {drug.max_dose}")

            if drug.side_effects:
                content["side_effects"] = drug.side_effects
                text_parts.append(f"Side effects: {', '.join(drug.side_effects)}")

            if drug.contraindications:
                content["contraindications"] = drug.contraindications
                text_parts.append(f"Contraindications: {', '.join(drug.contraindications)}")

            if drug.monitoring:
                content["monitoring"] = drug.monitoring
                text_parts.append(f"Monitoring: {drug.monitoring}")

            if drug.pregnancy_category:
                content["pregnancy_category"] = drug.pregnancy_category
                text_parts.append(f"Pregnancy category: {drug.pregnancy_category}")

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.DRUG_FORMULARY,
                chunk_index=idx,
                content_json=content,
                content_text="\n".join(text_parts),
                drug_classes=[drug_class.lower().replace(" ", "_")] if drug_class else [],
                drug_names=[drug_name.lower()] if drug_name else [],
                contraindications=[c.lower() for c in drug.contraindications] if drug.contraindications else [],
                source_section=f"drug_formulary[{idx}]",
            ))

        return chunks

    def _extract_step_protocol(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract step-wise management protocol chunk."""
        chunks = []
        protocol = condition.step_wise_management

        content = {
            "condition_name": condition.name,
            "description": protocol.description,
            "steps": [],
        }

        text_parts = [f"Step-wise management for {condition.name}:"]
        if protocol.description:
            text_parts.append(protocol.description)

        for step in protocol.steps:
            step_data = {
                "step": step.step,
                "description": step.description,
                "action": step.action,
            }

            if step.options:
                step_data["options"] = step.options
            if step.methods:
                step_data["methods"] = step.methods

            content["steps"].append(step_data)

            text_parts.append(f"\nStep {step.step}: {step.description or step.action}")
            if step.options:
                text_parts.append(f"  Options: {', '.join(step.options)}")
            if step.methods:
                for method in step.methods:
                    text_parts.append(f"  - {method}")

        chunks.append(ClinicalChunk(
            chunk_type=ChunkType.STEP_PROTOCOL,
            chunk_index=0,
            content_json=content,
            content_text="\n".join(text_parts),
            source_section="step_wise_management",
        ))

        return chunks

    def _extract_emergency_protocols(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract emergency protocol chunks."""
        chunks = []
        protocols = condition.emergency_protocols
        idx = 0

        # Hypertensive emergency
        if protocols.hypertensive_emergency:
            proto = protocols.hypertensive_emergency
            content = {
                "condition_name": condition.name,
                "protocol_type": "hypertensive_emergency",
                "definition": proto.definition,
                "target": proto.target,
            }

            text_parts = [f"Emergency protocol: Hypertensive emergency"]
            if proto.definition:
                text_parts.append(f"Definition: {proto.definition}")
            if proto.target:
                text_parts.append(f"Target: {proto.target}")

            drug_names = []
            if proto.drugs:
                content["drugs"] = [d.model_dump() if hasattr(d, 'model_dump') else d for d in proto.drugs]
                for drug in proto.drugs:
                    text_parts.append(f"Drug: {drug.drug} - {drug.dose}")
                    drug_names.append(drug.drug.lower().replace("iv ", ""))

            if proto.avoid:
                content["avoid"] = proto.avoid
                text_parts.append(f"Avoid: {proto.avoid}")

            # Extract numeric threshold from definition
            numeric_thresholds = {}
            if proto.definition and "180" in proto.definition:
                numeric_thresholds["sbp_min"] = 180
            if proto.definition and "110" in proto.definition:
                numeric_thresholds["dbp_min"] = 110

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.EMERGENCY_PROTOCOL,
                chunk_index=idx,
                content_json=content,
                content_text="\n".join(text_parts),
                urgency_default="emergency",
                has_emergency_triggers=True,
                numeric_thresholds=numeric_thresholds if numeric_thresholds else None,
                drug_names=drug_names,
                source_section="emergency_protocols.hypertensive_emergency",
            ))
            idx += 1

        # Hypertensive urgency
        if protocols.hypertensive_urgency:
            proto = protocols.hypertensive_urgency
            content = {
                "condition_name": condition.name,
                "protocol_type": "hypertensive_urgency",
                "definition": proto.definition,
                "management": proto.management,
            }

            text_parts = [f"Emergency protocol: Hypertensive urgency"]
            if proto.definition:
                text_parts.append(f"Definition: {proto.definition}")
            if proto.management:
                text_parts.append(f"Management: {proto.management}")

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.EMERGENCY_PROTOCOL,
                chunk_index=idx,
                content_json=content,
                content_text="\n".join(text_parts),
                urgency_default="urgent",
                source_section="emergency_protocols.hypertensive_urgency",
            ))
            idx += 1

        # Stroke-specific
        if protocols.stroke_specific:
            stroke = protocols.stroke_specific
            content = {
                "condition_name": condition.name,
                "protocol_type": "stroke_specific",
            }
            text_parts = [f"Stroke-specific protocol for {condition.name}:"]

            if stroke.ischemic_stroke:
                content["ischemic_stroke"] = stroke.ischemic_stroke
                text_parts.append("Ischemic stroke:")
                for key, val in stroke.ischemic_stroke.items():
                    text_parts.append(f"  {key}: {val}")

            if stroke.hemorrhagic_stroke:
                content["hemorrhagic_stroke"] = stroke.hemorrhagic_stroke
                text_parts.append("Hemorrhagic stroke:")
                for key, val in stroke.hemorrhagic_stroke.items():
                    text_parts.append(f"  {key}: {val}")

            chunks.append(ClinicalChunk(
                chunk_type=ChunkType.EMERGENCY_PROTOCOL,
                chunk_index=idx,
                content_json=content,
                content_text="\n".join(text_parts),
                urgency_default="emergency",
                has_emergency_triggers=True,
                source_section="emergency_protocols.stroke_specific",
            ))

        return chunks

    def _extract_follow_up(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract follow-up chunk."""
        chunks = []
        follow_up = condition.follow_up

        content = {"condition_name": condition.name}
        text_parts = [f"Follow-up for {condition.name}:"]

        if follow_up.frequency:
            content["frequency"] = follow_up.frequency
            for key, val in follow_up.frequency.items():
                text_parts.append(f"{key}: {val}")

        if follow_up.annual_review_components:
            content["annual_review_components"] = follow_up.annual_review_components
            text_parts.append("Annual review:")
            for comp in follow_up.annual_review_components:
                text_parts.append(f"  - {comp}")

        if follow_up.quality_metrics:
            content["quality_metrics"] = follow_up.quality_metrics
            text_parts.append("Quality metrics:")
            for metric in follow_up.quality_metrics:
                text_parts.append(f"  - {metric}")

        if follow_up.interventions:
            content["interventions"] = follow_up.interventions
            for intervention in follow_up.interventions:
                text_parts.append(f"Intervention: {intervention}")

        chunks.append(ClinicalChunk(
            chunk_type=ChunkType.FOLLOW_UP,
            chunk_index=0,
            content_json=content,
            content_text="\n".join(text_parts),
            source_section="follow_up",
        ))

        return chunks

    def _extract_patient_education(self, condition: ClinicalCondition) -> List[ClinicalChunk]:
        """Extract patient education chunk."""
        chunks = []
        edu = condition.patient_education

        content = {"condition_name": condition.name}
        text_parts = [f"Patient education for {condition.name}:"]

        if edu.key_messages:
            content["key_messages"] = edu.key_messages
            for msg in edu.key_messages:
                text_parts.append(f"- {msg}")

        if edu.self_monitoring:
            content["self_monitoring"] = edu.self_monitoring
            text_parts.append("Self-monitoring:")
            for key, val in edu.self_monitoring.items():
                text_parts.append(f"  {key}: {val}")

        chunks.append(ClinicalChunk(
            chunk_type=ChunkType.PATIENT_EDUCATION,
            chunk_index=0,
            content_json=content,
            content_text="\n".join(text_parts),
            source_section="patient_education",
        ))

        return chunks


# Singleton instance
_chunking_service = None


def get_clinical_chunking_service() -> ClinicalChunkingService:
    """Get singleton ClinicalChunkingService instance."""
    global _chunking_service
    if _chunking_service is None:
        _chunking_service = ClinicalChunkingService()
    return _chunking_service

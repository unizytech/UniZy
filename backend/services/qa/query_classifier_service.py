"""
Query Classifier Service

Uses Gemini Flash to classify user queries into:
- SEMANTIC: Pattern detection, insights -> Narrative synthesis
- HYBRID: Search with filters -> Patient table
- SQL: Analytics, counts -> Charts/stats

Also extracts:
- Relevant segment codes for filtering
- Date/filter parameters
- Rephrased semantic query for embedding
"""

import json
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

from models.qa_models import (
    ClassifiedQuery,
    QueryIntent,
    SearchLevel,
    ResponseFormat,
    TemporalReference,
    TemporalReferenceType,
    QAPriorContext
)

logger = logging.getLogger(__name__)

# ============================================================================
# Segment Code Normalization
# ============================================================================
# Maps canonical codes to all stored variants in segment_embeddings table.
# Based on actual DB data (queried 2026-03-24). Different templates use different
# segment codes for similar content, so we group all related codes together.
SEGMENT_CODE_VARIANTS = {
    "chiefComplaints": ["chiefComplaints", "chief_complaints", "complaints"],
    "diagnosis": ["diagnosis"],
    "prescription": ["prescription", "medications", "medicines", "currentTreatment"],
    "investigations": ["investigations", "investigation", "otherInvestigations",
                        "dischargeBloodInvestigations", "labResults", "orderedLabs"],
    "vitals": ["vitals"],
    "examination": ["examination", "generalExamination", "systemicExamination",
                     "dischargeExamination", "mentalStatusExamination",
                     "slitLampExamination", "fundusExamination",
                     "summaryOfExamination", "initialExaminationSummary"],
    "historyOfPresentIllness": ["historyOfPresentIllness", "history",
                                 "clinicalHistory", "extendedHistory"],
    "medicalHistory": ["medicalHistory", "generalHistory", "obstetricHistory",
                        "pastOcularHistory"],
    "treatmentPlan": ["treatmentPlan", "treatmentDetails", "treatmentSummary",
                       "managementPlan", "plan"],
    "followUp": ["followUp", "follow_up", "adviceAndFollowUp",
                  "nextFollowupDetails", "planForFollowup"],
    "referralDetails": ["referralDetails", "referralInformation",
                         "referralReason", "referredBy"],
    "patientInformation": ["patientInformation", "patientDemographics"],
    "emergencyContact": ["emergencyContact"],
    "allergy": ["allergy", "allergies"],
    "summary": ["summary", "visitSummary"],
    "clinicalNotes": ["clinicalNotes", "doctorNotes", "notes"],
    "hospitalCourse": ["hospitalCourse"],
    "admission": ["admission", "admissionDetails"],
    "discharge": ["discharge", "dischargeCondition"],
    "procedures": ["procedures", "procedureNotes"],
    "immunization": ["immunization"],
}

# Maps any alias (SCREAMING_SNAKE, loose names, LLM outputs) to canonical key
SEGMENT_CODE_ALIASES = {
    # SCREAMING_SNAKE → canonical
    "CHIEF_COMPLAINT": "chiefComplaints",
    "CHIEF_COMPLAINTS": "chiefComplaints",
    "DIAGNOSIS": "diagnosis",
    "VITAL_SIGNS": "vitals",
    "VITALS": "vitals",
    "PRESCRIPTION": "prescription",
    "INVESTIGATIONS": "investigations",
    "PHYSICAL_EXAMINATION": "examination",
    "EXAMINATION": "examination",
    "HISTORY_OF_PRESENT_ILLNESS": "historyOfPresentIllness",
    "PAST_MEDICAL_HISTORY": "medicalHistory",
    "MEDICAL_HISTORY": "medicalHistory",
    "TREATMENT_PLAN": "treatmentPlan",
    "FOLLOW_UP": "followUp",
    "REFERRAL": "referralDetails",
    "PATIENT_INFORMATION": "patientInformation",
    "EMERGENCY_CONTACT": "emergencyContact",
    "ALLERGY": "allergy",
    "SUMMARY": "summary",
    "PROCEDURES": "procedures",
    "IMMUNIZATION": "immunization",
    "HOSPITAL_COURSE": "hospitalCourse",
    "CLINICAL_NOTES": "clinicalNotes",
    "ADMISSION": "admission",
    "DISCHARGE": "discharge",
    "DISCHARGE_CONDITION": "discharge",
    # Loose aliases from LLM classifier output
    "vitalSigns": "vitals",
    "physicalExamination": "examination",
    "pastMedicalHistory": "medicalHistory",
    "referral": "referralDetails",
    "medication": "prescription",
    "medicine": "prescription",
    "history": "historyOfPresentIllness",
    "follow_up": "followUp",
    "chief_complaints": "chiefComplaints",
    "complaints": "chiefComplaints",
    "lab": "investigations",
    "labs": "investigations",
    "test": "investigations",
    "tests": "investigations",
    "notes": "clinicalNotes",
    "admission": "admission",
    "discharge": "discharge",
}


def normalize_segment_codes(raw_codes: List[str]) -> List[str]:
    """Expand classifier segment codes into all stored camelCase variants."""
    expanded = set()
    for code in raw_codes:
        # Resolve alias to canonical, or use code as-is if already canonical
        canonical = SEGMENT_CODE_ALIASES.get(code, code)
        # Get all stored variants for this canonical code
        variants = SEGMENT_CODE_VARIANTS.get(canonical, [canonical])
        expanded.update(variants)
    logger.debug(f"Expanded segment codes: {raw_codes} -> {list(expanded)}")
    return list(expanded)

# Classification prompt for Gemini
CLASSIFICATION_SYSTEM_PROMPT = """You are a medical query classifier. Analyze user queries about medical consultations and extractions.

NOTE: The query has already been preprocessed (abbreviations expanded, typos fixed, terms normalized).
Your job is ONLY to classify the query - do NOT rephrase or modify it.

Classify each query into one of three intents:
1. SEMANTIC - Questions about patterns, insights, clinical observations
   Example: "What are common comorbidities in diabetic patients?"
   Response format: narrative (natural language summary)

2. HYBRID - Search queries that need specific patient/extraction results
   Example: "Show me patients with hypertension from last month"
   Response format: table (list of patients/extractions)

3. SQL - Analytics and counting queries
   Example: "How many extractions were done this week?"
   Response format: chart or stat_card

IMPORTANT - search_level decision:
- Use "segment" when the query focuses on a SPECIFIC type of medical data:
  * Medications/prescriptions → segment_codes: ["prescription"]
  * Diagnoses → segment_codes: ["diagnosis"]
  * Chief complaints → segment_codes: ["chiefComplaints"]
  * Investigations/labs → segment_codes: ["investigations"]
  * Vital signs → segment_codes: ["vitals"]
  * History of present illness → segment_codes: ["historyOfPresentIllness"]
  * Past medical history → segment_codes: ["medicalHistory"]
  * Treatment plans → segment_codes: ["treatmentPlan"]
  * Follow-up instructions → segment_codes: ["followUp"]
  * Examinations → segment_codes: ["examination"]
  * Referrals → segment_codes: ["referralDetails"]
  * Allergies → segment_codes: ["allergy"]
  * Summaries → segment_codes: ["summary"]

- Use "document" when the query needs broader context:
  * Patient overview questions
  * Questions spanning multiple segments
  * General consultation content

TEMPORAL REFERENCES - Extract any time-based references:
- relative_visit: "last visit", "previous consultation", "second to last visit"
- absolute_date: "January 15th", "2024-01-15", "last Tuesday"
- relative_time: "last week", "3 months ago", "yesterday"
- visit_number: "first visit", "visit 3", "initial consultation"
- comparison: "compare with previous", "changes since last time"

Set requires_patient_history=true when query needs patient's visit history.
Set comparison_mode=true when comparing visits or tracking changes.

Examples:
- "What medications are prescribed?" → search_level: "segment", segment_codes: ["prescription"]
- "Common diagnoses in diabetic patients" → search_level: "segment", segment_codes: ["diagnosis"]
- "What are the chief complaints?" → search_level: "segment", segment_codes: ["chiefComplaints"]
- "Show vital signs" → search_level: "segment", segment_codes: ["vitals"]
- "Any allergies?" → search_level: "segment", segment_codes: ["allergy"]
- "What referrals were made?" → search_level: "segment", segment_codes: ["referralDetails"]
- "Show patient history" → search_level: "document"
- "What changed since last visit?" → comparison_mode: true, temporal_references: [{"type": "relative_visit", "raw_text": "last visit", "visit_offset": -1}]
- "Compare diagnoses with previous consultation" → comparison_mode: true, requires_patient_history: true
- "What was prescribed on January 15th?" → temporal_references: [{"type": "absolute_date", "raw_text": "January 15th"}]
- "Has blood pressure improved since first visit?" → comparison_mode: true, temporal_references: [{"type": "visit_number", "raw_text": "first visit", "visit_offset": 1}]

Respond with a valid JSON object only, no markdown."""

CLASSIFICATION_USER_PROMPT = """Classify this query:
"{query}"

Respond with JSON in this exact format:
{{
  "intent": "SEMANTIC" | "HYBRID" | "SQL",
  "search_level": "document" | "segment",
  "response_format": "narrative" | "table" | "chart" | "stat_card",
  "segment_codes": ["CODE1", "CODE2"] or null,
  "filters": {{
    "date_from": "YYYY-MM-DD" or null,
    "date_to": "YYYY-MM-DD" or null,
    "patient_name": "string" or null,
    "doctor_name": "string" or null,
    "diagnosis": "string" or null
  }},
  "temporal_references": [
    {{
      "type": "relative_visit" | "absolute_date" | "relative_time" | "visit_number" | "comparison",
      "raw_text": "exact text from query",
      "visit_offset": integer or null
    }}
  ] or null,
  "requires_patient_history": true | false,
  "comparison_mode": true | false,
  "confidence": 0.0-1.0
}}"""


class QueryClassifierService:
    """
    Classifies user queries to determine the appropriate search strategy.

    Usage:
        service = QueryClassifierService()

        classified = await service.classify(
            query="What are the most common diagnoses in elderly patients?",
            hospital_id=hospital_uuid
        )

        print(classified.intent)  # QueryIntent.SEMANTIC
        print(classified.response_format)  # ResponseFormat.NARRATIVE
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy load Gemini client"""
        if self._client is None:
            from services.gemini_client_factory import get_gemini_client
            self._client = get_gemini_client()
        return self._client

    async def classify(
        self,
        query: str,
        hospital_id: Optional[UUID] = None,
        prior_context: Optional[QAPriorContext] = None
    ) -> ClassifiedQuery:
        """
        Classify a user query to determine search strategy.

        Args:
            query: The user's natural language query
            hospital_id: Optional hospital context
            prior_context: Previous Q&A exchange for follow-up classification

        Returns:
            ClassifiedQuery with intent, search level, and extracted parameters
        """
        try:
            client = self._get_client()

            user_prompt = CLASSIFICATION_USER_PROMPT.format(query=query)

            # Inject prior context for follow-up query classification
            if prior_context:
                context_block = '\n\nPrevious query context:'
                context_block += f'\n- Previous query: {prior_context.query}'
                if prior_context.intent:
                    context_block += f'\n- Previous intent: {prior_context.intent}'
                context_block += '\nConsider this context when classifying the current query. Follow-up questions about a specific visit should typically be SEMANTIC with narrative format.'
                user_prompt += context_block

            # Use Gemini Flash for quick classification
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {"role": "user", "parts": [{"text": CLASSIFICATION_SYSTEM_PROMPT}]},
                    {"role": "model", "parts": [{"text": "I understand. I'll classify queries and respond with JSON only."}]},
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 500,
                }
            )

            # Parse response
            response_text = response.text.strip()

            # Clean markdown if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # Map string values to enums (enum values are lowercase)
            intent = QueryIntent(result.get("intent", "semantic").lower())
            search_level = SearchLevel(result.get("search_level", "document").lower())
            response_format = ResponseFormat(result.get("response_format", "narrative").lower())

            # Parse temporal references
            temporal_refs = None
            raw_temporal = result.get("temporal_references")
            if raw_temporal:
                temporal_refs = []
                for ref in raw_temporal:
                    try:
                        ref_type = TemporalReferenceType(ref.get("type", "relative_visit"))
                        temporal_refs.append(TemporalReference(
                            type=ref_type,
                            raw_text=ref.get("raw_text", ""),
                            visit_offset=ref.get("visit_offset")
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to parse temporal reference: {ref}, error: {e}")

            return ClassifiedQuery(
                original_query=query,
                intent=intent,
                search_level=search_level,
                response_format=response_format,
                segment_codes=result.get("segment_codes"),
                filters=result.get("filters"),
                confidence=float(result.get("confidence", 0.8)),
                temporal_references=temporal_refs,
                requires_patient_history=result.get("requires_patient_history", False),
                comparison_mode=result.get("comparison_mode", False)
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse classification response: {e}")
            return self._fallback_classification(query)
        except Exception as e:
            logger.error(f"Query classification failed: {e}", exc_info=True)
            return self._fallback_classification(query)

    def _fallback_classification(self, query: str) -> ClassifiedQuery:
        """Fallback classification using keyword matching"""
        query_lower = query.lower()

        # Detect segment codes for potential segment-level search
        detected_segments = self._detect_segment_codes(query)

        # SQL indicators
        sql_keywords = ["how many", "count", "total", "average", "percentage", "statistics", "this week", "this month", "today"]
        if any(kw in query_lower for kw in sql_keywords):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.SQL,
                search_level=SearchLevel.DOCUMENT,
                response_format=ResponseFormat.CHART,
                semantic_query=query,
                confidence=0.6
            )

        # Hybrid/table indicators
        table_keywords = ["show me", "list", "find patients", "find extractions", "which patients", "search for"]
        if any(kw in query_lower for kw in table_keywords):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.HYBRID,
                search_level=SearchLevel.SEGMENT if detected_segments else SearchLevel.DOCUMENT,
                response_format=ResponseFormat.TABLE,
                segment_codes=detected_segments,
                semantic_query=query,
                confidence=0.6
            )

        # Default to semantic (use segment-level if specific segments detected)
        return ClassifiedQuery(
            original_query=query,
            intent=QueryIntent.SEMANTIC,
            search_level=SearchLevel.SEGMENT if detected_segments else SearchLevel.DOCUMENT,
            response_format=ResponseFormat.NARRATIVE,
            segment_codes=detected_segments,
            semantic_query=query,
            confidence=0.5
        )

    def _detect_segment_codes(self, query: str) -> Optional[list]:
        """Detect relevant segment codes from query keywords (camelCase matching DB)"""
        query_lower = query.lower()

        segment_mappings = {
            "complaint": "chiefComplaints",
            "history of present": "historyOfPresentIllness",
            "present illness": "historyOfPresentIllness",
            "history": "historyOfPresentIllness",
            "past medical": "medicalHistory",
            "medical history": "medicalHistory",
            "vital": "vitals",
            "blood pressure": "vitals",
            "examination": "examination",
            "diagnosis": "diagnosis",
            "diagnoses": "diagnosis",
            "prescription": "prescription",
            "medication": "prescription",
            "medicine": "prescription",
            "investigation": "investigations",
            "test": "investigations",
            "lab": "investigations",
            "follow up": "followUp",
            "follow-up": "followUp",
            "treatment": "treatmentPlan",
            "referral": "referralDetails",
            "allergy": "allergy",
            "allergies": "allergy",
            "summary": "summary",
        }

        detected = set()
        for keyword, code in segment_mappings.items():
            if keyword in query_lower:
                detected.add(code)

        return list(detected) if detected else None


# Singleton instance
query_classifier_service = QueryClassifierService()

"""
Q&A Synthesis Service

Generates narrative responses from semantic search results using Gemini.

Features:
- Synthesizes insights from multiple search results
- Medical-appropriate language
- Citation of sources
"""

import json
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from models.qa_models import SearchResultItem, QAPriorContext

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a medical data analyst assistant helping doctors understand patterns in their patient data.

Given search results from medical extractions, synthesize a clear, concise narrative that:
1. Directly answers the user's question
2. Cites specific patient examples when relevant (use patient names or IDs)
3. Identifies patterns and trends
4. Uses appropriate medical terminology
5. Highlights important clinical insights

Keep responses focused and actionable. Aim for 2-4 paragraphs unless the query requires more detail.

Important:
- Never make up information. Only report what's in the provided data.
- Do NOT use \\n, newlines, or escape sequences inside the narrative string. Write everything as one continuous flowing text. Use periods and spaces to separate ideas, not line breaks.
- Do NOT use markdown formatting like **bold** or *italic*. Write in plain text only.

You MUST respond in valid JSON format with this structure:
{
  "narrative": "Your narrative response here as one continuous text without newlines or markdown...",
  "referenced_results": [1, 3, 5]
}"""

SYNTHESIS_USER_PROMPT = """User's question: "{query}"

Search results (medical extractions with similarity scores):
{results_context}

Total matching records: {total_count}

Respond in JSON format with your narrative and which result numbers (1-indexed) you referenced."""


class QASynthesisService:
    """
    Synthesizes narrative responses from search results.

    Usage:
        service = QASynthesisService()

        narrative = await service.synthesize(
            query="What are common patterns in diabetic patients?",
            results=[...search results...],
            total_count=50
        )
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy load Gemini client"""
        if self._client is None:
            from services.gemini_client_factory import get_gemini_client
            self._client = get_gemini_client()
        return self._client

    def _format_results_context(
        self,
        results: List[SearchResultItem],
        max_results: int = 10
    ) -> str:
        """Format search results as context for synthesis"""
        context_parts = []

        for i, result in enumerate(results[:max_results]):
            parts = [f"Result {i+1} (similarity: {result.similarity_score:.2f}):"]

            if result.patient_name:
                parts.append(f"  Patient: {result.patient_name}")
            if result.patient_external_id:
                parts.append(f"  UHID: {result.patient_external_id}")
            if result.doctor_name:
                parts.append(f"  Doctor: {result.doctor_name}")
            if result.consultation_type_name:
                parts.append(f"  Type: {result.consultation_type_name}")
            if result.created_at:
                parts.append(f"  Date: {result.created_at}")
            if result.matched_segment_code:
                parts.append(f"  Matched Segment: {result.matched_segment_code}")

            # Include key clinical data from extraction
            if result.extraction_data:
                data = result.extraction_data

                # Diagnosis (check multiple key variations)
                diagnosis = (data.get("diagnosis") or data.get("diagnosisOp") or
                            data.get("diagnosisDischarge") or data.get("primary_diagnosis"))
                if diagnosis:
                    parts.append(f"  Diagnosis: {self._format_field(diagnosis)}")

                # Chief Complaints (check multiple key variations)
                complaints = (data.get("chief_complaints") or data.get("chiefComplaints") or
                             data.get("chiefComplaintsOp") or data.get("chiefComplaintsDischarge") or
                             data.get("complaints"))
                if complaints:
                    parts.append(f"  Chief Complaints: {self._format_field(complaints)}")

                # Medications/Prescriptions (check multiple key variations)
                meds = (data.get("prescription") or data.get("prescriptionOp") or
                       data.get("prescriptionDischarge") or data.get("medications") or
                       data.get("medicines") or data.get("drugs") or
                       data.get("dischargeMedication") or data.get("prescriptions"))
                if meds:
                    parts.append(f"  Medications: {self._format_field(meds)}")

                # Investigations
                investigations = (data.get("investigations") or data.get("investigationsDischarge") or
                                 data.get("investigation") or data.get("orderedLabs"))
                if investigations:
                    parts.append(f"  Investigations: {self._format_field(investigations)}")

                # Medical History
                history = (data.get("medical_history") or data.get("medicalHistory") or
                          data.get("history") or data.get("historyOp") or data.get("historyDischarge"))
                if history:
                    parts.append(f"  Medical History: {self._format_field(history)}")

            context_parts.append("\n".join(parts))

        return "\n\n".join(context_parts)

    def _format_field(self, value: Any) -> str:
        """Format a field value for display"""
        if isinstance(value, list):
            if not value:
                return "-"
            if isinstance(value[0], dict):
                return ", ".join(str(v.get("name") or v.get("medication") or v) for v in value[:5])
            return ", ".join(str(v) for v in value[:5])
        if isinstance(value, dict):
            return str(value.get("name") or value.get("description") or json.dumps(value)[:100])
        return str(value)[:200]

    async def synthesize(
        self,
        query: str,
        results: List[SearchResultItem],
        total_count: int,
        hospital_id: Optional[UUID] = None,
        prior_context: Optional[QAPriorContext] = None
    ) -> Dict[str, Any]:
        """
        Generate narrative response from search results.

        Args:
            query: Original user query
            results: Search results to synthesize
            total_count: Total matching records
            hospital_id: Optional hospital context
            prior_context: Previous Q&A exchange for follow-up context

        Returns:
            Dict with narrative and metadata
        """
        start_time = datetime.now(timezone.utc)

        if not results:
            return {
                "narrative": "No matching records found for your query. Try broadening your search criteria.",
                "synthesis_time_ms": 0
            }

        try:
            client = self._get_client()

            results_context = self._format_results_context(results)

            user_prompt = SYNTHESIS_USER_PROMPT.format(
                query=query,
                results_context=results_context,
                total_count=total_count
            )

            # Inject prior conversation context for follow-up queries
            if prior_context:
                context_block = '\n\nConversation context (previous Q&A):'
                context_block += f'\n- User previously asked: "{prior_context.query}"'
                if prior_context.narrative:
                    narrative_preview = prior_context.narrative[:500]
                    if len(prior_context.narrative) > 500:
                        narrative_preview += "..."
                    context_block += f'\n- Previous answer: "{narrative_preview}"'
                context_block += '\nThe current query may be a follow-up. Use this context to provide a relevant answer.'
                user_prompt += context_block

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {"role": "user", "parts": [{"text": SYNTHESIS_SYSTEM_PROMPT}]},
                    {"role": "model", "parts": [{"text": '{"narrative": "I understand. I\'ll synthesize medical data insights clearly and accurately.", "referenced_results": []}'}]},
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                config={
                    "temperature": 0.3,
                    "max_output_tokens": 3000,
                    "response_mime_type": "application/json",
                }
            )

            response_text = response.text.strip()

            end_time = datetime.now(timezone.utc)
            synthesis_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Parse JSON response
            try:
                parsed = json.loads(response_text)
                narrative = parsed.get("narrative", response_text)
                # Clean up any literal \n escape sequences or markdown that Gemini may include
                narrative = narrative.replace("\\n", " ").replace("\n", " ")
                narrative = narrative.replace("**", "")
                # Collapse multiple spaces
                while "  " in narrative:
                    narrative = narrative.replace("  ", " ")
                narrative = narrative.strip()
                referenced_indices = parsed.get("referenced_results", [])

                # Convert 1-indexed result numbers to extraction IDs
                referenced_extraction_ids = []
                for idx in referenced_indices:
                    if 1 <= idx <= len(results):
                        referenced_extraction_ids.append(str(results[idx - 1].extraction_id))

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse synthesis JSON (likely truncated), extracting narrative")
                # Try to extract narrative from truncated JSON like: {"narrative": "some text...
                narrative = response_text
                if '"narrative"' in response_text:
                    import re
                    match = re.search(r'"narrative"\s*:\s*"(.*)', response_text, re.DOTALL)
                    if match:
                        # Extract everything after "narrative": " and strip trailing incomplete JSON
                        extracted = match.group(1)
                        # Remove trailing incomplete JSON artifacts
                        # Look for the last complete sentence
                        for ending in ['. ', '.\n', '."', '...']:
                            last_pos = extracted.rfind(ending)
                            if last_pos > 0:
                                extracted = extracted[:last_pos + len(ending)].rstrip('",} \n')
                                break
                        narrative = extracted
                referenced_extraction_ids = [str(r.extraction_id) for r in results[:5]]

            return {
                "narrative": narrative,
                "synthesis_time_ms": synthesis_time_ms,
                "results_used": len(results),
                "total_available": total_count,
                "referenced_extraction_ids": referenced_extraction_ids
            }

        except Exception as e:
            logger.error(f"Synthesis failed: {e}", exc_info=True)

            # Fallback: Generate simple summary
            return {
                "narrative": self._generate_fallback_narrative(query, results, total_count),
                "synthesis_time_ms": 0,
                "fallback": True
            }

    def _generate_fallback_narrative(
        self,
        query: str,
        results: List[SearchResultItem],
        total_count: int
    ) -> str:
        """Generate simple narrative without AI"""
        if not results:
            return "No matching records found."

        narrative_parts = [
            f"Found {total_count} matching records for: \"{query}\"\n"
        ]

        # Group by patient if available
        patients = {}
        for result in results[:10]:
            patient_key = result.patient_name or result.patient_external_id or "Unknown"
            if patient_key not in patients:
                patients[patient_key] = []
            patients[patient_key].append(result)

        narrative_parts.append(f"Results span {len(patients)} patients:")

        for patient, patient_results in list(patients.items())[:5]:
            result = patient_results[0]
            narrative_parts.append(
                f"- {patient}: {result.consultation_type_name or 'Consultation'} "
                f"({result.created_at[:10] if result.created_at else 'Unknown date'})"
            )

        if len(patients) > 5:
            narrative_parts.append(f"... and {len(patients) - 5} more patients")

        return "\n".join(narrative_parts)


# Singleton instance
qa_synthesis_service = QASynthesisService()

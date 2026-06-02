"""
Student Longitudinal Service

Provides longitudinal data aggregation and comparison for student visits:
- Compare visits side-by-side
- Track changes over time (medications, diagnoses, vitals)
- Generate change summaries
- Synthesize narratives from longitudinal data
"""

import logging
import json
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StudentLongitudinalService:
    """
    Service for longitudinal student data analysis.

    Usage:
        service = StudentLongitudinalService()

        # Compare two visits
        comparison = await service.compare_visits(
            student_id=student_uuid,
            extraction_id_1=visit1_uuid,
            extraction_id_2=visit2_uuid
        )

        # Get changes since a baseline visit
        changes = await service.get_changes_since_visit(
            student_id=student_uuid,
            baseline_extraction_id=baseline_uuid,
            school_id=school_uuid
        )
    """

    def __init__(self):
        self._supabase = None
        self._gemini = None

    def _get_supabase(self):
        """Lazy load Supabase client"""
        if self._supabase is None:
            from services.supabase_service import supabase
            self._supabase = supabase
        return self._supabase

    def _get_gemini(self):
        """Lazy load Gemini client"""
        if self._gemini is None:
            from services.gemini_client_factory import get_gemini_client
            self._gemini = get_gemini_client()
        return self._gemini

    async def get_changes_since_visit(
        self,
        student_id: UUID,
        baseline_extraction_id: UUID,
        school_id: UUID,
        current_extraction_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Get changes between a baseline visit and current/latest visit.

        Returns:
            Dict with:
            - baseline_visit: Baseline extraction summary
            - current_visit: Current extraction summary
            - medication_changes: Added/removed/modified medications
            - new_diagnoses: Diagnoses in current not in baseline
            - resolved_complaints: Complaints in baseline not in current
            - vital_trends: Vital sign trends/changes
        """
        try:
            supabase = self._get_supabase()

            # Fetch baseline extraction
            baseline_result = supabase.table("extractions")\
                .select("*")\
                .eq("id", str(baseline_extraction_id))\
                .single()\
                .execute()

            if not baseline_result.data:
                return {"error": "Baseline extraction not found"}

            baseline = baseline_result.data

            # Fetch current/latest extraction
            if current_extraction_id:
                current_result = supabase.table("extractions")\
                    .select("*")\
                    .eq("id", str(current_extraction_id))\
                    .single()\
                    .execute()
            else:
                # Get most recent extraction for student
                # Note: extractions doesn't have school_id, filter through counsellors join
                current_result = supabase.table("extractions")\
                    .select("*, counsellors!inner(school_id)")\
                    .eq("student_id", str(student_id))\
                    .eq("counsellors.school_id", str(school_id))\
                    .order("created_at", desc=True)\
                    .limit(1)\
                    .execute()
                current_result.data = current_result.data[0] if current_result.data else None

            if not current_result.data:
                return {"error": "Current extraction not found"}

            current = current_result.data

            # Parse extraction data
            baseline_data = self._parse_extraction_data(baseline)
            current_data = self._parse_extraction_data(current)

            # Compare and generate changes
            changes = {
                "baseline_visit": {
                    "extraction_id": baseline["id"],
                    "created_at": baseline["created_at"],
                    "summary": baseline_data.get("summary", "")
                },
                "current_visit": {
                    "extraction_id": current["id"],
                    "created_at": current["created_at"],
                    "summary": current_data.get("summary", "")
                },
                "medication_changes": self._compare_medications(
                    baseline_data.get("medications", []),
                    current_data.get("medications", [])
                ),
                "new_diagnoses": self._get_new_items(
                    baseline_data.get("diagnoses", []),
                    current_data.get("diagnoses", [])
                ),
                "resolved_complaints": self._get_removed_items(
                    baseline_data.get("chief_complaints", []),
                    current_data.get("chief_complaints", [])
                ),
                "vital_trends": self._compare_vitals(
                    baseline_data.get("vitals", {}),
                    current_data.get("vitals", {})
                ),
                "time_span_days": self._calculate_time_span(
                    baseline["created_at"],
                    current["created_at"]
                )
            }

            return changes

        except Exception as e:
            logger.error(f"Failed to get changes since visit: {e}", exc_info=True)
            return {"error": str(e)}

    async def compare_visits(
        self,
        student_id: UUID,
        extraction_id_1: UUID,
        extraction_id_2: UUID
    ) -> Dict[str, Any]:
        """
        Compare two specific visits side-by-side.

        Returns:
            Dict with both visit summaries and detailed comparison.
        """
        try:
            supabase = self._get_supabase()

            # Fetch both extractions
            result = supabase.table("extractions")\
                .select("*")\
                .in_("id", [str(extraction_id_1), str(extraction_id_2)])\
                .execute()

            extractions = {str(r["id"]): r for r in (result.data or [])}

            visit1 = extractions.get(str(extraction_id_1))
            visit2 = extractions.get(str(extraction_id_2))

            if not visit1 or not visit2:
                return {"error": "One or both extractions not found"}

            # Ensure chronological order
            if visit1["created_at"] > visit2["created_at"]:
                visit1, visit2 = visit2, visit1

            data1 = self._parse_extraction_data(visit1)
            data2 = self._parse_extraction_data(visit2)

            comparison = {
                "visit_1": {
                    "extraction_id": visit1["id"],
                    "created_at": visit1["created_at"],
                    "chief_complaints": data1.get("chief_complaints", []),
                    "diagnoses": data1.get("diagnoses", []),
                    "medications": data1.get("medications", []),
                    "vitals": data1.get("vitals", {}),
                    "investigations": data1.get("investigations", [])
                },
                "visit_2": {
                    "extraction_id": visit2["id"],
                    "created_at": visit2["created_at"],
                    "chief_complaints": data2.get("chief_complaints", []),
                    "diagnoses": data2.get("diagnoses", []),
                    "medications": data2.get("medications", []),
                    "vitals": data2.get("vitals", {}),
                    "investigations": data2.get("investigations", [])
                },
                "changes": {
                    "new_complaints": self._get_new_items(
                        data1.get("chief_complaints", []),
                        data2.get("chief_complaints", [])
                    ),
                    "resolved_complaints": self._get_removed_items(
                        data1.get("chief_complaints", []),
                        data2.get("chief_complaints", [])
                    ),
                    "new_diagnoses": self._get_new_items(
                        data1.get("diagnoses", []),
                        data2.get("diagnoses", [])
                    ),
                    "medication_changes": self._compare_medications(
                        data1.get("medications", []),
                        data2.get("medications", [])
                    ),
                    "vital_changes": self._compare_vitals(
                        data1.get("vitals", {}),
                        data2.get("vitals", {})
                    )
                },
                "time_span_days": self._calculate_time_span(
                    visit1["created_at"],
                    visit2["created_at"]
                )
            }

            return comparison

        except Exception as e:
            logger.error(f"Failed to compare visits: {e}", exc_info=True)
            return {"error": str(e)}

    async def get_longitudinal_summary(
        self,
        student_id: UUID,
        school_id: UUID,
        counsellor_id: Optional[UUID] = None,
        num_visits: int = 5
    ) -> Dict[str, Any]:
        """
        Aggregate data across multiple visits.

        Returns:
            Dict with aggregated timeline, patterns, and trends.
            Includes per-visit medication/diagnosis details for history queries.
        """
        try:
            supabase = self._get_supabase()

            # Note: extractions doesn't have school_id, filter through counsellors join
            query = supabase.table("extractions")\
                .select("*, counsellors!inner(school_id, full_name), consultation_types(type_name)")\
                .eq("student_id", str(student_id))\
                .eq("counsellors.school_id", str(school_id))\
                .order("created_at", desc=True)\
                .limit(num_visits)

            if counsellor_id:
                query = query.eq("counsellor_id", str(counsellor_id))

            result = query.execute()
            visits = result.data or []

            if not visits:
                return {"error": "No visits found for student"}

            # Aggregate data
            all_diagnoses = set()
            all_medications = set()
            vital_history = []
            complaint_history = []
            medication_history = []  # Per-visit medication tracking

            for visit in reversed(visits):  # Chronological order
                data = self._parse_extraction_data(visit)

                for d in data.get("diagnoses", []):
                    all_diagnoses.add(self._normalize_item(d))

                visit_medications = []
                for m in data.get("medications", []):
                    normalized = self._normalize_medication(m)
                    all_medications.add(normalized)
                    visit_medications.append(normalized)

                # Track medications per visit
                medication_history.append({
                    "date": visit["created_at"],
                    "extraction_id": visit["id"],
                    "medications": visit_medications,
                    "counsellor_name": visit.get("counsellors", {}).get("full_name") if visit.get("counsellors") else None,
                    "consultation_type": visit.get("consultation_types", {}).get("type_name") if visit.get("consultation_types") else None
                })

                if data.get("vitals"):
                    vital_history.append({
                        "date": visit["created_at"],
                        "vitals": data["vitals"]
                    })

                if data.get("chief_complaints"):
                    complaint_history.append({
                        "date": visit["created_at"],
                        "complaints": data["chief_complaints"]
                    })

            summary = {
                "student_id": str(student_id),
                "total_visits": len(visits),
                "date_range": {
                    "from": visits[-1]["created_at"] if visits else None,
                    "to": visits[0]["created_at"] if visits else None
                },
                "all_diagnoses": list(all_diagnoses),
                "all_medications": list(all_medications),
                "vital_history": vital_history,
                "complaint_history": complaint_history,
                "medication_history": medication_history,  # Per-visit medications
                "visits": [
                    {
                        "extraction_id": v["id"],
                        "created_at": v["created_at"],
                        "consultation_type_id": v.get("consultation_type_id"),
                        "consultation_type_name": v.get("consultation_types", {}).get("type_name") if v.get("consultation_types") else None,
                        "counsellor_name": v.get("counsellors", {}).get("full_name") if v.get("counsellors") else None
                    }
                    for v in visits
                ]
            }

            return summary

        except Exception as e:
            logger.error(f"Failed to get longitudinal summary: {e}", exc_info=True)
            return {"error": str(e)}

    async def get_single_visit_data(
        self,
        extraction_id: UUID,
        school_id: UUID
    ) -> Dict[str, Any]:
        """
        Fetch and parse data for a single specific visit/extraction.

        Args:
            extraction_id: The extraction UUID to fetch
            school_id: School context for validation

        Returns:
            Dict with extraction_id, created_at, counsellor_name, consultation_type_name,
            parsed_data, and visit_info — or {"error": ...} on failure.
        """
        try:
            supabase = self._get_supabase()

            result = supabase.table("extractions")\
                .select("*, counsellors!inner(full_name, school_id), consultation_types(type_name)")\
                .eq("id", str(extraction_id))\
                .eq("counsellors.school_id", str(school_id))\
                .single()\
                .execute()

            if not result.data:
                return {"error": "Extraction not found"}

            row = result.data
            parsed_data = self._parse_extraction_data(row)
            counsellor_info = row.get("counsellors") or {}
            ct_info = row.get("consultation_types") or {}

            return {
                "extraction_id": row["id"],
                "created_at": row["created_at"],
                "counsellor_name": counsellor_info.get("full_name", "Unknown"),
                "consultation_type_name": ct_info.get("type_name", "Consultation"),
                "parsed_data": parsed_data,
                "visit_info": {
                    "extraction_id": row["id"],
                    "created_at": row["created_at"],
                    "consultation_type_name": ct_info.get("type_name"),
                    "counsellor_name": counsellor_info.get("full_name"),
                }
            }

        except Exception as e:
            logger.error(f"Failed to get single visit data: {e}", exc_info=True)
            return {"error": str(e)}

    async def synthesize_single_visit_narrative(
        self,
        query: str,
        visit_data: Dict[str, Any],
        school_id: UUID
    ) -> str:
        """
        Generate a focused narrative answering the user's question from a single visit.

        Args:
            query: Original user query
            visit_data: Data from get_single_visit_data()
            school_id: School context

        Returns:
            Natural language narrative focused on the specific visit
        """
        try:
            client = self._get_gemini()

            parsed = visit_data.get("parsed_data", {})
            visit_date = (visit_data.get("created_at", "Unknown") or "Unknown")[:10]
            counsellor_name = visit_data.get("counsellor_name", "Unknown")
            consult_type = visit_data.get("consultation_type_name", "Consultation")

            # Format clinical data sections
            complaints = parsed.get("chief_complaints", [])
            diagnoses = parsed.get("diagnoses", [])
            medications = parsed.get("medications", [])
            vitals = parsed.get("vitals", {})
            investigations = parsed.get("investigations", [])

            def _fmt_list(items: list) -> str:
                if not items:
                    return "None recorded"
                formatted = []
                for item in items[:10]:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("medicine") or item.get("complaint") or item.get("diagnosis") or str(item)
                        formatted.append(str(name))
                    else:
                        formatted.append(str(item))
                result = ", ".join(formatted)
                if len(items) > 10:
                    result += f" (+{len(items) - 10} more)"
                return result

            def _fmt_vitals(v: dict) -> str:
                if not v:
                    return "None recorded"
                parts = [f"{k}: {v_val}" for k, v_val in v.items() if v_val]
                return ", ".join(parts[:8]) if parts else "None recorded"

            system_prompt = """You are a medical assistant helping answer questions about a specific student visit.
Generate a clear, direct narrative answering the user's question using ONLY the provided visit data.

Guidelines:
- Start with a direct answer to the question
- Be specific — cite actual medications, diagnoses, vitals from the data
- Mention the visit date and type for context
- Keep response to 2-4 sentences
- Do not make up information not in the data"""

            user_prompt = f"""User Question: {query}

Visit Details:
- Date: {visit_date}
- Type: {consult_type}
- Counsellor: {counsellor_name}

Clinical Data:
- Chief Complaints: {_fmt_list(complaints)}
- Diagnoses: {_fmt_list(diagnoses)}
- Medications/Prescriptions: {_fmt_list(medications)}
- Vitals: {_fmt_vitals(vitals)}
- Investigations: {_fmt_list(investigations)}

Generate a clear narrative answering the user's question about this specific visit."""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {"role": "user", "parts": [{"text": system_prompt}]},
                    {"role": "model", "parts": [{"text": "I'll provide a focused answer about this specific visit."}]},
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                config={
                    "temperature": 0.3,
                    "max_output_tokens": 500,
                }
            )

            return response.text.strip()

        except Exception as e:
            logger.error(f"Failed to synthesize single visit narrative: {e}", exc_info=True)
            return self._generate_single_visit_fallback(visit_data)

    def _generate_single_visit_fallback(self, visit_data: Dict[str, Any]) -> str:
        """Generate a plain-text fallback for a single visit if LLM fails."""
        parts = []
        parsed = visit_data.get("parsed_data", {})
        visit_date = (visit_data.get("created_at", "Unknown") or "Unknown")[:10]
        consult_type = visit_data.get("consultation_type_name", "Consultation")

        parts.append(f"Visit on {visit_date} ({consult_type}).")

        diagnoses = parsed.get("diagnoses", [])
        if diagnoses:
            diag_str = ", ".join(str(d.get("name", d) if isinstance(d, dict) else d) for d in diagnoses[:3])
            parts.append(f"Diagnoses: {diag_str}.")

        medications = parsed.get("medications", [])
        if medications:
            med_str = ", ".join(str(m.get("name", m) if isinstance(m, dict) else m) for m in medications[:3])
            parts.append(f"Medications: {med_str}.")

        complaints = parsed.get("chief_complaints", [])
        if complaints:
            cc_str = ", ".join(str(c.get("complaint", c) if isinstance(c, dict) else c) for c in complaints[:3])
            parts.append(f"Complaints: {cc_str}.")

        return " ".join(parts) if parts else "Visit data available but could not be summarized."

    async def synthesize_multi_visit_narrative(
        self,
        query: str,
        longitudinal_data: Dict[str, Any],
        school_id: UUID
    ) -> str:
        """
        Generate a narrative summarizing data across multiple visits.

        Args:
            query: Original user query for context
            longitudinal_data: Multi-visit aggregated data from get_longitudinal_summary()
            school_id: School context

        Returns:
            Natural language narrative summarizing the multi-visit data
        """
        try:
            client = self._get_gemini()

            # Extract relevant data from longitudinal summary
            total_visits = longitudinal_data.get("total_visits", 0)
            date_range = longitudinal_data.get("date_range", {})
            all_medications = longitudinal_data.get("all_medications", [])
            all_diagnoses = longitudinal_data.get("all_diagnoses", [])
            visits = longitudinal_data.get("visits", [])
            vital_history = longitudinal_data.get("vital_history", [])
            complaint_history = longitudinal_data.get("complaint_history", [])

            # Build per-visit medication history for prescription queries
            medication_history = longitudinal_data.get("medication_history", [])
            visit_med_summaries = []
            for med_entry in medication_history:
                visit_date = med_entry.get("date", "Unknown")[:10] if med_entry.get("date") else "Unknown"
                meds = med_entry.get("medications", [])
                counsellor = med_entry.get("counsellor_name", "Unknown counsellor")
                consult_type = med_entry.get("consultation_type", "")
                if meds:
                    med_str = ", ".join(meds[:5])
                    if len(meds) > 5:
                        med_str += f" (+{len(meds) - 5} more)"
                    visit_med_summaries.append(f"- {visit_date} ({consult_type}): {med_str}")
                else:
                    visit_med_summaries.append(f"- {visit_date} ({consult_type}): No medications")

            medication_timeline = "\n".join(visit_med_summaries) if visit_med_summaries else "No medication history"

            # Build visit timeline summary
            visit_summaries = []
            for v in visits:
                visit_date = v.get("created_at", "Unknown date")[:10]
                consult_type = v.get("consultation_type_name", "")
                counsellor = v.get("counsellor_name", "")
                visit_summaries.append(f"- {visit_date}: {consult_type} with {counsellor}" if counsellor else f"- {visit_date}: {consult_type}")

            visit_timeline = "\n".join(visit_summaries) if visit_summaries else "No visits found"

            # Build medication history (aggregated)
            med_list = ", ".join(list(all_medications)[:10]) if all_medications else "None recorded"

            # Build diagnosis history
            diag_list = ", ".join(list(all_diagnoses)[:10]) if all_diagnoses else "None recorded"

            system_prompt = """You are a medical assistant helping summarize student history across multiple visits.
Generate a clear, clinically relevant narrative that directly answers the user's question.

Guidelines:
- Start with a direct answer to the question
- Summarize the key information across all visits
- Highlight any patterns or changes over time
- Use clear, simple language
- Keep response to 3-5 sentences
- Do not make up information not in the data"""

            user_prompt = f"""User Question: {query}

Student Visit Summary ({total_visits} visits):
Date Range: {date_range.get('from', 'Unknown')[:10] if date_range.get('from') else 'Unknown'} to {date_range.get('to', 'Unknown')[:10] if date_range.get('to') else 'Unknown'}

Visit Timeline:
{visit_timeline}

Prescription History (per visit):
{medication_timeline}

All Medications Prescribed (across all visits):
{med_list}

Diagnoses (across all visits):
{diag_list}

Generate a clear narrative response answering the user's question about their history across these visits."""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {"role": "user", "parts": [{"text": system_prompt}]},
                    {"role": "model", "parts": [{"text": "I'll provide clear summaries of student visit history."}]},
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                config={
                    "temperature": 0.3,
                    "max_output_tokens": 600,
                }
            )

            return response.text.strip()

        except Exception as e:
            logger.error(f"Failed to synthesize multi-visit narrative: {e}", exc_info=True)
            # Return a structured fallback
            return self._generate_multi_visit_fallback(longitudinal_data)

    def _generate_multi_visit_fallback(self, longitudinal_data: Dict[str, Any]) -> str:
        """Generate a simple multi-visit narrative without LLM as fallback"""
        parts = []
        total_visits = longitudinal_data.get("total_visits", 0)
        date_range = longitudinal_data.get("date_range", {})
        all_medications = longitudinal_data.get("all_medications", [])

        if total_visits:
            parts.append(f"Reviewed {total_visits} visits.")

        if date_range.get("from") and date_range.get("to"):
            from_date = date_range.get("from", "")[:10]
            to_date = date_range.get("to", "")[:10]
            parts.append(f"Date range: {from_date} to {to_date}.")

        if all_medications:
            med_count = len(all_medications)
            med_sample = ", ".join(list(all_medications)[:3])
            parts.append(f"{med_count} medications prescribed including: {med_sample}.")

        return " ".join(parts) if parts else "No visit data available."

    async def synthesize_narrative(
        self,
        query: str,
        longitudinal_data: Dict[str, Any],
        school_id: UUID
    ) -> str:
        """
        Use LLM to generate a natural language narrative from longitudinal data.

        Args:
            query: Original user query for context
            longitudinal_data: Comparison/change data to summarize
            school_id: School context

        Returns:
            Natural language narrative summarizing the data
        """
        try:
            client = self._get_gemini()

            # Build a more structured prompt with clear change summaries
            baseline = longitudinal_data.get("baseline_visit", {})
            current = longitudinal_data.get("current_visit", {})
            med_changes = longitudinal_data.get("medication_changes", {})
            new_diagnoses = longitudinal_data.get("new_diagnoses", [])
            resolved = longitudinal_data.get("resolved_complaints", [])
            vital_trends = longitudinal_data.get("vital_trends", {})
            time_span = longitudinal_data.get("time_span_days", 0)

            # Build structured change summary
            change_summary_parts = []

            if time_span:
                change_summary_parts.append(f"Time between visits: {time_span} days")

            if med_changes:
                added = med_changes.get("added", [])
                removed = med_changes.get("removed", [])
                if added:
                    change_summary_parts.append(f"Medications ADDED: {', '.join(added[:5])}")
                if removed:
                    change_summary_parts.append(f"Medications STOPPED: {', '.join(removed[:5])}")
                if not added and not removed:
                    change_summary_parts.append("Medications: No changes")

            if new_diagnoses:
                change_summary_parts.append(f"New diagnoses: {', '.join(new_diagnoses[:5])}")

            if resolved:
                change_summary_parts.append(f"Resolved complaints: {', '.join(resolved[:5])}")

            if vital_trends:
                vital_changes = []
                for key, trend in vital_trends.items():
                    status = trend.get("status", "unknown")
                    if status in ["increased", "decreased"]:
                        vital_changes.append(f"{key} {status}")
                if vital_changes:
                    change_summary_parts.append(f"Vital changes: {', '.join(vital_changes)}")

            change_summary = "\n".join(change_summary_parts) if change_summary_parts else "No significant changes detected."

            system_prompt = """You are a medical assistant helping summarize changes between student visits.
Generate a clear, clinically relevant narrative that directly answers the user's question.

Guidelines:
- Start with a direct answer to the question
- Be specific about what changed (medications, diagnoses, vitals)
- Use clear, simple language
- Mention the time span between visits
- Keep response to 2-4 sentences
- Do not make up information not in the data"""

            user_prompt = f"""User Question: {query}

Comparison Summary:
- Baseline visit date: {baseline.get('created_at', 'Unknown')}
- Current visit date: {current.get('created_at', 'Unknown')}

Changes Detected:
{change_summary}

Generate a clear narrative response answering the user's question about what changed."""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {"role": "user", "parts": [{"text": system_prompt}]},
                    {"role": "model", "parts": [{"text": "I'll provide clear summaries of student visit changes."}]},
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                config={
                    "temperature": 0.3,
                    "max_output_tokens": 500,
                }
            )

            return response.text.strip()

        except Exception as e:
            logger.error(f"Failed to synthesize narrative: {e}", exc_info=True)
            # Return a structured fallback instead of error
            return self._generate_fallback_narrative(longitudinal_data)

    def _generate_fallback_narrative(self, longitudinal_data: Dict[str, Any]) -> str:
        """Generate a simple narrative without LLM as fallback"""
        parts = []
        time_span = longitudinal_data.get("time_span_days", 0)
        med_changes = longitudinal_data.get("medication_changes", {})
        new_diagnoses = longitudinal_data.get("new_diagnoses", [])
        resolved = longitudinal_data.get("resolved_complaints", [])

        if time_span:
            parts.append(f"Comparing visits {time_span} days apart.")

        added = med_changes.get("added", [])
        removed = med_changes.get("removed", [])
        if added:
            parts.append(f"New medications: {', '.join(added[:3])}.")
        if removed:
            parts.append(f"Stopped medications: {', '.join(removed[:3])}.")
        if not added and not removed:
            parts.append("No medication changes.")

        if new_diagnoses:
            parts.append(f"New diagnoses: {', '.join(new_diagnoses[:3])}.")
        if resolved:
            parts.append(f"Resolved: {', '.join(resolved[:3])}.")

        return " ".join(parts) if parts else "No significant changes detected between visits."

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_extraction_data(self, extraction: Dict[str, Any]) -> Dict[str, Any]:
        """Parse extraction JSON data into structured format."""
        result = {
            "summary": "",
            "chief_complaints": [],
            "diagnoses": [],
            "medications": [],
            "vitals": {},
            "investigations": []
        }

        # Try different JSON columns (prefer edited over original)
        data = None
        for col in ["edited_extraction_json", "original_extraction_json",
                     "core_extraction", "additional_extraction", "merged_extraction", "extraction_data"]:
            if extraction.get(col):
                try:
                    if isinstance(extraction[col], str):
                        data = json.loads(extraction[col])
                    else:
                        data = extraction[col]
                    break
                except:
                    continue

        if not data:
            return result

        # Extract chief complaints
        if "chiefComplaints" in data:
            cc = data["chiefComplaints"]
            if isinstance(cc, list):
                result["chief_complaints"] = cc
            elif isinstance(cc, dict):
                # Handle different nested key names
                result["chief_complaints"] = (
                    cc.get("chief_complaints") or cc.get("complaints") or []
                )

        # Extract diagnoses
        if "diagnosis" in data:
            diag = data["diagnosis"]
            if isinstance(diag, list):
                result["diagnoses"] = diag
            elif isinstance(diag, dict):
                if "diagnoses" in diag:
                    result["diagnoses"] = diag["diagnoses"]
                elif "primary" in diag or "secondary" in diag:
                    result["diagnoses"] = [diag.get("primary")] + (diag.get("secondary", []) or [])

        # Extract medications/prescriptions
        if "prescription" in data:
            presc = data["prescription"]
            if isinstance(presc, list):
                result["medications"] = presc
            elif isinstance(presc, dict) and "medicines" in presc:
                result["medications"] = presc["medicines"]

        # Extract vitals
        if "vitals" in data:
            vitals = data["vitals"]
            if isinstance(vitals, dict):
                result["vitals"] = vitals

        # Extract investigations
        if "investigations" in data:
            inv = data["investigations"]
            if isinstance(inv, list):
                result["investigations"] = inv
            elif isinstance(inv, dict):
                result["investigations"] = inv.get("ordered", []) + inv.get("recommended", [])

        return result

    def _compare_medications(
        self,
        baseline_meds: List[Any],
        current_meds: List[Any]
    ) -> Dict[str, List[str]]:
        """Compare medication lists and return changes."""

        baseline_set = {self._normalize_medication(m) for m in baseline_meds}
        current_set = {self._normalize_medication(m) for m in current_meds}

        return {
            "added": list(current_set - baseline_set),
            "removed": list(baseline_set - current_set),
            "unchanged": list(baseline_set & current_set)
        }

    def _get_new_items(self, baseline: List[Any], current: List[Any]) -> List[str]:
        """Get items in current that are not in baseline."""
        baseline_set = {self._normalize_item(i) for i in baseline}
        current_set = {self._normalize_item(i) for i in current}
        return list(current_set - baseline_set)

    def _get_removed_items(self, baseline: List[Any], current: List[Any]) -> List[str]:
        """Get items in baseline that are not in current."""
        baseline_set = {self._normalize_item(i) for i in baseline}
        current_set = {self._normalize_item(i) for i in current}
        return list(baseline_set - current_set)

    def _compare_vitals(
        self,
        baseline_vitals: Dict[str, Any],
        current_vitals: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare vital signs and return trends."""

        trends = {}

        for key in set(baseline_vitals.keys()) | set(current_vitals.keys()):
            baseline_val = baseline_vitals.get(key)
            current_val = current_vitals.get(key)

            if baseline_val is None and current_val is not None:
                trends[key] = {"status": "new", "current": current_val}
            elif baseline_val is not None and current_val is None:
                trends[key] = {"status": "removed", "baseline": baseline_val}
            elif baseline_val != current_val:
                # Try numeric comparison
                try:
                    b_num = self._extract_numeric(baseline_val)
                    c_num = self._extract_numeric(current_val)
                    if b_num is not None and c_num is not None:
                        change = c_num - b_num
                        trend = "increased" if change > 0 else "decreased" if change < 0 else "unchanged"
                        trends[key] = {
                            "status": trend,
                            "baseline": baseline_val,
                            "current": current_val,
                            "change": change
                        }
                    else:
                        trends[key] = {
                            "status": "changed",
                            "baseline": baseline_val,
                            "current": current_val
                        }
                except:
                    trends[key] = {
                        "status": "changed",
                        "baseline": baseline_val,
                        "current": current_val
                    }

        return trends

    def _normalize_medication(self, med: Any) -> str:
        """Normalize a medication entry to a comparable string."""
        if isinstance(med, str):
            return med.lower().strip()
        elif isinstance(med, dict):
            name = med.get("name", med.get("medicine", med.get("drug", "")))
            return str(name).lower().strip()
        return str(med).lower().strip()

    def _normalize_item(self, item: Any) -> str:
        """Normalize an item to a comparable string."""
        if isinstance(item, str):
            return item.lower().strip()
        elif isinstance(item, dict):
            # Try common keys
            for key in ["name", "complaint", "diagnosis", "description", "value"]:
                if key in item:
                    return str(item[key]).lower().strip()
            return str(item).lower().strip()
        return str(item).lower().strip()

    def _extract_numeric(self, value: Any) -> Optional[float]:
        """Extract numeric value from a vital reading."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            import re
            match = re.search(r'[\d.]+', value)
            if match:
                return float(match.group())
        return None

    def _calculate_time_span(self, date1: str, date2: str) -> int:
        """Calculate days between two dates."""
        try:
            d1 = datetime.fromisoformat(date1.replace('Z', '+00:00'))
            d2 = datetime.fromisoformat(date2.replace('Z', '+00:00'))
            return abs((d2 - d1).days)
        except:
            return 0


# Singleton instance
student_longitudinal_service = StudentLongitudinalService()

"""
Analytics Engine Service

Text-to-SQL using Gemini for analytics queries.

Features:
- Natural language to SQL conversion
- SQL validation (SELECT only, no dangerous keywords)
- Chart type inference from results
- Clinical intelligence table queries
"""

import json
import re
import logging
from typing import Optional, Dict, Any, List, Union
from uuid import UUID
from datetime import datetime, timezone

from models.qa_models import ChartData, ChartType, StatCardData

logger = logging.getLogger(__name__)

# Database schema context for text-to-SQL
DATABASE_SCHEMA = """
Available tables for analytics:

1. medical_extractions
   - id (UUID, PK)
   - doctor_id (UUID, FK) -- Use doctors.hospital_id to filter by hospital
   - patient_id (UUID, FK)
   - consultation_type_id (UUID, FK)
   - extraction_mode (VARCHAR)
   - segment_count (INT)
   - created_at (TIMESTAMPTZ)
   NOTE: medical_extractions does NOT have hospital_id. Join with doctors table to filter by hospital.

2. consultation_types
   - id (UUID, PK)
   - type_code (VARCHAR)
   - type_name (VARCHAR)

3. doctors
   - id (UUID, PK)
   - full_name (VARCHAR)
   - email (VARCHAR)
   - specialization (VARCHAR)
   - hospital_id (UUID, FK)

4. patients
   - id (UUID, PK)
   - patient_id (VARCHAR) -- external UHID
   - full_name (VARCHAR)
   - date_of_birth (DATE)
   - gender (VARCHAR)

5. hospitals
   - id (UUID, PK)
   - hospital_name (VARCHAR)
   - hospital_code (VARCHAR)

6. clinical_severity_assessments
   - id (UUID, PK)
   - extraction_id (UUID, FK)
   - severity_level (VARCHAR) -- low, moderate, high, critical
   - severity_score (INT)
   - created_at (TIMESTAMPTZ)

7. patient_interventions
   - id (UUID, PK)
   - extraction_id (UUID, FK)
   - patient_id (UUID, FK)
   - intervention_code (VARCHAR)
   - intervention_category (VARCHAR) -- OP_TO_IP, FOLLOWUP_DUE, etc.
   - priority (VARCHAR) -- low, medium, high, critical
   - created_at (TIMESTAMPTZ)

8. intervention_outcomes
   - id (UUID, PK)
   - intervention_id (UUID, FK)
   - outcome_status (VARCHAR) -- pending, converted, declined, expired
   - outcome_date (TIMESTAMPTZ)
"""

TEXT_TO_SQL_SYSTEM_PROMPT = f"""You are a SQL generator for a medical records database.
Generate PostgreSQL SELECT queries only. Never generate INSERT, UPDATE, DELETE, DROP, or ALTER queries.

{DATABASE_SCHEMA}

Rules:
1. Always include hospital_id filter for security: WHERE hospital_id = '{{hospital_id}}'
2. Only generate SELECT queries
3. Use proper date functions for time-based queries (NOW(), INTERVAL)
4. For counts, always alias as 'count' or 'total'
5. For groupings, alias grouped column as 'label' and count as 'value'
6. Limit results to 100 rows max
7. Never use subqueries with user input
8. Always use parameterized-style placeholders

Respond with JSON only:
{{
  "sql": "SELECT ... FROM ... WHERE hospital_id = '{{hospital_id}}' ...",
  "chart_type": "bar" | "line" | "pie" | "stat_card",
  "title": "Chart/Stat title",
  "description": "Brief description of what this shows"
}}"""


# Dangerous SQL patterns to block
DANGEROUS_PATTERNS = [
    r'\bINSERT\b',
    r'\bUPDATE\b',
    r'\bDELETE\b',
    r'\bDROP\b',
    r'\bALTER\b',
    r'\bTRUNCATE\b',
    r'\bCREATE\b',
    r'\bGRANT\b',
    r'\bREVOKE\b',
    r'\bEXEC\b',
    r'\bEXECUTE\b',
    r'--',  # SQL comments
    r';.*SELECT',  # Multiple statements
]


class AnalyticsEngineService:
    """
    Text-to-SQL analytics engine for medical data queries.

    Usage:
        service = AnalyticsEngineService()

        result = await service.execute_analytics_query(
            query="How many extractions were done this month?",
            hospital_id=hospital_uuid
        )

        print(result["chart"])  # ChartData or StatCardData
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy load Gemini client"""
        if self._client is None:
            from services.gemini_client_factory import get_gemini_client
            self._client = get_gemini_client()
        return self._client

    def _validate_sql(self, sql: str) -> tuple[bool, Optional[str]]:
        """
        Validate SQL query for safety.

        Returns:
            (is_valid, error_message)
        """
        sql_upper = sql.upper()

        # Must be a SELECT query
        if not sql_upper.strip().startswith("SELECT"):
            return False, "Only SELECT queries are allowed"

        # Check for dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, sql_upper):
                return False, f"Dangerous SQL pattern detected"

        # Must not have multiple statements
        if sql.count(";") > 1:
            return False, "Multiple SQL statements not allowed"

        return True, None

    async def execute_analytics_query(
        self,
        query: str,
        hospital_id: UUID,
        doctor_id: Optional[UUID] = None,
        patient_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Convert natural language to SQL and execute analytics query.

        Args:
            query: Natural language analytics query
            hospital_id: Hospital ID for scoping
            doctor_id: Optional doctor filter
            patient_id: Optional patient filter

        Returns:
            Dict with chart/stat_card data or error
        """
        from services.supabase_service import supabase

        start_time = datetime.now(timezone.utc)

        try:
            # Generate SQL using Gemini
            client = self._get_client()

            # Build filter context for LLM
            filter_context = []
            if doctor_id:
                filter_context.append(f"Doctor ID filter: {doctor_id}")
            if patient_id:
                filter_context.append(f"Patient ID filter: {patient_id}")
            filter_str = "\n".join(filter_context) if filter_context else "No additional filters"

            prompt = f"""Generate SQL for this analytics question:
"{query}"

Hospital ID to use: {hospital_id}
{filter_str}

Remember: Only SELECT queries, always filter by hospital_id."""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {"role": "user", "parts": [{"text": TEXT_TO_SQL_SYSTEM_PROMPT}]},
                    {"role": "model", "parts": [{"text": "I understand. I'll generate safe SELECT queries only with JSON response."}]},
                    {"role": "user", "parts": [{"text": prompt}]}
                ],
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 1000,
                }
            )

            response_text = response.text.strip()

            # Clean markdown if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)
            sql = result.get("sql", "")
            chart_type = result.get("chart_type", "stat_card")
            title = result.get("title", "Query Result")

            # Validate SQL
            is_valid, error = self._validate_sql(sql)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"SQL validation failed: {error}",
                    "generated_sql": sql
                }

            # Execute SQL
            try:
                sql_result = supabase.rpc("exec_sql", {"sql_query": sql}).execute()
            except Exception as sql_error:
                logger.warning(f"SQL execution failed, trying fallback: {sql_error}")
                return await self._execute_direct_analytics(query, hospital_id, doctor_id, patient_id)

            if not sql_result.data:
                # Try direct execution for simple queries
                return await self._execute_direct_analytics(query, hospital_id, doctor_id, patient_id)

            data = sql_result.data

            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Format response based on chart type
            if chart_type == "stat_card":
                stat_card = self._format_stat_card(data, title)
                return {
                    "success": True,
                    "stat_card": stat_card,
                    "generated_sql": sql,
                    "duration_ms": duration_ms
                }
            else:
                chart = self._format_chart(data, ChartType(chart_type), title)
                return {
                    "success": True,
                    "chart": chart,
                    "generated_sql": sql,
                    "duration_ms": duration_ms
                }

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse SQL generation response: {e}")
            return await self._execute_direct_analytics(query, hospital_id, doctor_id)
        except Exception as e:
            logger.error(f"Analytics query failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _execute_direct_analytics(
        self,
        query: str,
        hospital_id: UUID,
        doctor_id: Optional[UUID] = None,
        patient_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Fallback: Execute predefined analytics queries"""
        from services.supabase_service import supabase

        query_lower = query.lower()

        # Extraction count queries
        if "how many" in query_lower and "extraction" in query_lower:
            from datetime import date, timedelta

            # Build base query - filter by hospital through doctors table
            query_builder = supabase.table("medical_extractions")\
                .select("id, doctors!inner(hospital_id)", count="exact")\
                .eq("doctors.hospital_id", str(hospital_id))

            # Apply date filter
            if "today" in query_lower:
                today = date.today().isoformat()
                query_builder = query_builder.gte("created_at", today)
            elif "this week" in query_lower:
                start_of_week = (date.today() - timedelta(days=date.today().weekday())).isoformat()
                query_builder = query_builder.gte("created_at", start_of_week)
            elif "this month" in query_lower:
                start_of_month = date.today().replace(day=1).isoformat()
                query_builder = query_builder.gte("created_at", start_of_month)

            result = query_builder.execute()
            count = result.count or 0

            return {
                "success": True,
                "stat_card": StatCardData(
                    title="Total Extractions",
                    value=count,
                    subtitle=self._get_time_subtitle(query_lower)
                )
            }

        # Distribution queries
        if "distribution" in query_lower and "consultation" in query_lower:
            # Get consultation type distribution
            result = supabase.table("medical_extractions")\
                .select("consultation_type_id, consultation_types(type_name), doctors!inner(hospital_id)")\
                .eq("doctors.hospital_id", str(hospital_id))\
                .execute()

            # Count by type
            type_counts = {}
            for row in result.data or []:
                ct = row.get("consultation_types", {})
                type_name = ct.get("type_name", "Unknown") if ct else "Unknown"
                type_counts[type_name] = type_counts.get(type_name, 0) + 1

            # Format as chart data
            labels = list(type_counts.keys())
            values = list(type_counts.values())

            return {
                "success": True,
                "chart": ChartData(
                    chart_type=ChartType.PIE,
                    title="Consultation Type Distribution",
                    labels=labels,
                    values=[float(v) for v in values]
                )
            }

        # Default fallback
        return {
            "success": False,
            "error": "Could not parse analytics query. Try rephrasing."
        }

    def _format_stat_card(self, data: List[Dict], title: str) -> StatCardData:
        """Format single value result as stat card"""
        if not data:
            return StatCardData(title=title, value=0)

        row = data[0]
        # Try common column names for count/total
        value = row.get("count") or row.get("total") or row.get("value") or list(row.values())[0]

        return StatCardData(
            title=title,
            value=value if isinstance(value, (int, float, str)) else str(value)
        )

    def _format_chart(
        self,
        data: List[Dict],
        chart_type: ChartType,
        title: str
    ) -> ChartData:
        """Format tabular data as chart"""
        if not data:
            return ChartData(
                chart_type=chart_type,
                title=title,
                labels=[],
                values=[]
            )

        # Extract labels and values from common column patterns
        labels = []
        values = []

        for row in data:
            # Try label column names
            label = row.get("label") or row.get("name") or row.get("category") or str(list(row.values())[0])
            labels.append(str(label))

            # Try value column names
            value = row.get("value") or row.get("count") or row.get("total")
            if value is None:
                # Use second column as value
                vals = list(row.values())
                value = vals[1] if len(vals) > 1 else 0
            values.append(float(value) if value else 0)

        return ChartData(
            chart_type=chart_type,
            title=title,
            labels=labels,
            values=values
        )

    def _get_time_subtitle(self, query: str) -> str:
        """Get time period subtitle from query"""
        if "today" in query:
            return "Today"
        elif "this week" in query:
            return "This Week"
        elif "this month" in query:
            return "This Month"
        elif "this year" in query:
            return "This Year"
        return "All Time"


# Singleton instance
analytics_engine_service = AnalyticsEngineService()

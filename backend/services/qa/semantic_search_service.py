"""
Semantic Search Service

Vector similarity search over extractions using pgvector.

Features:
- Document-level search (full extractions)
- Segment-level search (specific segments like DIAGNOSIS, PRESCRIPTION)
- Permission-based filtering (school, counsellor scoping)
- Student sharing support
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from models.qa_models import SearchResultItem, SearchLevel

logger = logging.getLogger(__name__)


def _unwrap_exec_sql(data):
    """Unwrap exec_sql RPC response if PostgREST wraps it in [{"exec_sql": [...]}]."""
    if (data and isinstance(data, list) and len(data) == 1
            and isinstance(data[0], dict) and "exec_sql" in data[0]):
        return data[0]["exec_sql"]
    return data


class SemanticSearchService:
    """
    Semantic search over extractions using vector similarity.

    Usage:
        service = SemanticSearchService()

        # Document-level search
        results = await service.search(
            query="students with diabetes and hypertension",
            school_id=school_uuid,
            counsellor_id=counsellor_uuid,
            search_level=SearchLevel.DOCUMENT,
            limit=20
        )

        # Segment-level search
        results = await service.search(
            query="high blood pressure readings",
            school_id=school_uuid,
            search_level=SearchLevel.SEGMENT,
            segment_codes=["VITAL_SIGNS", "DIAGNOSIS"],
            limit=20
        )
    """

    def __init__(self):
        from .embedding_service import embedding_service
        self._embedding_service = embedding_service

    async def search(
        self,
        query: str,
        school_id: UUID,
        counsellor_id: Optional[UUID] = None,
        student_id: Optional[UUID] = None,
        search_level: SearchLevel = SearchLevel.DOCUMENT,
        segment_codes: Optional[List[str]] = None,
        consultation_type_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
        include_shared_students: bool = True
    ) -> Dict[str, Any]:
        """
        Perform semantic search over extractions.

        Args:
            query: Search query text
            school_id: School ID for scoping
            counsellor_id: Optional counsellor ID filter
            student_id: Optional student ID filter
            search_level: Document or segment level search
            segment_codes: Filter by segment codes (for segment search)
            consultation_type_id: Filter by consultation type
            date_from: Filter by date range start
            date_to: Filter by date range end
            limit: Maximum results
            offset: Pagination offset
            include_shared_students: Include students shared with this counsellor

        Returns:
            Dict with results and metadata
        """
        from services.supabase_service import supabase

        start_time = datetime.now(timezone.utc)

        # Generate query embedding
        embeddings, embed_usage = await self._embedding_service.generate_embedding(
            texts=[query],
            input_type="search_query",
            school_id=school_id
        )

        query_embedding = embeddings[0]
        logger.info(f"Generated query embedding: dim={len(query_embedding)}, "
                    f"search_level={search_level.value}, segment_codes={segment_codes}")

        # Pad to 1536 if needed (matches database column size)
        if len(query_embedding) < 1536:
            query_embedding = query_embedding + [0.0] * (1536 - len(query_embedding))

        embed_time = datetime.now(timezone.utc)
        embed_time_ms = int((embed_time - start_time).total_seconds() * 1000)

        # Get active model for this school
        model_config = await self._embedding_service.get_active_model(school_id)

        if search_level == SearchLevel.SEGMENT:
            results, total_count = await self._search_segments(
                query_embedding=query_embedding,
                model_id=model_config["id"],
                school_id=school_id,
                counsellor_id=counsellor_id,
                student_id=student_id,
                segment_codes=segment_codes,
                consultation_type_id=consultation_type_id,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
                include_shared_students=include_shared_students
            )
        else:
            results, total_count = await self._search_documents(
                query_embedding=query_embedding,
                model_id=model_config["id"],
                school_id=school_id,
                counsellor_id=counsellor_id,
                student_id=student_id,
                consultation_type_id=consultation_type_id,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
                include_shared_students=include_shared_students
            )

        search_time = datetime.now(timezone.utc)
        search_time_ms = int((search_time - embed_time).total_seconds() * 1000)

        return {
            "results": results,
            "total_count": total_count,
            "search_level": search_level.value,
            "embedding_time_ms": embed_time_ms,
            "search_time_ms": search_time_ms,
            "model_code": model_config["model_code"],
        }

    async def _search_documents(
        self,
        query_embedding: List[float],
        model_id: str,
        school_id: UUID,
        counsellor_id: Optional[UUID] = None,
        student_id: Optional[UUID] = None,
        consultation_type_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
        include_shared_students: bool = True
    ) -> tuple[List[SearchResultItem], int]:
        """Search at document (full extraction) level"""
        from services.supabase_service import supabase

        # Build the embedding vector string for pgvector
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Get accessible student IDs if counsellor_id is provided and sharing is enabled
        accessible_student_ids = None
        if counsellor_id and include_shared_students:
            accessible_student_ids = await self._get_accessible_student_ids(counsellor_id)

        # Build SQL query with vector similarity
        # Using pgvector's <=> operator for cosine distance
        sql = f"""
        SELECT
            ee.extraction_id,
            ee.student_id,
            ee.counsellor_id,
            ee.school_id,
            1 - (ee.embedding <=> '{embedding_str}'::extensions.vector) as similarity_score,
            ee.embedded_content,
            me.created_at,
            me.consultation_type_id,
            COALESCE(me.edited_extraction_json, me.original_extraction_json) as extraction_data,
            p.full_name as patient_name,
            p.student_id as student_external_id,
            d.full_name as counsellor_name,
            ct.type_name as consultation_type_name
        FROM extraction_embeddings ee
        JOIN extractions me ON me.id = ee.extraction_id
        LEFT JOIN students p ON p.id = ee.student_id
        LEFT JOIN counsellors d ON d.id = ee.counsellor_id
        LEFT JOIN consultation_types ct ON ct.id = me.consultation_type_id
        WHERE ee.school_id = '{school_id}'
          AND ee.model_id = '{model_id}'
        """

        # Add filters
        if counsellor_id:
            if accessible_student_ids:
                student_ids_str = ",".join(f"'{pid}'" for pid in accessible_student_ids)
                sql += f" AND (ee.counsellor_id = '{counsellor_id}' OR ee.student_id IN ({student_ids_str}))"
            else:
                sql += f" AND ee.counsellor_id = '{counsellor_id}'"

        if student_id:
            sql += f" AND ee.student_id = '{student_id}'"

        if consultation_type_id:
            sql += f" AND me.consultation_type_id = '{consultation_type_id}'"

        if date_from:
            sql += f" AND me.created_at >= '{date_from.isoformat()}'"

        if date_to:
            sql += f" AND me.created_at <= '{date_to.isoformat()}'"

        # Order by similarity and paginate
        sql += f"""
        ORDER BY similarity_score DESC
        LIMIT {limit}
        OFFSET {offset}
        """

        # Execute search query
        logger.debug(f"Document search SQL (first 200 chars): {sql[:200]}...")
        result = supabase.rpc("exec_sql", {"sql_query": sql}).execute()
        raw_count = len(result.data) if result.data else 0
        result.data = _unwrap_exec_sql(result.data)
        logger.info(f"Document search: raw_rows={raw_count}, unwrapped_rows={len(result.data) if result.data else 0}")

        # If RPC doesn't exist, fall back to direct query (less efficient)
        if not result.data:
            # Fallback: use Supabase SDK filtering (without vector ops)
            logger.warning("exec_sql RPC not available, using fallback search")
            return await self._search_documents_fallback(
                school_id=school_id,
                counsellor_id=counsellor_id,
                student_id=student_id,
                consultation_type_id=consultation_type_id,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset
            )

        # Parse results
        results = []
        for row in result.data:
            results.append(SearchResultItem(
                extraction_id=UUID(row["extraction_id"]),
                student_id=UUID(row["student_id"]) if row.get("student_id") else None,
                patient_name=row.get("patient_name"),
                student_external_id=row.get("student_external_id"),
                counsellor_id=UUID(row["counsellor_id"]) if row.get("counsellor_id") else None,
                counsellor_name=row.get("counsellor_name"),
                consultation_type_name=row.get("consultation_type_name"),
                created_at=row["created_at"],
                similarity_score=float(row["similarity_score"]),
                matched_content_preview=row.get("embedded_content", "")[:200] if row.get("embedded_content") else None,
                extraction_data=row.get("extraction_data")
            ))

        # Get total count
        count_sql = f"""
        SELECT COUNT(*) as total
        FROM extraction_embeddings ee
        JOIN extractions me ON me.id = ee.extraction_id
        WHERE ee.school_id = '{school_id}'
          AND ee.model_id = '{model_id}'
        """
        if counsellor_id:
            count_sql += f" AND ee.counsellor_id = '{counsellor_id}'"
        if student_id:
            count_sql += f" AND ee.student_id = '{student_id}'"

        count_result = supabase.rpc("exec_sql", {"sql_query": count_sql}).execute()
        count_data = _unwrap_exec_sql(count_result.data)
        total_count = count_data[0]["total"] if count_data else len(results)

        return results, total_count

    async def _search_segments(
        self,
        query_embedding: List[float],
        model_id: str,
        school_id: UUID,
        counsellor_id: Optional[UUID] = None,
        student_id: Optional[UUID] = None,
        segment_codes: Optional[List[str]] = None,
        consultation_type_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
        include_shared_students: bool = True
    ) -> tuple[List[SearchResultItem], int]:
        """Search at segment level for more specific results"""
        from services.supabase_service import supabase

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Get accessible student IDs
        accessible_student_ids = None
        if counsellor_id and include_shared_students:
            accessible_student_ids = await self._get_accessible_student_ids(counsellor_id)

        sql = f"""
        SELECT
            se.extraction_id,
            se.segment_code,
            se.student_id,
            se.counsellor_id,
            se.school_id,
            1 - (se.embedding <=> '{embedding_str}'::extensions.vector) as similarity_score,
            se.embedded_content,
            me.created_at,
            me.consultation_type_id,
            COALESCE(me.edited_extraction_json, me.original_extraction_json) as extraction_data,
            p.full_name as patient_name,
            p.student_id as student_external_id,
            d.full_name as counsellor_name,
            ct.type_name as consultation_type_name
        FROM segment_embeddings se
        JOIN extractions me ON me.id = se.extraction_id
        LEFT JOIN students p ON p.id = se.student_id
        LEFT JOIN counsellors d ON d.id = se.counsellor_id
        LEFT JOIN consultation_types ct ON ct.id = me.consultation_type_id
        WHERE se.school_id = '{school_id}'
          AND se.model_id = '{model_id}'
        """

        # Add segment code filter
        if segment_codes:
            codes_str = ",".join(f"'{code}'" for code in segment_codes)
            sql += f" AND se.segment_code IN ({codes_str})"

        # Add other filters
        if counsellor_id:
            if accessible_student_ids:
                student_ids_str = ",".join(f"'{pid}'" for pid in accessible_student_ids)
                sql += f" AND (se.counsellor_id = '{counsellor_id}' OR se.student_id IN ({student_ids_str}))"
            else:
                sql += f" AND se.counsellor_id = '{counsellor_id}'"

        if student_id:
            sql += f" AND se.student_id = '{student_id}'"

        if consultation_type_id:
            sql += f" AND me.consultation_type_id = '{consultation_type_id}'"

        if date_from:
            sql += f" AND me.created_at >= '{date_from.isoformat()}'"

        if date_to:
            sql += f" AND me.created_at <= '{date_to.isoformat()}'"

        sql += f"""
        ORDER BY similarity_score DESC
        LIMIT {limit}
        OFFSET {offset}
        """

        result = supabase.rpc("exec_sql", {"sql_query": sql}).execute()
        raw_count = len(result.data) if result.data else 0
        result.data = _unwrap_exec_sql(result.data)
        logger.info(f"Segment search: raw_rows={raw_count}, unwrapped_rows={len(result.data) if result.data else 0}, "
                    f"segment_codes={segment_codes}")

        if not result.data:
            logger.warning("exec_sql RPC returned no results for segment search")
            return [], 0

        results = []
        for row in result.data:
            results.append(SearchResultItem(
                extraction_id=UUID(row["extraction_id"]),
                student_id=UUID(row["student_id"]) if row.get("student_id") else None,
                patient_name=row.get("patient_name"),
                student_external_id=row.get("student_external_id"),
                counsellor_id=UUID(row["counsellor_id"]) if row.get("counsellor_id") else None,
                counsellor_name=row.get("counsellor_name"),
                consultation_type_name=row.get("consultation_type_name"),
                created_at=row["created_at"],
                similarity_score=float(row["similarity_score"]),
                matched_segment_code=row.get("segment_code"),
                matched_content_preview=row.get("embedded_content", "")[:200] if row.get("embedded_content") else None,
                extraction_data=row.get("extraction_data")
            ))

        return results, len(results)

    async def _search_documents_fallback(
        self,
        school_id: UUID,
        counsellor_id: Optional[UUID] = None,
        student_id: Optional[UUID] = None,
        consultation_type_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[List[SearchResultItem], int]:
        """Fallback search without vector operations (returns by date)"""
        from services.supabase_service import supabase

        query = supabase.table("extractions")\
            .select(
                "id, student_id, counsellor_id, consultation_type_id, created_at, "
                "students(full_name, student_id), "
                "counsellors(full_name), "
                "consultation_types(type_name)"
            )\
            .order("created_at", desc=True)

        # Apply filters using the FK relationships
        # Note: school_id filter needs to go through counsellors
        if counsellor_id:
            query = query.eq("counsellor_id", str(counsellor_id))

        if student_id:
            query = query.eq("student_id", str(student_id))

        if consultation_type_id:
            query = query.eq("consultation_type_id", str(consultation_type_id))

        if date_from:
            query = query.gte("created_at", date_from.isoformat())

        if date_to:
            query = query.lte("created_at", date_to.isoformat())

        query = query.range(offset, offset + limit - 1)
        result = query.execute()

        results = []
        for row in result.data or []:
            patient = row.get("students") or {}
            doctor = row.get("counsellors") or {}
            ct = row.get("consultation_types") or {}

            results.append(SearchResultItem(
                extraction_id=UUID(row["id"]),
                student_id=UUID(row["student_id"]) if row.get("student_id") else None,
                patient_name=patient.get("full_name"),
                student_external_id=patient.get("student_id"),
                counsellor_id=UUID(row["counsellor_id"]) if row.get("counsellor_id") else None,
                counsellor_name=doctor.get("full_name"),
                consultation_type_name=ct.get("type_name"),
                created_at=row["created_at"],
                similarity_score=0.5  # Placeholder score
            ))

        return results, len(results)

    async def _get_accessible_student_ids(self, counsellor_id: UUID) -> List[str]:
        """Get student IDs that a counsellor has access to through sharing"""
        from services.supabase_service import supabase

        # Get students shared with this counsellor
        shared_result = supabase.table("student_sharing")\
            .select("student_id")\
            .eq("target_counsellor_id", str(counsellor_id))\
            .is_("revoked_at", "null")\
            .execute()

        student_ids = [row["student_id"] for row in (shared_result.data or [])]

        # Also get counsellor's own students
        own_result = supabase.table("extractions")\
            .select("student_id")\
            .eq("counsellor_id", str(counsellor_id))\
            .execute()

        for row in own_result.data or []:
            if row.get("student_id") and row["student_id"] not in student_ids:
                student_ids.append(row["student_id"])

        return student_ids


# Singleton instance
semantic_search_service = SemanticSearchService()

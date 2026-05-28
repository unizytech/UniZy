"""
Q&A Engine API Router

Endpoints for the RAG-based Q&A system:
- POST /api/v1/qa/query - Main Q&A query endpoint
- GET /api/v1/qa/suggested-questions - Get suggested questions
- GET /api/v1/qa/history - User's query history
- POST /api/v1/qa/export - Export results

Auth: Requires authenticated user (Admin + Web + EHR)
"""

import os
import logging
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Depends, Request

from models.qa_models import (
    QAQueryRequest,
    QAQueryResponse,
    SuggestedQuestionsResponse,
    QueryHistoryResponse,
    QueryHistoryItem,
    ExportRequest,
    ExportResponse,
    QueryIntent,
    ResponseFormat,
    QuestionCategory,
    SearchLevel,
    ReframedQuery,
    ReframeExpansion,
    ReframeCorrection,
    TemporalReference
)
from models.auth_models import ClientContext

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/qa",
    tags=["Q&A Engine"]
)

# Conditional auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import get_current_client
else:
    async def get_current_client(request: Request) -> ClientContext:
        """Stub for development without auth"""
        return ClientContext(
            client_type="admin",
            client_id=UUID("00000000-0000-0000-0000-000000000000"),
            client_name="dev_client",
            hospital_id=None,
            scopes=["qa:query", "qa:history"]
        )


# ============================================================================
# Main Query Endpoint
# ============================================================================

@router.post("/query", response_model=QAQueryResponse)
async def execute_query(
    request: QAQueryRequest,
    client: ClientContext = Depends(get_current_client)
):
    """
    Execute a natural language Q&A query.

    The query is classified into one of three intents:
    - **SEMANTIC**: Pattern detection, insights -> Narrative response
    - **HYBRID**: Search with filters -> Patient/extraction table
    - **SQL**: Analytics, counts -> Charts/stats

    **Query Examples:**
    - "What are common diagnoses in diabetic patients?" -> Narrative
    - "Show patients with hypertension from last month" -> Table
    - "How many extractions were done this week?" -> Chart

    **Auth:** Admin, Web, or EHR clients with hospital scoping.
    """
    from services.qa.query_reframer_service import query_reframer_service
    from services.qa.query_classifier_service import query_classifier_service
    from services.qa.semantic_search_service import semantic_search_service
    from services.qa.analytics_engine_service import analytics_engine_service
    from services.qa.qa_synthesis_service import qa_synthesis_service
    from services.qa.temporal_resolution_service import temporal_resolution_service
    from services.qa.patient_longitudinal_service import patient_longitudinal_service
    from services.supabase_service import supabase

    start_time = datetime.now(timezone.utc)

    try:
        # Get hospital_id from request (preferred) or resolve from hospital_code, or fall back to client context
        hospital_id = request.hospital_id
        if not hospital_id and request.hospital_code:
            hospital_response = (
                supabase.table("hospitals")
                .select("id")
                .eq("hospital_code", request.hospital_code)
                .eq("is_active", True)
                .execute()
            )
            if not hospital_response.data or len(hospital_response.data) == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Hospital not found or inactive"
                )
            hospital_id = UUID(hospital_response.data[0]["id"])
        if not hospital_id:
            hospital_id = client.hospital_id
        if not hospital_id:
            raise HTTPException(
                status_code=400,
                detail="Hospital context required for Q&A queries. Please provide hospital_id or hospital_code in request."
            )

        doctor_id = request.doctor_id

        # Resolve patient_id (external UHID or internal UUID) to internal UUID
        patient_id = None
        if request.patient_id:
            from routers.patient_history import resolve_patient_id
            patient_id = resolve_patient_id(request.patient_id, hospital_id=str(hospital_id) if hospital_id else None)
            if not patient_id:
                raise HTTPException(
                    status_code=404,
                    detail="Patient not found"
                )

        # Step 0: Reframe query (expand abbreviations, fix typos, normalize terms)
        reframed = await query_reframer_service.reframe(
            query=request.query,
            use_llm=True,
            prior_context=request.prior_context
        )

        if reframed.was_modified:
            logger.info(
                f"Query reframed: '{request.query}' -> '{reframed.reframed_query}' "
                f"(expansions={len(reframed.expansions)}, corrections={len(reframed.corrections)})"
            )

        # Use reframed query for classification
        query_for_classification = reframed.reframed_query

        # Step 1: Classify query
        classified = await query_classifier_service.classify(
            query=query_for_classification,
            hospital_id=hospital_id,
            prior_context=request.prior_context
        )

        logger.info(
            f"Query classified: intent={classified.intent.value}, "
            f"search_level={classified.search_level.value}, "
            f"format={classified.response_format.value}, "
            f"temporal_refs={len(classified.temporal_references or [])}, "
            f"comparison_mode={classified.comparison_mode}"
        )

        # Backup pattern detection for temporal/longitudinal queries
        # (in case LLM classifier misses them)
        import re

        # Pattern for multi-visit queries (e.g., "last 3 visits", "over the past 5 consultations")
        multi_visit_pattern = r'\b(?:last|past|previous)\s+(\d+)\s+(visits?|consultations?|appointments?)\b'
        multi_visit_match = re.search(multi_visit_pattern, request.query.lower())

        # Patterns for comparison queries (2-visit comparison)
        comparison_patterns = [
            r'\bcompare\b.*\b(previous|last)\s+(visit|consultation|appointment)\b',
            r'\bcompare\b.*\bwith\s+(previous|last)\b',
            r'\bchanged?\s+since\b',
            r'\bsince\s+(last|first|previous)\b',
            r'\bdifference\s+(?:from|since)\s+(last|previous)\b',
        ]

        # General temporal patterns (single visit reference — regex backup only)
        # The LLM classifier handles most temporal detection; these catch simple cases it might miss.
        temporal_patterns = [
            r'\blast\s+(visit|consultation|appointment)\b',
            r'\bprevious\s+(visit|consultation|appointment|prescription)\b',
            r'\bfirst\s+(visit|consultation|appointment)\b',
            r'\binitial\s+(visit|consultation)\b',
            r'\blast\s+time\b',
            r'\b(visit|consultation)\s+before\s+last\b',
            r'\bbefore\s+last\s+(visit|consultation)\b',
            r'\bsecond\s+(?:to\s+)?last\s+(visit|consultation)\b',
        ]

        query_lower = request.query.lower()
        is_multi_visit_query = bool(multi_visit_match)
        is_comparison_query = any(re.search(p, query_lower) for p in comparison_patterns)
        is_temporal_query = any(re.search(p, query_lower) for p in temporal_patterns)
        pattern_detected = is_multi_visit_query or is_comparison_query or is_temporal_query

        # Extract number of visits for multi-visit queries
        num_visits_requested = int(multi_visit_match.group(1)) if multi_visit_match else None

        # Import for temporal reference creation (needed in multiple places)
        from models.qa_models import TemporalReferenceType

        if pattern_detected and not classified.temporal_references:
            logger.info(f"Temporal pattern detected via regex backup: {request.query} "
                       f"(multi_visit={is_multi_visit_query}, comparison={is_comparison_query}, "
                       f"temporal={is_temporal_query}, num_visits={num_visits_requested})")
            # Create a generic temporal reference
            classified.temporal_references = [
                TemporalReference(
                    type=TemporalReferenceType.RELATIVE_VISIT,
                    raw_text="detected from query pattern",
                    visit_offset=-1
                )
            ]
            # Only set comparison_mode for actual comparison queries, NOT multi-visit queries
            classified.comparison_mode = is_comparison_query
            classified.requires_patient_history = True

        # Check if query requires patient context but none provided.
        # Only gate on temporal/comparison signals — NOT requires_patient_history alone,
        # since cross-patient queries like "common diagnoses across my patients" falsely
        # trigger requires_patient_history but don't need a specific patient.
        needs_patient = (
            classified.comparison_mode or
            (classified.temporal_references and len(classified.temporal_references) > 0) or
            pattern_detected  # Also check backup pattern
        )

        if needs_patient and not request.patient_id:
            # Return a helpful message instead of failing silently
            end_time = datetime.now(timezone.utc)
            total_time_ms = int((end_time - start_time).total_seconds() * 1000)

            return QAQueryResponse(
                success=True,
                query=request.query,
                intent=classified.intent,
                response_format=ResponseFormat.NARRATIVE,
                reframed_query=reframed.reframed_query if reframed.was_modified else None,
                reframe_expansions=reframed.expansions if reframed.expansions else None,
                reframe_corrections=reframed.corrections if reframed.corrections else None,
                narrative=(
                    "This query references specific visits or requires patient history. "
                    "Please select a **Doctor** first, then a **Patient** from the filters above "
                    "to enable temporal comparisons like 'last visit', 'previous consultation', or 'since first visit'."
                ),
                temporal_references=[
                    TemporalReference(
                        type=ref.type,
                        raw_text=ref.raw_text,
                        visit_offset=ref.visit_offset
                    ) for ref in (classified.temporal_references or [])
                ] if classified.temporal_references else None,
                reframe_time_ms=reframed.reframe_time_ms,
                total_time_ms=total_time_ms
            )

        # Step 2: Resolve temporal references if patient context is available
        temporal_resolution_time_ms = 0
        resolved_temporal_refs = None
        if classified.temporal_references and patient_id:
            temp_start = datetime.now(timezone.utc)
            try:
                resolved_temporal_refs = await temporal_resolution_service.resolve_references(
                    references=classified.temporal_references,
                    patient_id=patient_id,
                    hospital_id=hospital_id,
                    doctor_id=doctor_id,
                    current_extraction_id=request.extraction_id
                )
                logger.info(f"Resolved {len(resolved_temporal_refs)} temporal references")
            except Exception as e:
                logger.warning(f"Temporal resolution failed: {e}")
                resolved_temporal_refs = classified.temporal_references
            temp_end = datetime.now(timezone.utc)
            temporal_resolution_time_ms = int((temp_end - temp_start).total_seconds() * 1000)

        # Step 3: Handle multi-visit and comparison/longitudinal queries
        longitudinal_data = None
        longitudinal_time_ms = 0
        referenced_visits = None

        # Handle multi-visit queries (e.g., "last 3 visits") differently from comparison queries
        if is_multi_visit_query and patient_id:
            long_start = datetime.now(timezone.utc)
            try:
                # Use longitudinal summary for multi-visit queries
                num_visits = num_visits_requested or 3  # Default to 3 if not specified
                logger.info(f"Fetching longitudinal summary for {num_visits} visits")

                longitudinal_data = await patient_longitudinal_service.get_longitudinal_summary(
                    patient_id=patient_id,
                    hospital_id=hospital_id,
                    doctor_id=doctor_id,
                    num_visits=num_visits
                )

                if longitudinal_data and not longitudinal_data.get("error"):
                    # Prepare referenced visits from the summary
                    referenced_visits = longitudinal_data.get("visits", [])

                    # Generate narrative from multi-visit data
                    narrative = await patient_longitudinal_service.synthesize_multi_visit_narrative(
                        query=request.query,
                        longitudinal_data=longitudinal_data,
                        hospital_id=hospital_id
                    )

                    long_end = datetime.now(timezone.utc)
                    longitudinal_time_ms = int((long_end - long_start).total_seconds() * 1000)
                    total_time_ms = int((long_end - start_time).total_seconds() * 1000)

                    # Log query to history
                    await _log_query_history(
                        hospital_id=hospital_id,
                        doctor_id=doctor_id,
                        client=client,
                        query=request.query,
                        reframed=reframed,
                        intent=classified.intent,
                        response_format=ResponseFormat.NARRATIVE,
                        result_count=len(referenced_visits),
                        total_time_ms=total_time_ms
                    )

                    # Return multi-visit longitudinal response
                    return QAQueryResponse(
                        success=True,
                        query=request.query,
                        intent=classified.intent,
                        response_format=ResponseFormat.NARRATIVE,
                        reframed_query=reframed.reframed_query if reframed.was_modified else None,
                        reframe_expansions=reframed.expansions if reframed.expansions else None,
                        reframe_corrections=reframed.corrections if reframed.corrections else None,
                        narrative=narrative,
                        temporal_references=resolved_temporal_refs,
                        longitudinal_data=longitudinal_data,
                        referenced_visits=referenced_visits,
                        reframe_time_ms=reframed.reframe_time_ms,
                        temporal_resolution_time_ms=temporal_resolution_time_ms,
                        longitudinal_time_ms=longitudinal_time_ms,
                        total_time_ms=total_time_ms
                    )
            except Exception as e:
                logger.error(f"Multi-visit longitudinal query failed: {e}", exc_info=True)
                # Fall through to normal search flow
            long_end = datetime.now(timezone.utc)
            longitudinal_time_ms = int((long_end - long_start).total_seconds() * 1000)

        # Handle comparison queries (e.g., "what changed since last visit")
        elif classified.comparison_mode and patient_id and resolved_temporal_refs:
            long_start = datetime.now(timezone.utc)
            try:
                # Get baseline extraction from temporal references
                baseline_ref = next(
                    (ref for ref in resolved_temporal_refs if ref.resolved_extraction_id),
                    None
                )

                if baseline_ref and baseline_ref.resolved_extraction_id:
                    # Get changes since baseline visit
                    longitudinal_data = await patient_longitudinal_service.get_changes_since_visit(
                        patient_id=patient_id,
                        baseline_extraction_id=baseline_ref.resolved_extraction_id,
                        hospital_id=hospital_id,
                        current_extraction_id=request.extraction_id
                    )

                    # Prepare referenced visits for response
                    if longitudinal_data and not longitudinal_data.get("error"):
                        referenced_visits = [
                            longitudinal_data.get("baseline_visit"),
                            longitudinal_data.get("current_visit")
                        ]
                        referenced_visits = [v for v in referenced_visits if v]

                        # Generate narrative from longitudinal data
                        narrative = await patient_longitudinal_service.synthesize_narrative(
                            query=request.query,
                            longitudinal_data=longitudinal_data,
                            hospital_id=hospital_id
                        )

                        long_end = datetime.now(timezone.utc)
                        longitudinal_time_ms = int((long_end - long_start).total_seconds() * 1000)
                        total_time_ms = int((long_end - start_time).total_seconds() * 1000)

                        # Log query to history
                        await _log_query_history(
                            hospital_id=hospital_id,
                            doctor_id=doctor_id,
                            client=client,
                            query=request.query,
                            reframed=reframed,
                            intent=classified.intent,
                            response_format=ResponseFormat.NARRATIVE,
                            result_count=len(referenced_visits),
                            total_time_ms=total_time_ms
                        )

                        # Return longitudinal response
                        return QAQueryResponse(
                            success=True,
                            query=request.query,
                            intent=classified.intent,
                            response_format=ResponseFormat.NARRATIVE,
                            reframed_query=reframed.reframed_query if reframed.was_modified else None,
                            reframe_expansions=reframed.expansions if reframed.expansions else None,
                            reframe_corrections=reframed.corrections if reframed.corrections else None,
                            narrative=narrative,
                            temporal_references=resolved_temporal_refs,
                            longitudinal_data=longitudinal_data,
                            referenced_visits=referenced_visits,
                            reframe_time_ms=reframed.reframe_time_ms,
                            temporal_resolution_time_ms=temporal_resolution_time_ms,
                            longitudinal_time_ms=longitudinal_time_ms,
                            total_time_ms=total_time_ms
                        )
            except Exception as e:
                logger.error(f"Longitudinal query failed: {e}", exc_info=True)
                # Fall through to normal search flow
            long_end = datetime.now(timezone.utc)
            longitudinal_time_ms = int((long_end - long_start).total_seconds() * 1000)

        # Handle single-visit temporal queries (e.g., "what did I prescribe last time")
        # Use resolved_temporal_refs (from classifier OR regex backup) rather than
        # is_temporal_query (regex-only) so LLM-detected temporal refs also trigger this.
        elif (not is_multi_visit_query and not classified.comparison_mode
              and patient_id and resolved_temporal_refs):
            long_start = datetime.now(timezone.utc)
            try:
                # Find the resolved extraction_id from temporal references
                target_ref = next(
                    (ref for ref in resolved_temporal_refs if ref.resolved_extraction_id),
                    None
                )

                if target_ref and target_ref.resolved_extraction_id:
                    # Fetch data for the specific visit
                    visit_data = await patient_longitudinal_service.get_single_visit_data(
                        extraction_id=target_ref.resolved_extraction_id,
                        hospital_id=hospital_id
                    )

                    if visit_data and not visit_data.get("error"):
                        # Synthesize a focused narrative from the single visit
                        narrative = await patient_longitudinal_service.synthesize_single_visit_narrative(
                            query=request.query,
                            visit_data=visit_data,
                            hospital_id=hospital_id
                        )

                        referenced_visits = [visit_data.get("visit_info")]
                        referenced_visits = [v for v in referenced_visits if v]

                        long_end = datetime.now(timezone.utc)
                        longitudinal_time_ms = int((long_end - long_start).total_seconds() * 1000)
                        total_time_ms = int((long_end - start_time).total_seconds() * 1000)

                        # Log query to history
                        await _log_query_history(
                            hospital_id=hospital_id,
                            doctor_id=doctor_id,
                            client=client,
                            query=request.query,
                            reframed=reframed,
                            intent=classified.intent,
                            response_format=ResponseFormat.NARRATIVE,
                            result_count=1,
                            total_time_ms=total_time_ms
                        )

                        return QAQueryResponse(
                            success=True,
                            query=request.query,
                            intent=classified.intent,
                            response_format=ResponseFormat.NARRATIVE,
                            reframed_query=reframed.reframed_query if reframed.was_modified else None,
                            reframe_expansions=reframed.expansions if reframed.expansions else None,
                            reframe_corrections=reframed.corrections if reframed.corrections else None,
                            narrative=narrative,
                            temporal_references=resolved_temporal_refs,
                            referenced_visits=referenced_visits,
                            referenced_extraction_ids=[str(target_ref.resolved_extraction_id)],
                            reframe_time_ms=reframed.reframe_time_ms,
                            temporal_resolution_time_ms=temporal_resolution_time_ms,
                            longitudinal_time_ms=longitudinal_time_ms,
                            total_time_ms=total_time_ms
                        )
            except Exception as e:
                logger.error(f"Single-visit temporal query failed: {e}", exc_info=True)
                # Fall through to normal search flow
            long_end = datetime.now(timezone.utc)
            longitudinal_time_ms = int((long_end - long_start).total_seconds() * 1000)

        # Step 4: Execute based on intent (original flow)
        if classified.intent == QueryIntent.SQL:
            # Analytics query -> Text-to-SQL (use reframed query)
            analytics_result = await analytics_engine_service.execute_analytics_query(
                query=query_for_classification,
                hospital_id=hospital_id,
                doctor_id=doctor_id,
                patient_id=patient_id
            )

            end_time = datetime.now(timezone.utc)
            total_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Log query to history (with reframing info)
            await _log_query_history(
                hospital_id=hospital_id,
                doctor_id=doctor_id,
                client=client,
                query=request.query,
                reframed=reframed,
                intent=classified.intent,
                response_format=classified.response_format,
                result_count=1 if analytics_result.get("success") else 0,
                total_time_ms=total_time_ms
            )

            if not analytics_result.get("success"):
                return QAQueryResponse(
                    success=False,
                    query=request.query,
                    intent=classified.intent,
                    response_format=classified.response_format,
                    reframed_query=reframed.reframed_query if reframed.was_modified else None,
                    reframe_expansions=reframed.expansions if reframed.expansions else None,
                    reframe_corrections=reframed.corrections if reframed.corrections else None,
                    error_message=analytics_result.get("error", "Analytics query failed"),
                    reframe_time_ms=reframed.reframe_time_ms,
                    total_time_ms=total_time_ms
                )

            return QAQueryResponse(
                success=True,
                query=request.query,
                intent=classified.intent,
                response_format=classified.response_format,
                reframed_query=reframed.reframed_query if reframed.was_modified else None,
                reframe_expansions=reframed.expansions if reframed.expansions else None,
                reframe_corrections=reframed.corrections if reframed.corrections else None,
                chart=analytics_result.get("chart"),
                stat_card=analytics_result.get("stat_card"),
                reframe_time_ms=reframed.reframe_time_ms,
                total_time_ms=total_time_ms
            )

        else:
            # Semantic or Hybrid -> Vector search
            # Normalize segment codes to match stored camelCase variants
            segment_codes_for_search = classified.segment_codes
            if segment_codes_for_search:
                from services.qa.query_classifier_service import normalize_segment_codes
                segment_codes_for_search = normalize_segment_codes(segment_codes_for_search)
                logger.info(f"Segment codes: {classified.segment_codes} -> expanded: {segment_codes_for_search}")

            # Use reframed query for embedding search
            search_result = await semantic_search_service.search(
                query=query_for_classification,
                hospital_id=hospital_id,
                doctor_id=doctor_id,
                patient_id=patient_id,
                search_level=classified.search_level,
                segment_codes=segment_codes_for_search,
                consultation_type_id=request.consultation_type_id,
                date_from=request.date_from,
                date_to=request.date_to,
                limit=request.limit,
                offset=request.offset
            )

            results = search_result.get("results", [])
            total_count = search_result.get("total_count", len(results))
            embed_time_ms = search_result.get("embedding_time_ms", 0)
            search_time_ms = search_result.get("search_time_ms", 0)

            # Step 3: Format response based on intent
            if classified.intent == QueryIntent.SEMANTIC:
                # Synthesize narrative (use original query for context, reframed for search)
                synthesis_result = await qa_synthesis_service.synthesize(
                    query=request.query,
                    results=results,
                    total_count=total_count,
                    hospital_id=hospital_id,
                    prior_context=request.prior_context
                )

                end_time = datetime.now(timezone.utc)
                total_time_ms = int((end_time - start_time).total_seconds() * 1000)

                await _log_query_history(
                    hospital_id=hospital_id,
                    doctor_id=doctor_id,
                    client=client,
                    query=request.query,
                    reframed=reframed,
                    intent=classified.intent,
                    response_format=ResponseFormat.NARRATIVE,
                    result_count=total_count,
                    total_time_ms=total_time_ms
                )

                # Filter results to only those referenced in narrative (if available)
                referenced_ids = synthesis_result.get("referenced_extraction_ids", [])
                if referenced_ids:
                    # Show referenced results first, then others
                    referenced_results = [r for r in results if str(r.extraction_id) in referenced_ids]
                    other_results = [r for r in results if str(r.extraction_id) not in referenced_ids]
                    display_results = referenced_results + other_results[:max(0, 5 - len(referenced_results))]
                else:
                    display_results = results[:5]

                return QAQueryResponse(
                    success=True,
                    query=request.query,
                    intent=classified.intent,
                    response_format=ResponseFormat.NARRATIVE,
                    reframed_query=reframed.reframed_query if reframed.was_modified else None,
                    reframe_expansions=reframed.expansions if reframed.expansions else None,
                    reframe_corrections=reframed.corrections if reframed.corrections else None,
                    narrative=synthesis_result.get("narrative"),
                    results=display_results,
                    total_count=total_count,
                    referenced_extraction_ids=referenced_ids,
                    temporal_references=resolved_temporal_refs,
                    reframe_time_ms=reframed.reframe_time_ms,
                    temporal_resolution_time_ms=temporal_resolution_time_ms if temporal_resolution_time_ms else None,
                    embedding_time_ms=embed_time_ms,
                    search_time_ms=search_time_ms,
                    synthesis_time_ms=synthesis_result.get("synthesis_time_ms", 0),
                    total_time_ms=total_time_ms
                )

            else:  # HYBRID -> Table response
                end_time = datetime.now(timezone.utc)
                total_time_ms = int((end_time - start_time).total_seconds() * 1000)

                await _log_query_history(
                    hospital_id=hospital_id,
                    doctor_id=doctor_id,
                    client=client,
                    query=request.query,
                    reframed=reframed,
                    intent=classified.intent,
                    response_format=ResponseFormat.TABLE,
                    result_count=total_count,
                    total_time_ms=total_time_ms
                )

                return QAQueryResponse(
                    success=True,
                    query=request.query,
                    intent=classified.intent,
                    response_format=ResponseFormat.TABLE,
                    reframed_query=reframed.reframed_query if reframed.was_modified else None,
                    reframe_expansions=reframed.expansions if reframed.expansions else None,
                    reframe_corrections=reframed.corrections if reframed.corrections else None,
                    results=results,
                    total_count=total_count,
                    temporal_references=resolved_temporal_refs,
                    reframe_time_ms=reframed.reframe_time_ms,
                    temporal_resolution_time_ms=temporal_resolution_time_ms if temporal_resolution_time_ms else None,
                    embedding_time_ms=embed_time_ms,
                    search_time_ms=search_time_ms,
                    total_time_ms=total_time_ms
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Q&A query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Query execution failed")


# ============================================================================
# Suggested Questions
# ============================================================================

@router.get("/suggested-questions", response_model=SuggestedQuestionsResponse)
async def get_suggested_questions(
    category: Optional[QuestionCategory] = Query(
        None,
        description="Filter by category: clinical, risk, referrals, interventions, triage, analytics"
    ),
    client: ClientContext = Depends(get_current_client)
):
    """
    Get suggested questions for the Q&A interface.

    Returns pre-defined question templates that users can click to execute.

    **Categories:**
    - `clinical`: Clinical insights, diagnoses, prescriptions
    - `risk`: Severity assessments, compliance risks
    - `referrals`: Allied health referrals, specialist recommendations
    - `interventions`: Intervention tracking, conversion opportunities
    - `triage`: Red flags, urgent cases
    - `analytics`: Counts, trends, statistics
    """
    from services.qa.suggested_questions_service import suggested_questions_service

    # Determine user role for filtering
    role = client.user_role or "admin"

    return suggested_questions_service.get_questions_for_role(
        role=role,
        category=category
    )


# ============================================================================
# Query History
# ============================================================================

@router.get("/history", response_model=QueryHistoryResponse)
async def get_query_history(
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    page: int = Query(1, ge=1, description="Page number"),
    client: ClientContext = Depends(get_current_client)
):
    """
    Get user's Q&A query history.

    Shows recent queries with their intents and response times.
    """
    from services.supabase_service import supabase

    hospital_id = client.hospital_id
    doctor_id = None  # Could filter by user if needed

    offset = (page - 1) * limit

    query = supabase.table("qa_query_history")\
        .select("*")\
        .order("created_at", desc=True)

    if hospital_id:
        query = query.eq("hospital_id", str(hospital_id))

    query = query.range(offset, offset + limit - 1)
    result = query.execute()

    history = [
        QueryHistoryItem(
            id=UUID(row["id"]),
            query_text=row["query_text"],
            query_intent=QueryIntent(row["query_intent"]) if row.get("query_intent") else None,
            result_count=row.get("result_count", 0),
            response_format=ResponseFormat(row["response_format"]) if row.get("response_format") else None,
            total_time_ms=row.get("total_time_ms"),
            created_at=row["created_at"],
            # Reframing info
            reframed_query=row.get("reframed_query"),
            reframe_expansions=[
                ReframeExpansion(**e) for e in row.get("reframe_expansions", []) or []
            ] if row.get("reframe_expansions") else None,
            reframe_corrections=[
                ReframeCorrection(**c) for c in row.get("reframe_corrections", []) or []
            ] if row.get("reframe_corrections") else None,
            reframe_confidence=row.get("reframe_confidence"),
            reframe_time_ms=row.get("reframe_time_ms")
        )
        for row in (result.data or [])
    ]

    # Get total count
    count_result = supabase.table("qa_query_history")\
        .select("id", count="exact")
    if hospital_id:
        count_result = count_result.eq("hospital_id", str(hospital_id))
    count_result = count_result.execute()
    total_count = count_result.count or 0

    return QueryHistoryResponse(
        history=history,
        total_count=total_count,
        page=page,
        page_size=limit
    )


# ============================================================================
# Export
# ============================================================================

@router.post("/export", response_model=ExportResponse)
async def export_results(
    request: ExportRequest,
    client: ClientContext = Depends(get_current_client)
):
    """
    Export Q&A search results to CSV or PDF.

    **Formats:**
    - `csv`: Comma-separated values
    - `pdf`: PDF document (not yet implemented)
    """
    import csv
    import io

    if request.format == "csv":
        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Patient Name",
            "Patient ID",
            "Doctor",
            "Consultation Type",
            "Date",
            "Similarity Score"
        ])

        # Data rows
        for result in request.results:
            writer.writerow([
                result.patient_name or "",
                result.patient_external_id or "",
                result.doctor_name or "",
                result.consultation_type_name or "",
                str(result.created_at)[:10] if result.created_at else "",
                f"{result.similarity_score:.2f}"
            ])

        csv_content = output.getvalue()

        return ExportResponse(
            success=True,
            format="csv",
            filename=f"qa_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            content=csv_content
        )

    elif request.format == "pdf":
        return ExportResponse(
            success=False,
            format="pdf",
            filename="",
            error_message="PDF export not yet implemented"
        )

    else:
        return ExportResponse(
            success=False,
            format=request.format,
            filename="",
            error_message=f"Unsupported format: {request.format}"
        )


# ============================================================================
# Patient Visits (for temporal/longitudinal queries)
# ============================================================================

@router.get("/patients/{patient_id}/visits")
async def get_patient_visits(
    patient_id: str,
    hospital_id: Optional[UUID] = Query(None, description="Hospital ID filter (used for auth context only)"),
    doctor_id: Optional[UUID] = Query(None, description="Doctor ID filter"),
    consultation_type_id: Optional[UUID] = Query(None, description="Consultation type filter"),
    limit: int = Query(20, ge=1, le=100, description="Number of visits to return"),
    client: ClientContext = Depends(get_current_client)
):
    """
    Get a patient's consultation visits for the Q&A visit selector.

    Returns a list of visits with extraction_id, date, consultation type, and doctor.
    Ordered by date DESC (most recent first).

    **patient_id** can be either external patient ID (UHID) or internal UUID.

    **Use Cases:**
    - Populate visit selector dropdown in Q&A interface
    - Select specific visits for temporal queries
    - Filter Q&A scope to a specific consultation
    """
    from services.supabase_service import supabase
    from routers.patient_history import resolve_patient_id_or_404

    try:
        # Use hospital from request or client context for filtering
        effective_hospital_id = hospital_id or client.hospital_id

        # Resolve external patient_id (UHID) or internal UUID to database UUID
        # Scope by hospital to prevent cross-hospital patient leakage
        resolve_hospital = str(effective_hospital_id) if effective_hospital_id else None
        if not resolve_hospital and doctor_id:
            from services.supabase_service import get_doctor_hospital_id_cached
            resolve_hospital = get_doctor_hospital_id_cached(str(doctor_id))
        resolved_patient_id = resolve_patient_id_or_404(patient_id, hospital_id=resolve_hospital)

        # Note: medical_extractions doesn't have hospital_id column
        # Filter by hospital through doctors.hospital_id join

        query = supabase.table("medical_extractions")\
            .select(
                "id, created_at, consultation_type_id, doctor_id, "
                "consultation_types(type_code, type_name), doctors!inner(full_name, hospital_id)"
            )\
            .eq("patient_id", str(resolved_patient_id))\
            .order("created_at", desc=True)\
            .limit(limit)

        # Filter by hospital through doctors table
        if effective_hospital_id:
            query = query.eq("doctors.hospital_id", str(effective_hospital_id))

        if doctor_id:
            query = query.eq("doctor_id", str(doctor_id))

        if consultation_type_id:
            query = query.eq("consultation_type_id", str(consultation_type_id))

        result = query.execute()

        visits = []
        for row in (result.data or []):
            ct = row.get("consultation_types") or {}
            doc = row.get("doctors") or {}
            visits.append({
                "extraction_id": row["id"],
                "created_at": row["created_at"],
                "consultation_type_id": row.get("consultation_type_id"),
                "consultation_type_code": ct.get("type_code"),
                "consultation_type_name": ct.get("type_name"),
                "doctor_id": row.get("doctor_id"),
                "doctor_name": doc.get("full_name")
            })

        return {
            "success": True,
            "patient_id": str(patient_id),
            "visits": visits,
            "count": len(visits)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get patient visits: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get patient visits")


# ============================================================================
# Helper Functions
# ============================================================================

async def _log_query_history(
    hospital_id: UUID,
    doctor_id: Optional[UUID],
    client: ClientContext,
    query: str,
    reframed: ReframedQuery,
    intent: QueryIntent,
    response_format: ResponseFormat,
    result_count: int,
    total_time_ms: int
):
    """Log query to history table with reframing details"""
    from services.supabase_service import supabase

    try:
        # Build reframing data for storage
        reframe_expansions = None
        reframe_corrections = None

        if reframed.expansions:
            reframe_expansions = [
                {"original": e.original, "expanded": e.expanded, "category": e.category}
                for e in reframed.expansions
            ]

        if reframed.corrections:
            reframe_corrections = [
                {"original": c.original, "corrected": c.corrected, "category": c.category}
                for c in reframed.corrections
            ]

        supabase.table("qa_query_history").insert({
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id) if doctor_id else None,
            "user_role": client.user_role or client.client_type,
            "query_text": query,
            "query_intent": intent.value,
            "response_format": response_format.value,
            "result_count": result_count,
            "total_time_ms": total_time_ms,
            # Reframing fields
            "reframed_query": reframed.reframed_query if reframed.was_modified else None,
            "reframe_expansions": reframe_expansions,
            "reframe_corrections": reframe_corrections,
            "reframe_confidence": float(reframed.confidence) if reframed.was_modified else None,
            "reframe_time_ms": reframed.reframe_time_ms
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to log query history: {e}")

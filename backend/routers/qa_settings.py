"""
Q&A Settings API Router

Admin endpoints for Q&A Engine configuration:
- GET /api/v1/qa/settings/embedding-models - List available models
- GET /api/v1/qa/settings/current-model - Get active model
- POST /api/v1/qa/settings/embedding-model - Set model (admin only)
- POST /api/v1/qa/settings/reembed - Trigger re-embedding (admin only)

Auth: Admin only for write operations
"""

import os
import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Depends, Request

from models.qa_models import (
    EmbeddingModelResponse,
    EmbeddingModelsListResponse,
    SetEmbeddingModelRequest,
    ReembeddingJobRequest,
    ReembeddingJobResponse,
    QAEngineSettings,
    UpdateQASettingsRequest
)
from models.auth_models import ClientContext

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/qa/settings",
    tags=["Q&A Settings"]
)

# Conditional auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import require_admin, get_current_client
else:
    async def require_admin(request: Request) -> ClientContext:
        """Stub for development without auth"""
        return ClientContext(
            client_type="admin",
            client_id=UUID("00000000-0000-0000-0000-000000000000"),
            client_name="dev_admin",
            school_id=None,
            user_role="super_admin",
            scopes=["admin:*"]
        )

    async def get_current_client(request: Request) -> ClientContext:
        return await require_admin(request)


# ============================================================================
# Embedding Models
# ============================================================================

@router.get("/embedding-models", response_model=EmbeddingModelsListResponse)
async def list_embedding_models(
    active_only: bool = Query(True, description="Only return active models"),
    client: ClientContext = Depends(get_current_client)
):
    """
    List available embedding models.

    Returns all configured embedding providers:
    - Cohere embed-v4 (healthcare fine-tuned, default)
    - OpenAI text-embedding-3-large (highest accuracy)
    - OpenAI text-embedding-3-small (cost-effective)
    - Gemini (integrated)
    """
    from services.supabase_service import supabase

    query = supabase.table("embedding_models")\
        .select("*")\
        .order("is_default", desc=True)\
        .order("model_name")

    if active_only:
        query = query.eq("is_active", True)

    result = query.execute()

    models = [
        EmbeddingModelResponse(
            id=UUID(row["id"]),
            model_code=row["model_code"],
            model_name=row["model_name"],
            provider=row["provider"],
            dimensions=row["dimensions"],
            description=row.get("description"),
            is_default=row.get("is_default", False),
            is_active=row.get("is_active", True),
            price_per_million_tokens=float(row["price_per_million_tokens"]) if row.get("price_per_million_tokens") else None,
            max_tokens=row.get("max_tokens")
        )
        for row in (result.data or [])
    ]

    return EmbeddingModelsListResponse(
        models=models,
        count=len(models)
    )


@router.get("/current-model", response_model=EmbeddingModelResponse)
async def get_current_model(
    school_id: Optional[UUID] = Query(None, description="School ID (optional)"),
    client: ClientContext = Depends(get_current_client)
):
    """
    Get the currently active embedding model.

    If school_id is provided, returns the model configured for that school.
    Otherwise, returns the global default model.
    """
    from services.qa.embedding_service import embedding_service

    # Use school from client context if not provided
    effective_school_id = school_id or client.school_id

    model_config = await embedding_service.get_active_model(effective_school_id)

    return EmbeddingModelResponse(
        id=UUID(model_config["id"]) if model_config.get("id") else UUID("00000000-0000-0000-0000-000000000000"),
        model_code=model_config["model_code"],
        model_name=model_config["model_name"],
        provider=model_config["provider"],
        dimensions=model_config["dimensions"],
        is_default=True,
        is_active=True
    )


@router.post("/embedding-model")
async def set_embedding_model(
    request: SetEmbeddingModelRequest,
    school_id: UUID = Query(..., description="School ID to configure"),
    client: ClientContext = Depends(require_admin)
):
    """
    Set the active embedding model for a school.

    **Admin only.** Triggers re-embedding of existing extractions.

    **Available models:**
    - `cohere_v4` - Healthcare fine-tuned (recommended)
    - `openai_large` - Highest accuracy (3072 dims)
    - `openai_small` - Cost-effective
    - `gemini` - Fast and free tier available
    """
    from services.supabase_service import supabase

    # Verify model exists
    model_result = supabase.table("embedding_models")\
        .select("id, model_name")\
        .eq("model_code", request.model_code)\
        .eq("is_active", True)\
        .limit(1)\
        .execute()

    if not model_result.data:
        raise HTTPException(
            status_code=404,
            detail="Model not found or inactive"
        )

    model = model_result.data[0]
    model_id = model["id"]

    # Upsert school settings
    settings_data = {
        "school_id": str(school_id),
        "embedding_model_id": model_id
    }

    supabase.table("qa_engine_settings")\
        .upsert(settings_data, on_conflict="school_id")\
        .execute()

    logger.info(f"Set embedding model {request.model_code} for school {school_id}")

    return {
        "success": True,
        "message": f"Embedding model set to {model['model_name']}",
        "model_code": request.model_code,
        "school_id": str(school_id),
        "note": "Existing embeddings will need to be re-generated. Use POST /reembed to trigger."
    }


# ============================================================================
# Re-embedding
# ============================================================================

@router.post("/reembed", response_model=ReembeddingJobResponse)
async def trigger_reembedding(
    request: ReembeddingJobRequest,
    client: ClientContext = Depends(require_admin)
):
    """
    Trigger re-embedding of all extractions for a school.

    **Admin only.** Runs as a background job.

    Use this after changing the embedding model to update all vectors.
    """
    from services.qa.embedding_job_service import embedding_job_service

    result = await embedding_job_service.queue_reembedding_job(
        school_id=request.school_id,
        model_code=request.model_code,
        force=True
    )

    if not result.get("success", False):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Failed to start re-embedding job")
        )

    return ReembeddingJobResponse(
        success=True,
        job_id=result.get("job_id"),
        message=result.get("message", "Re-embedding job started"),
        extraction_count=result.get("extraction_count")
    )


@router.get("/reembed/status/{job_id}")
async def get_reembedding_status(
    job_id: str,
    client: ClientContext = Depends(get_current_client)
):
    """
    Get status of a re-embedding job.
    """
    from services.qa.embedding_job_service import embedding_job_service

    status = embedding_job_service.get_job_status(job_id)

    if not status:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    return {
        "job_id": job_id,
        **status
    }


# ============================================================================
# Q&A Engine Settings
# ============================================================================

@router.get("/school/{school_id}", response_model=QAEngineSettings)
async def get_school_settings(
    school_id: UUID,
    client: ClientContext = Depends(get_current_client)
):
    """
    Get Q&A Engine settings for a school.
    """
    from services.supabase_service import supabase

    result = supabase.table("qa_engine_settings")\
        .select("*, embedding_models(model_code, model_name)")\
        .eq("school_id", str(school_id))\
        .limit(1)\
        .execute()

    if not result.data:
        # Return defaults
        return QAEngineSettings(
            school_id=school_id,
            embedding_model_id=UUID("00000000-0000-0000-0000-000000000000"),
            embedding_model_code="cohere_v4",
            embedding_model_name="Cohere Embed v4 (Default)",
            is_enabled=True,
            allow_analytics_queries=True,
            allow_cross_counsellor_search=False,
            max_results_per_query=20,
            max_queries_per_day=1000
        )

    row = result.data[0]
    model = row.get("embedding_models") or {}

    return QAEngineSettings(
        school_id=UUID(row["school_id"]),
        embedding_model_id=UUID(row["embedding_model_id"]),
        embedding_model_code=model.get("model_code"),
        embedding_model_name=model.get("model_name"),
        is_enabled=row.get("is_enabled", True),
        allow_analytics_queries=row.get("allow_analytics_queries", True),
        allow_cross_counsellor_search=row.get("allow_cross_counsellor_search", False),
        max_results_per_query=row.get("max_results_per_query", 20),
        max_queries_per_day=row.get("max_queries_per_day", 1000)
    )


@router.patch("/school/{school_id}")
async def update_school_settings(
    school_id: UUID,
    request: UpdateQASettingsRequest,
    client: ClientContext = Depends(require_admin)
):
    """
    Update Q&A Engine settings for a school.

    **Admin only.**
    """
    from services.supabase_service import supabase

    update_data = {}
    if request.embedding_model_id is not None:
        update_data["embedding_model_id"] = str(request.embedding_model_id)
    if request.is_enabled is not None:
        update_data["is_enabled"] = request.is_enabled
    if request.allow_analytics_queries is not None:
        update_data["allow_analytics_queries"] = request.allow_analytics_queries
    if request.allow_cross_counsellor_search is not None:
        update_data["allow_cross_counsellor_search"] = request.allow_cross_counsellor_search
    if request.max_results_per_query is not None:
        update_data["max_results_per_query"] = request.max_results_per_query
    if request.max_queries_per_day is not None:
        update_data["max_queries_per_day"] = request.max_queries_per_day

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Upsert settings
    update_data["school_id"] = str(school_id)

    supabase.table("qa_engine_settings")\
        .upsert(update_data, on_conflict="school_id")\
        .execute()

    return {
        "success": True,
        "message": "Settings updated",
        "school_id": str(school_id)
    }

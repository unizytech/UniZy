"""
Usage Analytics Router

Provides endpoints for aggregated LLM usage analytics:
- Summary by API client, hospital, or doctor
- Total cost, recording hours, and token usage
- Date range filtering
- Model pricing management (view, update, refresh from web)
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from models.auth_models import ClientContext
from services.supabase_service import supabase, retry_on_network_error
from dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/usage", tags=["Usage Analytics"])

# Separate router for model pricing endpoints
models_router = APIRouter(prefix="/api/v1/models", tags=["Model Pricing"])


# ============================================================================
# Response Models
# ============================================================================

class UsageSummaryItem(BaseModel):
    """Individual usage summary item for a group (API client, hospital, or doctor)."""
    group_id: UUID
    group_name: str
    group_type: str  # client_type for api_client, "hospital" for hospital, specialization for doctor
    hospital_id: Optional[UUID] = None
    hospital_name: Optional[str] = None
    total_api_calls: int
    total_sessions: int
    total_cost_usd: float
    total_cache_savings_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_recording_hours: float
    total_transcription_hours: float
    avg_cache_hit_ratio: Optional[float] = None
    error_count: int
    first_usage_at: Optional[datetime] = None
    last_usage_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UsageTotals(BaseModel):
    """Aggregate totals across all filtered data."""
    total_api_calls: int
    total_sessions: int
    total_cost_usd: float
    total_cache_savings_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_recording_hours: float
    unique_doctors: int
    unique_hospitals: int
    unique_api_clients: int


class UsageSummaryResponse(BaseModel):
    """Response for usage summary endpoint."""
    items: List[UsageSummaryItem]
    totals: UsageTotals
    group_by: str
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class APIClientOption(BaseModel):
    """API client option for dropdown."""
    id: UUID
    client_name: str
    client_type: str
    hospital_id: Optional[UUID] = None
    hospital_name: Optional[str] = None


class HospitalOption(BaseModel):
    """Hospital option for dropdown."""
    id: UUID
    hospital_name: str
    hospital_code: Optional[str] = None


class DoctorOption(BaseModel):
    """Doctor option for dropdown."""
    id: UUID
    full_name: str
    specialization: Optional[str] = None
    hospital_id: Optional[UUID] = None
    hospital_name: Optional[str] = None


class FilterOptionsResponse(BaseModel):
    """Response with filter dropdown options."""
    api_clients: List[APIClientOption]
    hospitals: List[HospitalOption]
    doctors: List[DoctorOption]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    group_by: str = Query("doctor", description="Group by: api_client, hospital, doctor"),
    date_from: Optional[datetime] = Query(None, description="Start date (inclusive)"),
    date_to: Optional[datetime] = Query(None, description="End date (exclusive)"),
    api_client_id: Optional[UUID] = Query(None, description="Filter by API client"),
    hospital_id: Optional[UUID] = Query(None, description="Filter by hospital"),
    doctor_id: Optional[UUID] = Query(None, description="Filter by doctor"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    client: ClientContext = Depends(require_admin),
):
    """
    Get aggregated usage summary by API client, hospital, or doctor.

    **Admin only** - Provides comprehensive usage analytics for billing and monitoring.

    **Group by options:**
    - `api_client`: Aggregate by API client (EHR integrations, mobile apps, etc.)
    - `hospital`: Aggregate by hospital
    - `doctor`: Aggregate by individual doctor

    **Returns:**
    - List of usage items with costs, recording hours, and token usage
    - Aggregate totals across all filtered data
    """
    if group_by not in ("api_client", "hospital", "doctor"):
        raise HTTPException(
            status_code=400,
            detail="Invalid group_by value. Must be: api_client, hospital, or doctor"
        )

    try:
        # Call the RPC function for summary items
        result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_usage_summary",
                {
                    "p_group_by": group_by,
                    "p_date_from": date_from.isoformat() if date_from else None,
                    "p_date_to": date_to.isoformat() if date_to else None,
                    "p_api_client_id": str(api_client_id) if api_client_id else None,
                    "p_hospital_id": str(hospital_id) if hospital_id else None,
                    "p_doctor_id": str(doctor_id) if doctor_id else None,
                    "p_limit": limit,
                    "p_offset": offset,
                }
            ).execute()
        )

        items = []
        for row in result.data or []:
            items.append(UsageSummaryItem(
                group_id=UUID(row["group_id"]) if row.get("group_id") else None,
                group_name=row.get("group_name") or "Unknown",
                group_type=row.get("group_type") or "",
                hospital_id=UUID(row["hospital_id"]) if row.get("hospital_id") else None,
                hospital_name=row.get("hospital_name"),
                total_api_calls=int(row.get("total_api_calls") or 0),
                total_sessions=int(row.get("total_sessions") or 0),
                total_cost_usd=float(row.get("total_cost_usd") or 0),
                total_cache_savings_usd=float(row.get("total_cache_savings_usd") or 0),
                total_input_tokens=int(row.get("total_input_tokens") or 0),
                total_output_tokens=int(row.get("total_output_tokens") or 0),
                total_cached_tokens=int(row.get("total_cached_tokens") or 0),
                total_recording_hours=float(row.get("total_recording_hours") or 0),
                total_transcription_hours=float(row.get("total_transcription_hours") or 0),
                avg_cache_hit_ratio=float(row["avg_cache_hit_ratio"]) if row.get("avg_cache_hit_ratio") else None,
                error_count=int(row.get("error_count") or 0),
                first_usage_at=row.get("first_usage_at"),
                last_usage_at=row.get("last_usage_at"),
            ))

        # Call the RPC function for totals
        totals_result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_usage_totals",
                {
                    "p_date_from": date_from.isoformat() if date_from else None,
                    "p_date_to": date_to.isoformat() if date_to else None,
                    "p_api_client_id": str(api_client_id) if api_client_id else None,
                    "p_hospital_id": str(hospital_id) if hospital_id else None,
                    "p_doctor_id": str(doctor_id) if doctor_id else None,
                }
            ).execute()
        )

        totals_row = totals_result.data[0] if totals_result.data else {}
        totals = UsageTotals(
            total_api_calls=int(totals_row.get("total_api_calls") or 0),
            total_sessions=int(totals_row.get("total_sessions") or 0),
            total_cost_usd=float(totals_row.get("total_cost_usd") or 0),
            total_cache_savings_usd=float(totals_row.get("total_cache_savings_usd") or 0),
            total_input_tokens=int(totals_row.get("total_input_tokens") or 0),
            total_output_tokens=int(totals_row.get("total_output_tokens") or 0),
            total_recording_hours=float(totals_row.get("total_recording_hours") or 0),
            unique_doctors=int(totals_row.get("unique_doctors") or 0),
            unique_hospitals=int(totals_row.get("unique_hospitals") or 0),
            unique_api_clients=int(totals_row.get("unique_api_clients") or 0),
        )

        return UsageSummaryResponse(
            items=items,
            totals=totals,
            group_by=group_by,
            date_from=date_from,
            date_to=date_to,
        )

    except Exception as e:
        logger.error(f"Error fetching usage summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch usage summary")


@router.get("/filters", response_model=FilterOptionsResponse)
async def get_filter_options(
    client: ClientContext = Depends(require_admin),
):
    """
    Get dropdown options for filtering usage data.

    **Admin only** - Returns lists of API clients, hospitals, and doctors for filter dropdowns.
    """
    try:
        # Get API clients
        api_clients_result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .select("id, client_name, client_type, hospital_id, hospitals(hospital_name)")
            .eq("is_active", True)
            .order("client_name")
            .execute()
        )

        api_clients = []
        for row in api_clients_result.data or []:
            api_clients.append(APIClientOption(
                id=UUID(row["id"]),
                client_name=row["client_name"],
                client_type=row["client_type"],
                hospital_id=UUID(row["hospital_id"]) if row.get("hospital_id") else None,
                hospital_name=row.get("hospitals", {}).get("hospital_name") if row.get("hospitals") else None,
            ))

        # Get hospitals
        hospitals_result = retry_on_network_error(
            lambda: supabase.table("hospitals")
            .select("id, hospital_name, hospital_code")
            .order("hospital_name")
            .execute()
        )

        hospitals = []
        for row in hospitals_result.data or []:
            hospitals.append(HospitalOption(
                id=UUID(row["id"]),
                hospital_name=row["hospital_name"],
                hospital_code=row.get("hospital_code"),
            ))

        # Get doctors
        doctors_result = retry_on_network_error(
            lambda: supabase.table("doctors")
            .select("id, full_name, specialization, hospital_id, hospitals(hospital_name)")
            .order("full_name")
            .limit(500)
            .execute()
        )

        doctors = []
        for row in doctors_result.data or []:
            doctors.append(DoctorOption(
                id=UUID(row["id"]),
                full_name=row["full_name"],
                specialization=row.get("specialization"),
                hospital_id=UUID(row["hospital_id"]) if row.get("hospital_id") else None,
                hospital_name=row.get("hospitals", {}).get("hospital_name") if row.get("hospitals") else None,
            ))

        return FilterOptionsResponse(
            api_clients=api_clients,
            hospitals=hospitals,
            doctors=doctors,
        )

    except Exception as e:
        logger.error(f"Error fetching filter options: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch filter options")


@router.get("/export")
async def export_usage_csv(
    group_by: str = Query("doctor", description="Group by: api_client, hospital, doctor"),
    date_from: Optional[datetime] = Query(None, description="Start date (inclusive)"),
    date_to: Optional[datetime] = Query(None, description="End date (exclusive)"),
    api_client_id: Optional[UUID] = Query(None, description="Filter by API client"),
    hospital_id: Optional[UUID] = Query(None, description="Filter by hospital"),
    doctor_id: Optional[UUID] = Query(None, description="Filter by doctor"),
    client: ClientContext = Depends(require_admin),
):
    """
    Export usage data as CSV.

    **Admin only** - Exports usage data for billing or reporting purposes.
    """
    from fastapi.responses import StreamingResponse
    import csv
    import io

    if group_by not in ("api_client", "hospital", "doctor"):
        raise HTTPException(
            status_code=400,
            detail="Invalid group_by value. Must be: api_client, hospital, or doctor"
        )

    try:
        # Get all data (no pagination limit for export)
        result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_usage_summary",
                {
                    "p_group_by": group_by,
                    "p_date_from": date_from.isoformat() if date_from else None,
                    "p_date_to": date_to.isoformat() if date_to else None,
                    "p_api_client_id": str(api_client_id) if api_client_id else None,
                    "p_hospital_id": str(hospital_id) if hospital_id else None,
                    "p_doctor_id": str(doctor_id) if doctor_id else None,
                    "p_limit": 10000,  # Large limit for export
                    "p_offset": 0,
                }
            ).execute()
        )

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        headers = [
            "Name", "Type", "Hospital", "API Calls", "Sessions",
            "Cost (USD)", "Cache Savings (USD)", "Input Tokens", "Output Tokens",
            "Recording Hours", "Transcription Hours", "Cache Hit %", "Errors",
            "First Usage", "Last Usage"
        ]
        writer.writerow(headers)

        # Data rows
        for row in result.data or []:
            cache_hit_pct = f"{row.get('avg_cache_hit_ratio', 0):.1f}%" if row.get('avg_cache_hit_ratio') else "N/A"
            writer.writerow([
                row.get("group_name", "Unknown"),
                row.get("group_type", ""),
                row.get("hospital_name", ""),
                row.get("total_api_calls", 0),
                row.get("total_sessions", 0),
                f"${row.get('total_cost_usd', 0):.2f}",
                f"${row.get('total_cache_savings_usd', 0):.2f}",
                row.get("total_input_tokens", 0),
                row.get("total_output_tokens", 0),
                f"{row.get('total_recording_hours', 0):.2f}",
                f"{row.get('total_transcription_hours', 0):.2f}",
                cache_hit_pct,
                row.get("error_count", 0),
                row.get("first_usage_at", ""),
                row.get("last_usage_at", ""),
            ])

        output.seek(0)

        # Generate filename with date range
        filename_parts = [f"usage_by_{group_by}"]
        if date_from:
            filename_parts.append(f"from_{date_from.strftime('%Y%m%d')}")
        if date_to:
            filename_parts.append(f"to_{date_to.strftime('%Y%m%d')}")
        filename = "_".join(filename_parts) + ".csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Error exporting usage data: {e}")
        raise HTTPException(status_code=500, detail="Failed to export usage data")


# ============================================================================
# Model Pricing Endpoints
# ============================================================================

class ModelPricingItem(BaseModel):
    """Model pricing data."""
    model_id: str
    display_name: str
    provider: str
    input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None
    cached_input_price_per_million: Optional[float] = None
    audio_price_per_minute: Optional[float] = None
    thinking_price_per_million: Optional[float] = None
    thinking_budgets: Optional[dict] = None
    is_active: bool = True
    updated_at: Optional[datetime] = None


class PricingUpdateItem(BaseModel):
    """Single model price update."""
    model_id: str
    input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None
    cached_input_price_per_million: Optional[float] = None
    audio_price_per_minute: Optional[float] = None
    thinking_price_per_million: Optional[float] = None
    thinking_budgets: Optional[dict] = None


class PricingUpdateRequest(BaseModel):
    """Bulk pricing update request."""
    updates: List[PricingUpdateItem]


class SuggestedPriceItem(BaseModel):
    """Suggested price from web refresh."""
    model_id: str
    display_name: str
    current: Optional[dict] = None
    suggested: Optional[dict] = None
    source: Optional[str] = None


@models_router.get("/pricing", response_model=List[ModelPricingItem])
async def get_model_pricing(
    client: ClientContext = Depends(require_admin),
):
    """
    Get all model pricing from models_master table.

    **Admin only** - Returns pricing info for all models.
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("models_master")
            .select("model_id, display_name, provider, input_price_per_million, "
                    "output_price_per_million, cached_input_price_per_million, "
                    "audio_price_per_minute, thinking_price_per_million, "
                    "thinking_budgets, is_active, updated_at")
            .order("provider")
            .order("display_order")
            .execute()
        )

        items = []
        for row in result.data or []:
            items.append(ModelPricingItem(
                model_id=row["model_id"],
                display_name=row["display_name"],
                provider=row["provider"],
                input_price_per_million=float(row["input_price_per_million"]) if row.get("input_price_per_million") else None,
                output_price_per_million=float(row["output_price_per_million"]) if row.get("output_price_per_million") else None,
                cached_input_price_per_million=float(row["cached_input_price_per_million"]) if row.get("cached_input_price_per_million") else None,
                audio_price_per_minute=float(row["audio_price_per_minute"]) if row.get("audio_price_per_minute") else None,
                thinking_price_per_million=float(row["thinking_price_per_million"]) if row.get("thinking_price_per_million") else None,
                thinking_budgets=row.get("thinking_budgets"),
                is_active=row.get("is_active", True),
                updated_at=row.get("updated_at"),
            ))

        return items

    except Exception as e:
        logger.error(f"Error fetching model pricing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch model pricing")


@models_router.put("/pricing")
async def update_model_pricing(
    request: PricingUpdateRequest,
    client: ClientContext = Depends(require_admin),
):
    """
    Bulk update model pricing.

    **Admin only** - Updates pricing in models_master and invalidates the pricing cache.
    """
    try:
        updated_count = 0
        for item in request.updates:
            update_data: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}

            if item.input_price_per_million is not None:
                update_data["input_price_per_million"] = item.input_price_per_million
            if item.output_price_per_million is not None:
                update_data["output_price_per_million"] = item.output_price_per_million
            if item.cached_input_price_per_million is not None:
                update_data["cached_input_price_per_million"] = item.cached_input_price_per_million
            if item.audio_price_per_minute is not None:
                update_data["audio_price_per_minute"] = item.audio_price_per_minute
            if item.thinking_price_per_million is not None:
                update_data["thinking_price_per_million"] = item.thinking_price_per_million
            if item.thinking_budgets is not None:
                update_data["thinking_budgets"] = item.thinking_budgets

            result = retry_on_network_error(
                lambda ud=update_data, mid=item.model_id: supabase.table("models_master")
                .update(ud)
                .eq("model_id", mid)
                .execute()
            )
            if result.data:
                updated_count += 1

        # Invalidate pricing cache so new prices take effect
        from services.llm_usage_service import invalidate_pricing_cache, load_pricing_from_db
        invalidate_pricing_cache()
        await load_pricing_from_db()

        return {"message": f"Updated pricing for {updated_count} models", "updated_count": updated_count}

    except Exception as e:
        logger.error(f"Error updating model pricing: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model pricing")


@models_router.post("/pricing/refresh", response_model=List[SuggestedPriceItem])
async def refresh_pricing_from_web(
    client: ClientContext = Depends(require_admin),
):
    """
    Use Gemini with Google Search grounding to fetch latest model pricing.

    **Admin only** - Returns suggested prices for review. Does NOT auto-save.
    """
    try:
        # Get current pricing from DB
        current_result = retry_on_network_error(
            lambda: supabase.table("models_master")
            .select("model_id, display_name, provider, input_price_per_million, "
                    "output_price_per_million, cached_input_price_per_million, "
                    "audio_price_per_minute")
            .eq("is_active", True)
            .execute()
        )

        current_models = current_result.data or []

        # Build model list for the prompt
        model_list = "\n".join([
            f"- {m['display_name']} ({m['model_id']}, provider: {m['provider']})"
            for m in current_models
        ])

        prompt = f"""Search the official pricing pages for Google Gemini API, Anthropic Claude API, and OpenAI API.
Find the current API pricing for these models:

{model_list}

For each model, return the pricing as JSON with this structure:
{{
  "models": [
    {{
      "model_id": "the-model-id",
      "input_price_per_million": <number>,
      "output_price_per_million": <number>,
      "cached_input_price_per_million": <number or null>,
      "audio_price_per_minute": <number or null>,
      "source_url": "url where you found the price"
    }}
  ]
}}

Only include models you can find definitive pricing for. Use USD prices per million tokens.
Return ONLY the JSON, no other text."""

        # Use Gemini with search grounding
        from services.gemini_service import get_gemini_client
        import json

        gemini_client = get_gemini_client()
        from google.genai import types

        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
            ),
        )

        # Parse response
        response_text = response.text.strip()
        # Remove markdown code fences if present
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()

        suggested_data = json.loads(response_text)
        suggested_models = {m["model_id"]: m for m in suggested_data.get("models", [])}

        # Build response with current vs suggested comparison
        items = []
        for model in current_models:
            mid = model["model_id"]
            current = {
                "input_price_per_million": float(model["input_price_per_million"]) if model.get("input_price_per_million") else None,
                "output_price_per_million": float(model["output_price_per_million"]) if model.get("output_price_per_million") else None,
                "cached_input_price_per_million": float(model["cached_input_price_per_million"]) if model.get("cached_input_price_per_million") else None,
                "audio_price_per_minute": float(model["audio_price_per_minute"]) if model.get("audio_price_per_minute") else None,
            }

            suggested = None
            source = None
            if mid in suggested_models:
                s = suggested_models[mid]
                suggested = {
                    "input_price_per_million": s.get("input_price_per_million"),
                    "output_price_per_million": s.get("output_price_per_million"),
                    "cached_input_price_per_million": s.get("cached_input_price_per_million"),
                    "audio_price_per_minute": s.get("audio_price_per_minute"),
                }
                source = s.get("source_url")

            items.append(SuggestedPriceItem(
                model_id=mid,
                display_name=model["display_name"],
                current=current,
                suggested=suggested,
                source=source,
            ))

        return items

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini pricing response: {e}")
        raise HTTPException(status_code=502, detail="Failed to parse pricing data from web search")
    except Exception as e:
        logger.error(f"Error refreshing pricing from web: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh pricing")

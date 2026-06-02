"""
FastAPI Backend for Unizy
Ported from Next.js API routes

Provides REST API endpoints for:
- /api/transcribe: Audio → Transcription + Medical insights
- /api/extract: Direct audio → Medical insights (skip transcription)

Security Features:
- API Key authentication for EHR integrations
- Service JWT authentication for Mobile/Web apps
- Supabase JWT authentication for Admin dashboard
- HIPAA-compliant audit logging
- Rate limiting per client
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables BEFORE importing routers/services
# This ensures USE_VERTEX_AI and other env vars are available during module imports
load_dotenv()

# Configure logging early so factory logs are captured
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

from routers import compare_transcripts
from routers import recording_session
from routers import ephemeral_token
from routers import summary
from routers import counsellors
from routers import extractions
from routers import extraction_photos
from routers import merge
from routers import admin
from routers import processing_modes
from routers import counsellor_templates
from routers import system_prompts
from routers import medicines
from routers import investigations
from routers import student_history
from routers import triage
from routers import recordings
from routers import schools
from routers import assistants
from routers import assistant_templates
from routers import clinical_severity
from routers import other_clinical_needs
from routers import allied_health_needs
from routers import student_dropoff
from routers import care_quality
from routers import ehr_integration
from routers import dashboard_router
from routers import qa
from routers import qa_settings
from routers import usage
from routers import auth_router
from routers import metrics
from routers import poc_metrics
from routers import billing
from routers import procedure_fees
from routers import counsellor_sharing
from routers import radiology_config
from config import validate_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting Unizy Backend...")
    logger.info(f"Python FastAPI version running")

    # Validate settings
    try:
        validate_settings()
        logger.debug("✅ Required environment variables validated")
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        raise

    # Initialize webhook service to log configuration
    from services.webhook_service import webhook_service
    # The initialization log will be printed automatically when imported

    # Check FFmpeg availability for audio stitching
    from services.audio_stitcher import is_ffmpeg_available
    if is_ffmpeg_available():
        logger.info("✅ FFmpeg found - FFmpeg stitching available for schools with it enabled")
    else:
        logger.warning("⚠️  FFmpeg not found - schools with FFmpeg stitching enabled will fall back to simple concatenation")

    # Load LLM pricing from DB into memory cache
    try:
        from services.llm_usage_service import load_pricing_from_db
        model_count = await load_pricing_from_db()
        logger.info(f"✅ Loaded {model_count} model prices from DB")
    except Exception as e:
        logger.warning(f"⚠️  Failed to load pricing from DB, using fallback: {e}")

    # Start periodic cleanup task for in-memory chunk store
    cleanup_task = asyncio.create_task(_periodic_chunk_cleanup())
    logger.info("✅ Chunk memory cleanup task started")

    # Pre-warm Gemini API connection pool (avoids cold-start TCP timeout on first recording)
    try:
        from services.gemini_client_factory import warmup_connection_pool
        await warmup_connection_pool()
        logger.info("✅ Gemini API connection pool warmed up")
    except Exception as e:
        logger.warning(f"⚠️  Gemini connection warmup failed (non-fatal): {e}")

    logger.info("Backend startup complete")
    yield

    # Cleanup on shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down Unizy Backend...")


async def _periodic_chunk_cleanup():
    """
    Periodically clean up expired chunks from in-memory store.

    This runs every 60 seconds to remove chunks older than TTL (5 minutes).
    Prevents memory leaks from abandoned sessions.
    """
    from services.chunk_memory_store import cleanup_expired, get_stats

    while True:
        try:
            await asyncio.sleep(60)  # Run every minute
            expired_count = cleanup_expired()

            # Log stats periodically (every cleanup)
            stats = get_stats()
            if stats["total_sessions"] > 0 or expired_count > 0:
                logger.info(
                    f"[CHUNK_CLEANUP] Stats: sessions={stats['total_sessions']}, "
                    f"chunks={stats['total_chunks']}, memory={stats['estimated_memory_mb']:.1f}MB, "
                    f"expired={expired_count}"
                )
        except asyncio.CancelledError:
            logger.info("[CHUNK_CLEANUP] Cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"[CHUNK_CLEANUP] Error during cleanup: {e}")


# Initialize FastAPI app
app = FastAPI(
    title="Unizy API",
    description=(
        "Recording & Extraction integration API for the Career Counselling "
        "(`CAREER_DISCUSSION`) flow: record a session, upload audio in chunks, and receive "
        "structured extracted insights. Authentication uses OAuth 2.0 client-credentials with "
        "short-lived access tokens and rotating refresh tokens. See the integration guide for the "
        "full request/response contract."
    ),
    version="3.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# ============================================================================
# Security Configuration
# ============================================================================

# Environment-based auth configuration
# Set AUTH_ENABLED=true in production to enable authentication middleware
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"

# CORS Configuration
# In production, specify allowed origins explicitly
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

if CORS_ORIGINS and CORS_ORIGINS[0]:
    # Production: Use whitelist of allowed origins
    logger.debug(f"CORS configured with allowed origins: {CORS_ORIGINS}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
else:
    # Development: Allow all origins
    # ⚠️ WARNING: This allows requests from any domain. Only use for development/testing.
    logger.warning("⚠️ CORS configured to allow ALL origins. Set CORS_ORIGINS env var for production.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # Must be False when allow_origins=["*"]
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Authentication Middleware (optional - enable in production)
if AUTH_ENABLED:
    from middleware.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)
    logger.debug("✅ Authentication middleware enabled")
else:
    logger.warning("⚠️ Authentication middleware DISABLED. Set AUTH_ENABLED=true for production.")

# Include routers - Ephemeral Tokens (for secure client-side Gemini Live API access)
app.include_router(ephemeral_token.router, prefix="/api", tags=["Ephemeral Tokens"])

# Include routers - Live Recording
app.include_router(recording_session.router, tags=["Live Recording"])

# Include routers - Transcript Comparison
app.include_router(compare_transcripts.router, tags=["Transcript Comparison"])

# Include routers - Multi-Consultation Type Summary
app.include_router(summary.router, tags=["Medical Summary - Multi-Type"])

# Include routers - Counsellor Management
app.include_router(counsellors.router, tags=["Counsellor Management"])

# Include routers - Admin Operations
app.include_router(admin.router, tags=["Admin Operations"])

# Include routers - Processing Modes Admin
app.include_router(processing_modes.router, prefix="/api/v1/admin", tags=["Processing Modes Admin"])

# Include routers - Counsellor Templates (Template Sharing & Activation)
app.include_router(counsellor_templates.router, tags=["Counsellor Templates"])

# Include routers - System Prompts (Dynamic Prompt Management)
app.include_router(system_prompts.router, tags=["System Prompts"])

# Include routers - Medicine Lists (Counsellor & School Medicine Management)
app.include_router(medicines.router, tags=["Medicine Lists"])

# Include routers - Investigation Lists (Counsellor & School Investigation Management)
app.include_router(investigations.router, tags=["Investigation Lists"])

# Include routers - Extraction Management (Edit Tracking)
app.include_router(extractions.router, tags=["Extraction Management"])
app.include_router(extraction_photos.router, tags=["Extraction Photos"])

# Include routers - Usage Analytics
app.include_router(usage.router, tags=["Usage Analytics"])

# Include routers - Model Pricing
app.include_router(usage.models_router, tags=["Model Pricing"])

# Include routers - Extraction Merge
app.include_router(merge.router, tags=["Extraction Merge"])

# Include routers - Student History
app.include_router(student_history.router, tags=["Student History"])

# Include routers - Clinical Triage Suggestions
app.include_router(triage.router, tags=["Clinical Triage"])

# Include routers - Recording Management (List & Reprocess)
app.include_router(recordings.router, tags=["Recording Management"])

# Include routers - School Management
app.include_router(schools.router, tags=["School Management"])

# Include routers - Assistant Management
app.include_router(assistants.router, tags=["Assistant Management"])

# Include routers - Assistant Templates
app.include_router(assistant_templates.router, tags=["Assistant Templates"])

# Include routers - Clinical Severity Assessment
app.include_router(clinical_severity.router, tags=["Clinical Severity"])

# Include routers - Other Clinical Needs Assessment
app.include_router(other_clinical_needs.router, tags=["Other Clinical Needs"])

# Include routers - Allied Health Needs Assessment
app.include_router(allied_health_needs.router, tags=["Allied Health Needs"])

# Include routers - Student Dropoff Risk Assessment
app.include_router(student_dropoff.router, tags=["Student Dropoff Risk"])

# Include routers - Care Quality Risk Assessment
app.include_router(care_quality.router, tags=["Care Quality Risk"])

# Include routers - EHR Integration (Sanitized wrapper APIs)
app.include_router(ehr_integration.router, tags=["EHR Integration"])

# Include routers - Dashboard (Intervention Summary & Outcome Tracking)
app.include_router(dashboard_router.router, tags=["Dashboard"])

# Include routers - Q&A Engine (RAG-based medical query system)
app.include_router(qa.router, tags=["Q&A Engine"])
app.include_router(qa_settings.router, tags=["Q&A Settings"])

# Include routers - Auth Proxy (Login/Refresh for external webapps)
app.include_router(auth_router.router, tags=["Auth"])

# Include routers - Quality Metrics (School-scoped AI quality & performance)
app.include_router(metrics.router, tags=["Quality Metrics"])

# Include routers - POC Metrics (Admin screen: tracker + aggregate + timings + xlsx export)
app.include_router(poc_metrics.router, tags=["POC Metrics"])

# Include routers - Billing (Automated bill generation from extractions)
app.include_router(billing.router, tags=["Billing"])

# Include routers - Procedure Fees (School procedure fee master)
app.include_router(procedure_fees.router, tags=["Procedure Fees"])

# Include routers - Counsellor Sharing (Cross-counsellor student sharing)
app.include_router(counsellor_sharing.router, tags=["Counsellor Sharing"])

app.include_router(radiology_config.router, tags=["Radiology Config"])


@app.get("/", tags=["Health Check"])
async def root():
    """Root endpoint - health check"""
    return {
        "service": "Unizy API",
        "version": "3.3.0",
        "status": "running",
        "endpoints": {
            "core": {
                "insights": "/api/insights - Multi-prompt insights extraction",
                "ephemeral_token": "/api/ephemeral-token - Generate ephemeral tokens for client-side Gemini Live API"
            },
            "live_recording": {
                "start": "/api/v1/option1/recording/start - Start recording session",
                "chunk": "/api/v1/option1/recording/chunk - Upload audio chunk",
                "stream": "/api/v1/option1/recording/processing/{id}/stream - SSE progress stream",
                "cancel": "/api/v1/option1/recording/cancel - Cancel session"
            },
            "comparison": {
                "compare": "/api/compare-transcribe - Compare transcript accuracy"
            },
            "summary": {
                "extract": "/api/v1/summary/extract - Dynamic extraction for all consultation types",
                "types": "/api/v1/summary/consultation-types - List available types (OP, DISCHARGE, RESPIRATORY)",
                "segments": "/api/v1/summary/segments/{type} - Configure segments per type",
                "templates": "/api/v1/summary/templates/{type} - Template configurations per type"
            },
            "merge": {
                "merge": "/api/v1/extractions/merge - Merge multiple extractions with AI-powered contextual merging",
                "preview": "/api/v1/extractions/merge/preview - Preview merge without saving",
                "timeline": "/api/v1/extractions/student/{student_id}/timeline - Get student extraction timeline",
                "lineage": "/api/v1/extractions/{extraction_id}/merge-info - Get merge lineage information"
            }
        },
        "docs": "/docs",
        "active_tabs": ["Home (Live Recording)", "Live (Real-time Transcription)", "Compare (Accuracy Testing)"],
        "features": {
            "user_configurable_segments": "Drag-and-drop segment categorization (CORE/ADDITIONAL)",
            "per_segment_brevity": "Control verbosity (concise/balanced/detailed)",
            "terminology_style": "Medical terms vs simple language vs as-spoken",
            "extraction_merge": "AI-powered contextual merge of multiple extractions (NEW in v3.3.0)"
        }
    }


@app.get("/health", tags=["Health Check"])
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Unizy API"
    }


# ============================================================================
# OpenAPI surface restriction (temporary): expose ONLY the documented integration
# endpoints (Docs/RECORDING_EXTRACTION_API.md) via /openapi.json, /docs and /redoc.
# Every other route still functions normally — it is just hidden from the public API
# schema. Unreferenced component schemas are pruned so internal model shapes don't leak.
# ============================================================================
_PUBLIC_API_ENDPOINTS = {
    ("/api/v1/auth/token", "post"),
    ("/api/v1/auth/client-refresh", "post"),
    ("/api/v1/option1/recording/start", "post"),
    ("/api/v1/option1/recording/chunk", "post"),
    ("/api/v1/option1/recording/status/{submission_id}", "get"),
    ("/api/v1/recordings/{session_id}/reprocess", "post"),
}

_default_openapi = app.openapi


def _collect_schema_refs(node, acc):
    """Recursively collect #/components/schemas/<Name> references."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            acc.add(ref.rsplit("/", 1)[-1])
        for v in node.values():
            _collect_schema_refs(v, acc)
    elif isinstance(node, list):
        for v in node:
            _collect_schema_refs(v, acc)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = _default_openapi()
    # 1) keep only the documented (path, method) operations
    kept_paths = {}
    for path, ops in schema.get("paths", {}).items():
        ops_kept = {m: op for m, op in ops.items() if (path, m.lower()) in _PUBLIC_API_ENDPOINTS}
        if ops_kept:
            kept_paths[path] = ops_kept
    schema["paths"] = kept_paths
    # 2) prune component schemas not reachable from the kept operations
    all_schemas = (schema.get("components") or {}).get("schemas") or {}
    referenced = set()
    _collect_schema_refs(kept_paths, referenced)
    changed = True
    while changed:
        changed = False
        for name in list(referenced):
            sub = set()
            _collect_schema_refs(all_schemas.get(name, {}), sub)
            for s in sub - referenced:
                referenced.add(s)
                changed = True
    if schema.get("components", {}).get("schemas") is not None:
        schema["components"]["schemas"] = {n: s for n, s in all_schemas.items() if n in referenced}
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
        access_log=True
    )

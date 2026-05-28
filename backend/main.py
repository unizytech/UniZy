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
from routers import doctors
from routers import extractions
from routers import extraction_photos
from routers import merge
from routers import admin
from routers import processing_modes
from routers import doctor_templates
from routers import system_prompts
from routers import medicines
from routers import investigations
from routers import patient_history
from routers import triage
from routers import recordings
from routers import hospitals
from routers import nurses
from routers import nurse_templates
from routers import clinical_severity
from routers import other_clinical_needs
from routers import allied_health_needs
from routers import patient_dropoff
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
from routers import doctor_sharing
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
        logger.info("✅ FFmpeg found - FFmpeg stitching available for hospitals with it enabled")
    else:
        logger.warning("⚠️  FFmpeg not found - hospitals with FFmpeg stitching enabled will fall back to simple concatenation")

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
    description="""
    Backend API for medical audio transcription and insights extraction using Gemini AI.

    ## Core Endpoints
    - `/api/ephemeral-token` - Generate ephemeral tokens for secure client-side Gemini Live API access

    ## Live Recording Endpoints
    - `/api/v1/option1/recording/start` - Start recording session
    - `/api/v1/option1/recording/chunk` - Upload audio chunk
    - `/api/v1/option1/recording/processing/{id}/stream` - SSE progress stream
    - `/api/v1/option1/recording/cancel` - Cancel recording session

    ## Comparison Endpoints
    - `/api/compare-transcribe` - Compare transcript accuracy (WER/CER metrics)

    ## OP Summary Dynamic Extraction (LEGACY - use /api/v1/summary/* instead)
    - `/api/v1/op/summary-dynamic` - Extract OP summary with user-configurable segments
    - `/api/v1/op/summary-core` - Extract CORE segments only (fast ~25-35s)
    - `/api/v1/op/summary-additional` - Extract ADDITIONAL segments (~30-45s)
    - `/api/v1/op/segments` - List/configure segments with brevity and terminology control
    - `/api/v1/op/templates` - Template configurations (Cardiology, Pediatrics, etc.)

    ## Multi-Consultation Type Summary (NEW - Recommended)
    - `/api/v1/summary/consultation-types` - List available consultation types (OP, DISCHARGE, RESPIRATORY)
    - `/api/v1/summary/extract` - Extract medical summary for any consultation type
    - `/api/v1/summary/segments/{type}` - List/configure segments per consultation type
    - `/api/v1/summary/templates/{type}` - Templates per consultation type
    - `/api/v1/summary/segments/{type}/move` - Move segments between CORE/ADDITIONAL
    - `/api/v1/summary/segments/{type}/reset` - Reset configuration to defaults

    ## Doctor Management
    - `/api/v1/doctors` - List/create doctors
    - `/api/v1/doctors/{id}` - Get/update/delete doctor
    - `/api/v1/doctors/{id}/configurations` - Get doctor's segment configurations (global + consultation-specific)

    ## Extraction Merge (NEW)
    - `/api/v1/extractions/merge` - Merge multiple extractions into consolidated output
    - `/api/v1/extractions/merge/preview` - Preview merge without saving
    - `/api/v1/extractions/patient/{patient_id}/timeline` - Get patient extraction timeline
    - `/api/v1/extractions/{extraction_id}/merge-info` - Get merge lineage information
    """,
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

# Include routers - Doctor Management
app.include_router(doctors.router, tags=["Doctor Management"])

# Include routers - Admin Operations
app.include_router(admin.router, tags=["Admin Operations"])

# Include routers - Processing Modes Admin
app.include_router(processing_modes.router, prefix="/api/v1/admin", tags=["Processing Modes Admin"])

# Include routers - Doctor Templates (Template Sharing & Activation)
app.include_router(doctor_templates.router, tags=["Doctor Templates"])

# Include routers - System Prompts (Dynamic Prompt Management)
app.include_router(system_prompts.router, tags=["System Prompts"])

# Include routers - Medicine Lists (Doctor & Hospital Medicine Management)
app.include_router(medicines.router, tags=["Medicine Lists"])

# Include routers - Investigation Lists (Doctor & Hospital Investigation Management)
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

# Include routers - Patient History
app.include_router(patient_history.router, tags=["Patient History"])

# Include routers - Clinical Triage Suggestions
app.include_router(triage.router, tags=["Clinical Triage"])

# Include routers - Recording Management (List & Reprocess)
app.include_router(recordings.router, tags=["Recording Management"])

# Include routers - Hospital Management
app.include_router(hospitals.router, tags=["Hospital Management"])

# Include routers - Nurse Management
app.include_router(nurses.router, tags=["Nurse Management"])

# Include routers - Nurse Templates
app.include_router(nurse_templates.router, tags=["Nurse Templates"])

# Include routers - Clinical Severity Assessment
app.include_router(clinical_severity.router, tags=["Clinical Severity"])

# Include routers - Other Clinical Needs Assessment
app.include_router(other_clinical_needs.router, tags=["Other Clinical Needs"])

# Include routers - Allied Health Needs Assessment
app.include_router(allied_health_needs.router, tags=["Allied Health Needs"])

# Include routers - Patient Dropoff Risk Assessment
app.include_router(patient_dropoff.router, tags=["Patient Dropoff Risk"])

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

# Include routers - Quality Metrics (Hospital-scoped AI quality & performance)
app.include_router(metrics.router, tags=["Quality Metrics"])

# Include routers - POC Metrics (Admin screen: tracker + aggregate + timings + xlsx export)
app.include_router(poc_metrics.router, tags=["POC Metrics"])

# Include routers - Billing (Automated bill generation from extractions)
app.include_router(billing.router, tags=["Billing"])

# Include routers - Procedure Fees (Hospital procedure fee master)
app.include_router(procedure_fees.router, tags=["Procedure Fees"])

# Include routers - Doctor Sharing (Cross-doctor patient sharing)
app.include_router(doctor_sharing.router, tags=["Doctor Sharing"])

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
                "timeline": "/api/v1/extractions/patient/{patient_id}/timeline - Get patient extraction timeline",
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

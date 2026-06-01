"""
Processing Context for Pipeline Data Passing

This module defines the ProcessingContext dataclass that carries all data
through the processing pipeline, eliminating redundant database queries.

Architecture:
- Context is built ONCE at the start of processing
- Passed through all pipeline stages (stitch -> transcribe -> extract -> save)
- Each stage can read from and update the context
- No redundant database queries within a single processing session
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class TemplateInfo:
    """Template information for extraction"""
    template_id: uuid.UUID
    template_code: str
    template_name: str
    consultation_type_id: uuid.UUID
    consultation_type_code: str


@dataclass
class SessionInfo:
    """Recording session information"""
    session_id: uuid.UUID
    correlation_id: uuid.UUID
    counsellor_id: uuid.UUID
    student_id: str
    status: str
    template_code: str
    template_name: Optional[str]
    transcription_model: str
    extraction_model: str
    extraction_mode: Optional[str]  # 'core', 'additional', 'full', or None
    processing_mode: str
    consultation_type_id: Optional[uuid.UUID]


@dataclass
class AudioData:
    """Audio data after stitching"""
    audio_bytes: bytes
    audio_base64: str
    mime_type: str
    chunk_count: int
    estimated_duration_seconds: float
    total_size_bytes: int


@dataclass
class ExtractionArtifacts:
    """Pre-generated extraction prompts and schemas"""
    system_prompt: str
    gemini_schema: Any  # types.Schema from google-genai
    segment_count: int
    segment_codes: List[str]
    consultation_type_code: str


@dataclass
class ProcessingMetrics:
    """Timing and performance metrics"""
    start_time: float = 0.0
    stitching_time: float = 0.0
    transcription_time: float = 0.0
    extraction_time: float = 0.0
    total_time: float = 0.0


@dataclass
class ProcessingContext:
    """
    Main context object that carries all data through the processing pipeline.

    Usage:
        # Build context once at start
        ctx = await build_processing_context(submission_id)

        # Pass through pipeline
        ctx = await stitch_audio(ctx)
        ctx = await transcribe_audio(ctx)
        ctx = await extract_insights(ctx)
        await save_results(ctx)
    """
    # Core identifiers
    submission_id: uuid.UUID
    job_id: uuid.UUID

    # Session and template info (fetched once)
    session: SessionInfo
    template: Optional[TemplateInfo] = None

    # Audio data (populated after stitching)
    audio: Optional[AudioData] = None

    # Extraction artifacts (pre-generated in parallel with transcription)
    extraction_artifacts: Optional[ExtractionArtifacts] = None

    # Results (populated during processing)
    transcript: Optional[str] = None
    insights: Optional[Dict[str, Any]] = None
    extraction_id: Optional[uuid.UUID] = None

    # Metrics
    metrics: ProcessingMetrics = field(default_factory=ProcessingMetrics)

    # Progress tracking for Realtime updates
    current_status: str = "PENDING"
    current_progress: int = 0
    current_message: str = "Initializing..."

    # Error tracking
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    def update_progress(self, status: str, progress: int, message: str) -> None:
        """Update progress state (will be broadcast via Realtime)"""
        self.current_status = status
        self.current_progress = progress
        self.current_message = message

    def set_error(self, error: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Set error state"""
        self.current_status = "ERROR"
        self.current_progress = 0
        self.error = error
        self.error_details = details
        self.current_message = f"Error: {error}"

    def to_progress_dict(self) -> Dict[str, Any]:
        """Convert current state to progress update dict"""
        result = {
            "status": self.current_status,
            "progress": self.current_progress,
            "message": self.current_message,
        }

        if self.error:
            result["error"] = self.error
            result["error_details"] = self.error_details

        return result

    def to_complete_dict(self) -> Dict[str, Any]:
        """Convert final state to complete event dict"""
        return {
            "status": "COMPLETED",
            "progress": 100,
            "message": "Processing completed successfully",
            "transcript": self.transcript,
            "insights": self.insights,
            "metrics": {
                "stitching_time": round(self.metrics.stitching_time, 2),
                "transcription_time": round(self.metrics.transcription_time, 2),
                "extraction_time": round(self.metrics.extraction_time, 2),
                "total_time": round(self.metrics.total_time, 2),
                "chunk_count": self.audio.chunk_count if self.audio else 0,
                "audio_duration": round(self.audio.estimated_duration_seconds, 2) if self.audio else 0,
            }
        }

"""
Pydantic models for webhook payloads.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class WebhookSessionInfo(BaseModel):
    """Session information included in webhook payload."""

    correlation_id: Optional[str] = Field(None, description="Recording session correlation ID")
    submission_id: Optional[str] = Field(None, description="Processing job submission ID")
    session_id: Optional[str] = Field(None, description="Recording session UUID")
    doctor_id: Optional[str] = Field(None, description="Doctor UUID")
    patient_id: Optional[str] = Field(None, description="Patient identifier")
    template_code: Optional[str] = Field(None, description="Activated template code (unique identifier for DB lookups)")
    template_name: Optional[str] = Field(None, description="Activated template name (display name)")
    extraction_mode: Optional[str] = Field(None, description="Extraction mode (core/additional/full)")
    processing_mode: Optional[str] = Field(None, description="Processing mode code")
    consultation_type_code: Optional[str] = Field(None, description="Consultation type code (OP/IP/etc)")


class WebhookMetadata(BaseModel):
    """Metadata about the webhook event."""

    timestamp: str = Field(..., description="ISO 8601 timestamp of webhook generation")
    source: str = Field(..., description="Source of extraction (recording/direct_extraction)")
    version: str = Field(default="3.1.0", description="API version")


class WebhookPayload(BaseModel):
    """Complete webhook payload structure."""

    insights: Dict[str, Any] = Field(..., description="Extracted medical insights data")
    session_info: WebhookSessionInfo = Field(..., description="Session and context information")
    metadata: WebhookMetadata = Field(..., description="Webhook metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "insights": {
                    "diagnosis": {"data": "Primary diagnosis information"},
                    "chief_complaints": {"data": "Patient complaints"},
                    "prescription": {"data": "Prescribed medications"}
                },
                "session_info": {
                    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "submission_id": "660e8400-e29b-41d4-a716-446655440000",
                    "doctor_id": "770e8400-e29b-41d4-a716-446655440000",
                    "patient_id": "PAT12345",
                    "template_code": "OP_PSYCH_STD_FULL",
                    "template_name": "Psychiatry Standard - Full",
                    "extraction_mode": "full",
                    "processing_mode": "default",
                    "consultation_type_code": "OP"
                },
                "metadata": {
                    "timestamp": "2025-01-07T10:30:00.000Z",
                    "source": "recording",
                    "version": "3.1.0"
                }
            }
        }

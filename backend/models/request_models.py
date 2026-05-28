from pydantic import BaseModel, Field
from typing import Optional, List


class TranscribeRequest(BaseModel):
    """Request model for /api/transcribe endpoint"""
    audioBase64: str = Field(..., description="Base64-encoded audio data")
    mimeType: str = Field(..., description="MIME type of the audio (e.g., audio/wav, audio/mp3)")

    class Config:
        json_schema_extra = {
            "example": {
                "audioBase64": "UklGRiQAAABXQVZFZm10...",
                "mimeType": "audio/wav"
            }
        }


class ExtractRequest(BaseModel):
    """Request model for /api/extract endpoint"""
    audioBase64: str = Field(..., description="Base64-encoded audio data")
    mimeType: str = Field(..., description="MIME type of the audio (e.g., audio/wav, audio/mp3)")

    class Config:
        json_schema_extra = {
            "example": {
                "audioBase64": "UklGRiQAAABXQVZFZm10...",
                "mimeType": "audio/wav"
            }
        }


class CreateConsultationTypeRequest(BaseModel):
    """Request model for creating a new consultation type"""
    type_code: str = Field(..., description="Unique type code (uppercase, underscores)", max_length=50)
    type_name: str = Field(..., description="Display name for the consultation type", max_length=255)
    description: Optional[str] = Field(None, description="Detailed description of the consultation type")
    specialty_applicable: Optional[List[str]] = Field(None, description="List of applicable specialties")
    display_order: int = Field(..., description="Display order in UI (1-100)")
    icon_name: Optional[str] = Field(None, description="Icon name for UI display", max_length=50)
    color_code: Optional[str] = Field(None, description="Color code for UI theme (e.g., #4F46E5)", max_length=20)

    class Config:
        json_schema_extra = {
            "example": {
                "type_code": "EMERGENCY",
                "type_name": "Emergency Consultation",
                "description": "Emergency department consultation and triage",
                "specialty_applicable": ["emergency_medicine", "general_medicine"],
                "display_order": 4,
                "icon_name": "emergency",
                "color_code": "#EF4444"
            }
        }

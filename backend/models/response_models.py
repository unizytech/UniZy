from pydantic import BaseModel, Field
from typing import Optional, Any


class TranscribeResponse(BaseModel):
    """Response model for /api/transcribe endpoint"""
    transcription: str = Field(..., description="Transcribed text from audio")
    insights: Optional[Any] = Field(None, description="Extracted medical insights object")
    speed: float = Field(..., description="Processing time in seconds")
    error: Optional[str] = Field(None, description="Error message if any")


class ExtractResponse(BaseModel):
    """Response model for /api/extract endpoint"""
    insights: Optional[Any] = Field(None, description="Extracted medical insights object")
    speed: float = Field(..., description="Processing time in seconds")
    error: Optional[str] = Field(None, description="Error message if any")


class ErrorResponse(BaseModel):
    """Generic error response model"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")

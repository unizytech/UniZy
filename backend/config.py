"""
Configuration settings for the FastAPI backend.
Loads environment variables and provides centralized settings.
"""

import os
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Gemini API
    gemini_api_key: str = ""

    # Vertex AI Configuration (Production)
    # Set USE_VERTEX_AI=true to use Vertex AI instead of Gemini API
    use_vertex_ai: bool = False
    gcp_project_id: str = ""
    gcp_location: str = "global"

    # Audio Processing Configuration
    max_audio_size_mb: int = 25
    allowed_audio_formats: List[str] = [
        "wav", "mp3", "m4a", "flac", "ogg", "webm", "aac", "opus"
    ]

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"

    # Rate Limiting (for future implementation)
    rate_limit_per_user: int = 100  # calls per hour

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from environment


# Global settings instance
settings = Settings()


def validate_settings():
    """
    Validate that required settings are configured.

    Hybrid Mode:
    - GEMINI_API_KEY is always required (for Live API ephemeral tokens)
    - When USE_VERTEX_AI=true, GCP_PROJECT_ID is also required

    Raises:
        ValueError: If critical settings are missing
    """
    # GEMINI_API_KEY is always required (for Live API in Hybrid Mode)
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")

    # Vertex AI mode requires additional settings
    if settings.use_vertex_ai:
        if not settings.gcp_project_id:
            raise ValueError("GCP_PROJECT_ID required when USE_VERTEX_AI=true")

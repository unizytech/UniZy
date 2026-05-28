"""
Enums for Gemini AI models.
Defines Gemini model options for transcription and insights.
"""

from enum import Enum


class GeminiModel(str, Enum):
    """Gemini model options for transcription and insights"""

    # Gemini 1.5 models (stable)
    PRO_1_5 = "gemini-1.5-pro"
    """Gemini 1.5 Pro - Best quality, slower"""

    FLASH_1_5 = "gemini-1.5-flash"
    """Gemini 1.5 Flash - Balanced speed/quality"""

    FLASH_8B_1_5 = "gemini-1.5-flash-8b"
    """Gemini 1.5 Flash 8B - Fastest, lightweight"""

    # Gemini 2.5 models (recommended)
    FLASH_2_5 = "gemini-2.5-flash"
    """Gemini 2.5 Flash - Recommended default model"""

    PRO_2_5 = "gemini-2.5-pro"
    """Gemini 2.5 Pro - High quality Pro model"""

    # Gemini 3 models
    PRO_3 = "gemini-3-pro"
    """Gemini 3 Pro - Latest Pro model, best quality (Vertex AI)"""

    PRO_3_1_PREVIEW = "gemini-3.1-pro-preview"
    """Gemini 3.1 Pro Preview - Latest Gemini API Pro model"""


class GeminiLiveModel(str, Enum):
    """Gemini Live API specific models for WebSocket streaming"""

    FLASH_NATIVE_AUDIO = "gemini-2.5-flash-native-audio-preview-12-2025"
    """Gemini 2.5 Flash with native audio support - RECOMMENDED for Live API"""

    FLASH_LIVE = "gemini-2.0-flash-live-preview-04-09"
    """Gemini 2.0 Flash Live preview - Alternative Live API model"""

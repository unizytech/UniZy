"""
Transcription User Prompt Generators

This module provides the user prompt generator for plain audio transcription.

The audio-only EMOTION analysis path has been removed — the combined (text+audio)
emotion path is the only emotion path. Only transcription prompts remain here.

Author: Claude Code
Date: 2025-12-04
Updated: 2026-06-01 (Removed audio-only emotion prompts; combined path is the only emotion path)
"""


# ============================================================================
# Transcription-Only User Prompt Templates
# ============================================================================

def generate_transcription_user_prompt(target_language: str = None) -> str:
    """
    Generate user prompt for simple transcription (without emotion analysis).

    The system prompt (TRANSCRIPTION_BASE_PROMPT) is fetched from the database.
    This user prompt specifies the target language and task.

    Args:
        target_language: Target language for transcription (None = original language)

    Returns:
        Formatted user prompt with language-specific instructions
    """
    # Minimal anti-hallucination clause - only triggers on truly empty audio
    anti_hallucination = """
- If the audio file contains absolutely NO human speech (completely silent or only static/noise with zero words), respond with EXACTLY: "[NO_SPEECH_DETECTED]"
- Do NOT fabricate or invent conversations involving generic names like "Dr. Smith", "Mr. Smith", or "Mrs. Smith" - these are hallucination patterns"""

    if target_language:
        return f"""Transcribe this medical consultation audio accurately in {target_language}.

## Requirements:
- If the audio is NOT in {target_language}, translate it to {target_language}
- Output only the transcribed/translated text with speaker labels — no commentary or annotations
{anti_hallucination}"""
    else:
        return f"""Transcribe this medical consultation audio accurately in the original language spoken.

## Requirements:
- Transcribe in the original language of the audio
- Return the transcription without translation
{anti_hallucination}"""

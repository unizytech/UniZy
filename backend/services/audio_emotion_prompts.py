"""
Audio-Based Emotion Analysis - User Prompt Generators and Helper Functions

This module provides user prompt generators for audio emotion analysis.
System prompts and schemas are now stored in the database:
- AUDIO_EMOTION_PROMPT_COMBINED → AUDIO_EMOTION_BASE_PROMPT_COMBINED
- AUDIO_EMOTION_PROMPT_STANDALONE → AUDIO_EMOTION_BASE_PROMPT_STANDALONE

See migrations:
- 20251226090000_add_audio_emotion_base_prompt_components.sql

Features:
- Patient voice anxiety trajectory analysis
- Doctor voice communication style analysis
- Interaction dynamics (turn-taking, flow, engagement)
- Financial concern detection from voice prosody
- Treatment compliance indicators from voice confidence
- Other emotions (fear, anger, sadness, relief) from voice

Author: Claude Code
Date: 2025-12-04
Updated: 2025-12-26 (Moved system prompts and schemas to database)
"""

# NOTE: System prompts (AUDIO_EMOTION_TRANSCRIPTION_SYSTEM_PROMPT, AUDIO_EMOTION_STANDALONE_SYSTEM_PROMPT)
# and schemas (AUDIO_EMOTION_SCHEMA, AUDIO_EMOTION_STANDALONE_SCHEMA) have been moved to the database.
# See migration: 20251226090000_add_audio_emotion_base_prompt_components.sql


# ============================================================================
# User Prompt Templates
# ============================================================================

def generate_audio_emotion_transcription_prompt(target_language: str = "English") -> str:
    """
    Generate user prompt for combined transcription + audio emotion analysis.

    Args:
        target_language: Target language for transcription

    Returns:
        Formatted user prompt
    """
    return f"""Analyze this medical consultation audio.

## Tasks:
1. **Transcribe** the audio accurately in {target_language} with speaker diarization (Doctor: / Patient:)
2. **Analyze** voice characteristics for emotional indicators

## For Each Assessment, Provide:
- The level/category
- A one-line **rationale** explaining the voice evidence
- Your confidence level (Low/Medium/High)

"""


def generate_audio_emotion_standalone_prompt(transcript: str) -> str:
    """
    Generate user prompt for standalone audio emotion analysis (after transcription).

    Args:
        transcript: The transcript for context

    Returns:
        Formatted user prompt
    """
    return f"""Analyze the voice characteristics in this medical consultation audio.

## Transcript (for context):
{transcript}

## Your Task:
Analyze the AUDIO for emotional indicators that may differ from the text.
Focus on voice qualities: tone, pitch, pace, tremor, hesitation, breath patterns.

## For Each Assessment, Provide:
- The level/category
- A one-line **rationale** explaining the specific voice evidence you heard
- Your confidence level based on audio quality

Remember: What someone SAYS may differ from how they SOUND. Focus on VOICE qualities (tone, pitch, pace, tremor, breath) rather than word content."""


# ============================================================================
# Helper Functions
# ============================================================================

def get_audio_emotion_segment_codes() -> list[str]:
    """Get list of all audio emotion segment codes."""
    return [
        "AUDIO_PATIENT_ANXIETY",
        "AUDIO_DOCTOR_STYLE",
        "AUDIO_INTERACTION_DYNAMICS",
        "AUDIO_FINANCIAL_CONCERNS",
        "AUDIO_COMPLIANCE_INDICATORS",
        "AUDIO_OTHER_EMOTIONS"
    ]


def get_audio_emotion_required_fields() -> dict[str, list[str]]:
    """Get required fields for each audio emotion segment."""
    return {
        "AUDIO_PATIENT_ANXIETY": ["initial_anxiety_level", "final_anxiety_level", "anxiety_trajectory", "rationale", "confidence"],
        "AUDIO_DOCTOR_STYLE": ["primary_style", "voice_warmth", "tone_consistency", "rationale", "confidence"],
        "AUDIO_INTERACTION_DYNAMICS": ["turn_taking_balance", "conversation_flow", "mutual_engagement", "rationale", "confidence"],
        "AUDIO_FINANCIAL_CONCERNS": ["severity", "rationale", "confidence"],
        "AUDIO_COMPLIANCE_INDICATORS": ["likelihood", "rationale", "confidence"],
        "AUDIO_OTHER_EMOTIONS": ["dominant_emotion", "emotional_trajectory", "rationale", "confidence"],
    }


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

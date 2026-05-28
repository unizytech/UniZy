"""
Emotion and Subtext Analysis Prompts

Helper functions for text-based emotion analysis.
System prompts and schemas are now database-driven via:
- TEXT_EMOTION_BASE_PROMPT in system_prompt_components
- TEXT_EMOTION_* segments in segment_definitions

Author: Claude Code
Date: 2025-11-11
Updated: 2025-12-26 (removed hardcoded prompts/schemas)
"""


# ============================================================================
# User Prompt Template
# ============================================================================

def generate_emotion_analysis_user_prompt(transcript: str) -> str:
    """
    Generate user prompt for emotion analysis.

    Args:
        transcript: Full consultation transcript

    Returns:
        Formatted user prompt
    """
    return f"""Analyze the following medical consultation transcript and extract emotional and psychological indicators.

Focus on:
1. Pre-consultation anxiety (start of conversation)
2. Post-consultation anxiety (end of conversation)
3. Other medically relevant emotions
4. Financial concerns about treatment
5. Likelihood of treatment compliance
6. Doctor's communication style and its impact on patient

Provide evidence-based assessments with specific quotes and timestamps.

## Transcript:

{transcript}

## Instructions:

Return structured JSON with all 6 emotion segments. Be specific, cite evidence, and indicate confidence levels.

If any information cannot be determined from the transcript, mark confidence as "Low" and note the limitation rather than speculating."""


# ============================================================================
# Helper Functions
# ============================================================================

def get_emotion_segment_codes() -> list[str]:
    """Get list of all text-based emotion segment codes."""
    return [
        "TEXT_EMOTION_ANXIETY_PRE_CONSULTATION",
        "TEXT_EMOTION_ANXIETY_POST_CONSULTATION",
        "TEXT_EMOTION_OTHER_EMOTIONS_DETECTED",
        "TEXT_EMOTION_FINANCIAL_CONCERNS",
        "TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD",
        "TEXT_EMOTION_DOCTOR_COMMUNICATION_STYLE"
    ]


def is_emotion_segment(segment_code: str) -> bool:
    """Check if segment code is an emotion analysis segment (text-based)."""
    return segment_code in get_emotion_segment_codes()


def get_text_emotion_segment_codes() -> list[str]:
    """Alias for get_emotion_segment_codes() - explicit text-based naming."""
    return get_emotion_segment_codes()

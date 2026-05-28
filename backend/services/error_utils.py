"""
Shared error sanitization utilities.

Strips LLM provider names from error messages and collapses noisy
upstream API payloads (429 quota dumps, etc.) into user-safe messages
before they reach the frontend or get stored in the database.
"""

import re

_PROVIDER_NAME_PATTERN = re.compile(
    r'\b(Gemini|Google|Anthropic|Claude|OpenAI|GPT-?\d*\.?\d*)\b',
    re.IGNORECASE
)


def sanitize_error_message(msg: str) -> str:
    """Collapse known LLM error shapes to clean messages, then strip provider names."""
    lowered = msg.lower()

    # Collapse the entire payload to a friendly message when the upstream error
    # is a recognizable category — otherwise the raw dict / URL / status code
    # leaks through after the provider-name sub.
    if "429" in lowered or "resource_exhausted" in lowered or "rate limit" in lowered or "rate_limit" in lowered:
        return "AI service is busy (rate limit) — please retry in a moment."
    if "quota" in lowered or "billing" in lowered:
        return "AI service quota exceeded — please retry later."
    if "401" in lowered or "unauthenticated" in lowered or "permission_denied" in lowered or "api_key" in lowered:
        return "AI service authentication failed."
    if "503" in lowered or "unavailable" in lowered:
        return "AI service temporarily unavailable — please retry."

    sanitized = _PROVIDER_NAME_PATTERN.sub('AI service', msg)
    return sanitized if sanitized.strip() else "An unexpected error occurred"

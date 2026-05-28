"""
Multi-LLM Client Factory

Provides a unified interface for generating structured JSON output from multiple
LLM providers (Gemini, Anthropic/Claude, OpenAI/GPT).

Provider is inferred from model name prefix:
- "claude-*" → Anthropic
- "gpt-*" → OpenAI
- Everything else → Gemini (default)

Usage:
    from services.llm_client_factory import generate_structured_output, generate_json_output

    # Schema-enforced structured output (all providers)
    result = await generate_structured_output(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_schema=schema_dict,
        model=model,
        temperature=0.2
    )

    # Schema-free JSON output (all providers)
    result = await generate_json_output(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=0.2,
    )
"""

import os
import json
import logging
import asyncio
import time
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass

import httpx

from .schema_adapter import adapt_schema_for_openai, adapt_schema_for_claude

logger = logging.getLogger(__name__)


def _sanitize_llm_error(error: Exception, provider: str) -> str:
    """
    Sanitize LLM API errors to prevent internal details from leaking to external APIs.

    Converts detailed API errors (rate limits, org IDs, model names, etc.) to
    user-safe messages while preserving useful error categories.

    Args:
        error: The exception from the LLM API
        provider: "anthropic" or "openai"

    Returns:
        Sanitized error message safe for external consumption
    """
    error_str = str(error).lower()

    # Rate limit errors
    if "rate_limit" in error_str or "rate limit" in error_str or "429" in error_str:
        return "AI service rate limit exceeded. Please retry in a moment."

    # Authentication errors
    if "authentication" in error_str or "api_key" in error_str or "401" in error_str:
        return "AI service authentication failed."

    # Quota/billing errors
    if "quota" in error_str or "billing" in error_str or "insufficient" in error_str:
        return "AI service quota exceeded."

    # Context length / token limit errors
    if "context" in error_str or "token" in error_str and "exceed" in error_str:
        return "AI service: Input too long for model context window."

    # Server errors
    if "500" in error_str or "502" in error_str or "503" in error_str or "server" in error_str:
        return "AI service server error. Please retry."

    # Timeout errors
    if "timeout" in error_str:
        return "AI service request timed out. Please retry."

    # Generic fallback - don't expose raw error
    return "AI service error occurred. Please retry."


def get_provider(model: str) -> str:
    """
    Detect LLM provider from model name prefix.

    Args:
        model: Model identifier string

    Returns:
        Provider string: "anthropic", "openai", or "gemini"
    """
    if model.startswith("claude-"):
        return "anthropic"
    elif model.startswith("gpt-"):
        return "openai"
    else:
        return "gemini"


# Anthropic's hard context limit is 200K tokens; fall back at 180K to leave
# headroom for tool schema, response tokens, and 4-chars/token estimation error.
ANTHROPIC_TOKEN_FALLBACK_THRESHOLD = 180_000
ANTHROPIC_FALLBACK_MODEL = "gemini-2.5-flash"


def _estimate_prompt_tokens(system_prompt: str, user_prompt: str) -> int:
    """Rough token estimate via 4-chars/token heuristic (conservative enough for routing)."""
    return (len(system_prompt or "") + len(user_prompt or "")) // 4


def _resolve_model_for_prompt_size(model: str, system_prompt: str, user_prompt: str) -> str:
    """Pre-flight: if model is Anthropic and the prompt would exceed the context limit,
    reroute to Gemini 2.5 Flash (1M context) without stripping prompt content."""
    if get_provider(model) != "anthropic":
        return model

    estimated_tokens = _estimate_prompt_tokens(system_prompt, user_prompt)
    if estimated_tokens > ANTHROPIC_TOKEN_FALLBACK_THRESHOLD:
        logger.warning(
            f"[LLMFactory] Prompt ~{estimated_tokens} tokens exceeds "
            f"{ANTHROPIC_TOKEN_FALLBACK_THRESHOLD} threshold. "
            f"Rerouting from {model} to {ANTHROPIC_FALLBACK_MODEL}."
        )
        return ANTHROPIC_FALLBACK_MODEL
    return model


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    data: Dict[str, Any]  # Parsed JSON output
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    total_tokens: int
    raw_response: Any  # Provider-specific response object for detailed inspection


async def generate_structured_output(
    system_prompt: str,
    user_prompt: str,
    json_schema: Dict[str, Any],
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 8192,
    cache_key: Optional[str] = None,
    thinking_budget: Optional[int] = None,
) -> LLMResponse:
    """
    Generate structured JSON output using the appropriate provider.

    Routes to Gemini, Claude, or OpenAI based on model prefix.

    Args:
        system_prompt: System instruction text
        user_prompt: User prompt with transcript/content
        json_schema: Standard JSON Schema dict for the expected output
        model: Model identifier (e.g., "gemini-2.5-flash", "claude-sonnet-4-5-20250929", "gpt-4.1-2025-04-14")
        temperature: Generation temperature (0.0-1.0)
        max_tokens: Maximum output tokens

    Returns:
        LLMResponse with parsed data and usage metadata

    Raises:
        Exception: If generation fails or response cannot be parsed
    """
    model = _resolve_model_for_prompt_size(model, system_prompt, user_prompt)
    provider = get_provider(model)

    if provider == "anthropic":
        return await _anthropic_generate(system_prompt, user_prompt, json_schema, model, temperature, max_tokens)
    elif provider == "openai":
        return await _openai_generate(system_prompt, user_prompt, json_schema, model, temperature, max_tokens)
    else:
        return await _gemini_generate(system_prompt, user_prompt, json_schema, model, temperature, cache_key=cache_key, thinking_budget=thinking_budget)


async def generate_json_output(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 8192,
    cache_key: Optional[str] = None,
    thinking_budget: Optional[int] = None,
) -> LLMResponse:
    """
    Generate JSON output without schema enforcement.

    For schema-free JSON calls (triage, compare) where the prompt instructs
    the model to return JSON but no strict schema is enforced.

    Args:
        system_prompt: System instruction text
        user_prompt: User prompt with content
        model: Model identifier
        temperature: Generation temperature (0.0-1.0)
        max_tokens: Maximum output tokens

    Returns:
        LLMResponse with parsed JSON data and usage metadata
    """
    model = _resolve_model_for_prompt_size(model, system_prompt, user_prompt)
    provider = get_provider(model)

    if provider == "anthropic":
        return await _anthropic_json_output(system_prompt, user_prompt, model, temperature, max_tokens)
    elif provider == "openai":
        return await _openai_json_output(system_prompt, user_prompt, model, temperature, max_tokens)
    else:
        return await _gemini_json_output(system_prompt, user_prompt, model, temperature, cache_key=cache_key, thinking_budget=thinking_budget)


async def generate_structured_output_parallel(
    system_prompt: str,
    user_prompt: str,
    json_schema_part1: Dict[str, Any],
    json_schema_part2: Dict[str, Any],
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 8192,
    cache_key: Optional[str] = None,
    thinking_budget: Optional[int] = None,
) -> Tuple[LLMResponse, LLMResponse]:
    """
    Run two structured output calls in parallel for two-part extractions.

    Uses asyncio.gather() to run both extractions concurrently for performance.
    Routes to the appropriate provider (Claude/OpenAI) based on model prefix.

    Args:
        system_prompt: System instruction text (shared by both parts)
        user_prompt: User prompt with transcript/content (shared by both parts)
        json_schema_part1: Standard JSON Schema dict for part 1 output
        json_schema_part2: Standard JSON Schema dict for part 2 output
        model: Model identifier (e.g., "claude-haiku-4-5-20251001", "gpt-4.1-2025-04-14")
        temperature: Generation temperature (default 0.0 for deterministic)
        max_tokens: Maximum output tokens per part

    Returns:
        Tuple of (LLMResponse for part1, LLMResponse for part2)

    Raises:
        Exception: If either extraction fails
    """
    model = _resolve_model_for_prompt_size(model, system_prompt, user_prompt)
    provider = get_provider(model)

    logger.info(f"[LLMFactory] Running parallel two-part extraction with {provider} provider, model: {model}")

    part1_task = generate_structured_output(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_schema=json_schema_part1,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        cache_key=cache_key,
        thinking_budget=thinking_budget,
    )
    part2_task = generate_structured_output(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_schema=json_schema_part2,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        cache_key=cache_key,
        thinking_budget=thinking_budget,
    )

    part1_response, part2_response = await asyncio.gather(part1_task, part2_task)

    logger.info(
        f"[LLMFactory] Parallel extraction complete. "
        f"Part1: {part1_response.total_tokens} tokens, Part2: {part2_response.total_tokens} tokens"
    )

    return part1_response, part2_response


async def _anthropic_generate(
    system_prompt: str,
    user_prompt: str,
    json_schema: Dict[str, Any],
    model: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    """
    Generate structured output using Anthropic Claude via tool use.

    Uses forced tool call to guarantee JSON Schema adherence.
    Includes cache_control on system prompt for automatic prefix caching (90% discount).

    Args:
        system_prompt: System instruction
        user_prompt: User content
        json_schema: Standard JSON Schema for output structure
        model: Claude model identifier
        temperature: Generation temperature
        max_tokens: Max output tokens

    Returns:
        LLMResponse with parsed tool call result
    """
    from anthropic import AsyncAnthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = AsyncAnthropic(api_key=api_key)

    # Create tool definition from schema
    tool_def = adapt_schema_for_claude(json_schema)

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}  # Enable prefix caching
                }
            ],
            tools=[tool_def],
            tool_choice={"type": "tool", "name": tool_def["name"]},
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Extract tool call result
        tool_result = None
        for block in response.content:
            if block.type == "tool_use":
                tool_result = block.input
                break

        if tool_result is None:
            raise Exception("AI service did not return structured output")

        # Extract usage
        usage = response.usage
        input_tokens = getattr(usage, 'input_tokens', 0) or 0
        output_tokens = getattr(usage, 'output_tokens', 0) or 0
        cached_tokens = getattr(usage, 'cache_read_input_tokens', 0) or 0
        cache_creation = getattr(usage, 'cache_creation_input_tokens', 0) or 0
        total_tokens = input_tokens + output_tokens

        logger.info(
            f"[LLMFactory] Claude response: input={input_tokens}, output={output_tokens}, "
            f"cached={cached_tokens}, cache_creation={cache_creation}"
        )

        return LLMResponse(
            data=tool_result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            raw_response=response
        )

    except Exception as e:
        # Log full error for debugging, but sanitize for external consumption
        logger.error(f"[LLMFactory] Anthropic API error (full): {e}")
        sanitized = _sanitize_llm_error(e, "anthropic")
        raise Exception(f"AI extraction failed: {sanitized}")


async def _openai_generate(
    system_prompt: str,
    user_prompt: str,
    json_schema: Dict[str, Any],
    model: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    """
    Generate structured output using OpenAI GPT with json_schema response format.

    Uses strict mode for guaranteed schema adherence.
    OpenAI automatically caches repeated system prompt prefixes (50% discount).

    Args:
        system_prompt: System instruction
        user_prompt: User content
        json_schema: Standard JSON Schema for output structure
        model: GPT model identifier
        temperature: Generation temperature
        max_tokens: Max output tokens

    Returns:
        LLMResponse with parsed JSON content
    """
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = AsyncOpenAI(api_key=api_key)

    # Adapt schema for OpenAI's response_format
    response_format = adapt_schema_for_openai(json_schema)

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        # Parse response content
        content = response.choices[0].message.content
        if not content:
            raise Exception("AI service returned empty response")

        parsed_data = json.loads(content)

        # Extract usage
        usage = response.usage
        input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
        output_tokens = getattr(usage, 'completion_tokens', 0) or 0
        cached_tokens = 0  # OpenAI doesn't expose cached token count directly
        total_tokens = getattr(usage, 'total_tokens', 0) or 0

        # Check for cached tokens in prompt_tokens_details if available
        if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
            cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0) or 0

        logger.info(
            f"[LLMFactory] OpenAI response: input={input_tokens}, output={output_tokens}, "
            f"cached={cached_tokens}, total={total_tokens}"
        )

        return LLMResponse(
            data=parsed_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            raw_response=response
        )

    except json.JSONDecodeError as e:
        logger.error(f"[LLMFactory] Failed to parse OpenAI JSON response: {e}")
        raise Exception("AI service response was not valid JSON")
    except Exception as e:
        # Log full error for debugging, but sanitize for external consumption
        logger.error(f"[LLMFactory] OpenAI API error (full): {e}")
        sanitized = _sanitize_llm_error(e, "openai")
        raise Exception(f"AI extraction failed: {sanitized}")


# ============================================================================
# Gemini Provider Functions
# ============================================================================

def _get_gemini_client():
    """Get the Gemini client (lazy import to avoid circular dependencies)."""
    from services.gemini_client_factory import get_gemini_client
    return get_gemini_client()


async def _gemini_generate(
    system_prompt: str,
    user_prompt: str,
    json_schema: Dict[str, Any],
    model: str,
    temperature: float,
    cache_key: Optional[str] = None,
    thinking_budget: Optional[int] = None,
) -> LLMResponse:
    """
    Generate structured output using Gemini with response_schema enforcement.

    Converts standard JSON Schema to Gemini Schema format internally.
    Supports optional server-side caching via cache_key parameter.

    Args:
        system_prompt: System instruction
        user_prompt: User content
        json_schema: Standard JSON Schema for output structure
        model: Gemini model identifier
        temperature: Generation temperature
        cache_key: Optional cache key for Gemini server-side caching

    Returns:
        LLMResponse with parsed JSON content
    """
    from google.genai import types
    from services.segment_registry import _json_schema_to_gemini_schema

    client = _get_gemini_client()

    # Convert JSON Schema to Gemini Schema
    gemini_schema = _json_schema_to_gemini_schema(json_schema)

    # Attempt server-side caching if cache_key provided
    cache_name = None
    if cache_key:
        from services.gemini_cache_service import get_or_create_cache
        cache_name = get_or_create_cache(
            prompt_type=cache_key,
            system_instruction=system_prompt,
            model=model,
            ttl_seconds=3600
        )

    # Build thinking config only when budget > 0 (capping). 0 or None = use Gemini default
    thinking_config = None
    if thinking_budget is not None and thinking_budget > 0:
        thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)

    try:
        if cache_name:
            config = types.GenerateContentConfig(
                cached_content=cache_name,
                response_mime_type="application/json",
                response_schema=gemini_schema,
                temperature=temperature,
                thinking_config=thinking_config,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=gemini_schema,
                temperature=temperature,
                thinking_config=thinking_config,
            )

        # Retry on transient failures (timeout, connection issues)
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                attempt_start = time.time()
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=config,
                    ),
                    timeout=150.0
                )
                break  # Success — exit retry loop
            except (asyncio.TimeoutError, httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as retry_err:
                attempt_duration = time.time() - attempt_start
                is_timeout = isinstance(retry_err, asyncio.TimeoutError)
                err_label = "Timeout" if is_timeout else "Connection issue"
                if attempt < max_retries:
                    backoff = attempt * 3
                    logger.warning(
                        f"[LLM_RETRY] Attempt {attempt}/{max_retries} failed "
                        f"({err_label}, {attempt_duration:.1f}s). Retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        f"[LLM_RETRY] All {max_retries} attempts failed "
                        f"({err_label}, {attempt_duration:.1f}s). Giving up."
                    )
                    raise  # Re-raise to outer handler

        if not response.text:
            raise Exception("AI service returned empty response")

        parsed_data = json.loads(response.text)

        # Extract usage from response
        usage = response.usage_metadata if hasattr(response, 'usage_metadata') and response.usage_metadata else None
        input_tokens = getattr(usage, 'prompt_token_count', 0) or 0 if usage else 0
        output_tokens = getattr(usage, 'candidates_token_count', 0) or 0 if usage else 0
        cached_tokens = getattr(usage, 'cached_content_token_count', 0) or 0 if usage else 0
        total_tokens = getattr(usage, 'total_token_count', 0) or 0 if usage else 0
        thinking_tokens = getattr(usage, 'thoughts_token_count', 0) or 0 if usage else 0

        logger.info(
            f"[LLM] AI service response: input={input_tokens}, output={output_tokens}, "
            f"cached={cached_tokens}, thinking={thinking_tokens}, total={total_tokens}"
        )

        return LLMResponse(
            data=parsed_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            raw_response=response
        )

    except asyncio.TimeoutError:
        logger.error("[LLM] AI service timed out after 150 seconds (all retries exhausted)")
        raise Exception("AI service timed out after 150 seconds - please retry")
    except json.JSONDecodeError as e:
        logger.error(f"[LLM] Failed to parse AI service JSON response: {e}")
        raise Exception("AI service response was not valid JSON")
    except Exception as e:
        logger.error(f"[LLM] AI service error: {e}")
        sanitized = _sanitize_llm_error(e, "gemini")
        raise Exception(f"AI generation failed: {sanitized}")


async def _gemini_json_output(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    cache_key: Optional[str] = None,
    thinking_budget: Optional[int] = None,
) -> LLMResponse:
    """
    Generate schema-free JSON output using Gemini with response_mime_type only.

    Args:
        system_prompt: System instruction
        user_prompt: User content
        model: Gemini model identifier
        temperature: Generation temperature
        cache_key: Optional cache key for Gemini server-side caching

    Returns:
        LLMResponse with parsed JSON content
    """
    from google.genai import types

    client = _get_gemini_client()

    # Attempt server-side caching if cache_key provided
    cache_name = None
    if cache_key:
        from services.gemini_cache_service import get_or_create_cache
        cache_name = get_or_create_cache(
            prompt_type=cache_key,
            system_instruction=system_prompt,
            model=model,
            ttl_seconds=3600
        )

    # Build thinking config only when budget > 0 (capping). 0 or None = use Gemini default
    thinking_config = None
    if thinking_budget is not None and thinking_budget > 0:
        thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)

    try:
        if cache_name:
            config = types.GenerateContentConfig(
                cached_content=cache_name,
                response_mime_type="application/json",
                temperature=temperature,
                thinking_config=thinking_config,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=temperature,
                thinking_config=thinking_config,
            )

        response = await client.aio.models.generate_content(
            model=model,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=user_prompt)]
                )
            ],
            config=config,
        )

        if not response.text:
            raise Exception("AI service returned empty response")

        # Clean markdown code blocks if present
        result_text = response.text.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]

        parsed_data = json.loads(result_text.strip())

        # Extract usage
        usage = response.usage_metadata if hasattr(response, 'usage_metadata') and response.usage_metadata else None
        input_tokens = getattr(usage, 'prompt_token_count', 0) or 0 if usage else 0
        output_tokens = getattr(usage, 'candidates_token_count', 0) or 0 if usage else 0
        cached_tokens = getattr(usage, 'cached_content_token_count', 0) or 0 if usage else 0
        total_tokens = getattr(usage, 'total_token_count', 0) or 0 if usage else 0
        thinking_tokens = getattr(usage, 'thoughts_token_count', 0) or 0 if usage else 0

        logger.info(
            f"[LLMFactory] Gemini JSON output: input={input_tokens}, output={output_tokens}, "
            f"cached={cached_tokens}, thinking={thinking_tokens}, total={total_tokens}"
        )

        return LLMResponse(
            data=parsed_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            raw_response=response
        )

    except json.JSONDecodeError as e:
        logger.error(f"[LLMFactory] Failed to parse Gemini JSON output: {e}")
        raise Exception("AI service response was not valid JSON")
    except Exception as e:
        logger.error(f"[LLMFactory] Gemini API error: {e}")
        sanitized = _sanitize_llm_error(e, "gemini")
        raise Exception(f"AI generation failed: {sanitized}")


# ============================================================================
# Schema-Free JSON Output (Claude / OpenAI)
# ============================================================================

async def _anthropic_json_output(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    """
    Generate schema-free JSON output using Claude.

    Appends JSON instruction to system prompt and parses text response.
    """
    from anthropic import AsyncAnthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = AsyncAnthropic(api_key=api_key)

    # Append JSON instruction to system prompt
    json_system_prompt = system_prompt + "\n\nIMPORTANT: Respond with valid JSON only. No additional text or markdown."

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=[
                {
                    "type": "text",
                    "text": json_system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Extract text content
        content = ""
        for block in response.content:
            if block.type == "text":
                content = block.text
                break

        if not content:
            raise Exception("AI service returned empty response")

        # Clean and parse JSON
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        parsed_data = json.loads(content.strip())

        # Extract usage
        usage = response.usage
        input_tokens = getattr(usage, 'input_tokens', 0) or 0
        output_tokens = getattr(usage, 'output_tokens', 0) or 0
        cached_tokens = getattr(usage, 'cache_read_input_tokens', 0) or 0
        total_tokens = input_tokens + output_tokens

        logger.info(
            f"[LLMFactory] Claude JSON output: input={input_tokens}, output={output_tokens}, "
            f"cached={cached_tokens}"
        )

        return LLMResponse(
            data=parsed_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            raw_response=response
        )

    except json.JSONDecodeError as e:
        logger.error(f"[LLMFactory] Failed to parse Claude JSON output: {e}")
        raise Exception("AI service response was not valid JSON")
    except Exception as e:
        logger.error(f"[LLMFactory] Anthropic API error (full): {e}")
        sanitized = _sanitize_llm_error(e, "anthropic")
        raise Exception(f"AI generation failed: {sanitized}")


async def _openai_json_output(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    """
    Generate schema-free JSON output using OpenAI with json_object response format.
    """
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = AsyncOpenAI(api_key=api_key)

    # Append JSON instruction (required by OpenAI when using json_object format)
    json_system_prompt = system_prompt + "\n\nRespond with valid JSON only."

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": json_system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        content = response.choices[0].message.content
        if not content:
            raise Exception("AI service returned empty response")

        parsed_data = json.loads(content)

        # Extract usage
        usage = response.usage
        input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
        output_tokens = getattr(usage, 'completion_tokens', 0) or 0
        cached_tokens = 0
        total_tokens = getattr(usage, 'total_tokens', 0) or 0

        if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
            cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0) or 0

        logger.info(
            f"[LLMFactory] OpenAI JSON output: input={input_tokens}, output={output_tokens}, "
            f"cached={cached_tokens}, total={total_tokens}"
        )

        return LLMResponse(
            data=parsed_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            raw_response=response
        )

    except json.JSONDecodeError as e:
        logger.error(f"[LLMFactory] Failed to parse OpenAI JSON output: {e}")
        raise Exception("AI service response was not valid JSON")
    except Exception as e:
        logger.error(f"[LLMFactory] OpenAI API error (full): {e}")
        sanitized = _sanitize_llm_error(e, "openai")
        raise Exception(f"AI generation failed: {sanitized}")

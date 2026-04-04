import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .config import settings
from .prompt_builder import AuditPrompt

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    narrative: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    stop_reason: str


class ClaudeAuditClient:
    """Anthropic Claude API client for audit narrative generation.

    Uses claude-opus-4-6 by default — the most capable model for complex
    compliance reasoning. Switches to claude-sonnet-4-6 for cost-sensitive
    high-volume generation paths.

    Error handling:
    - Rate limits (429): exponential backoff, up to 5 retries
    - Overload (529): same backoff
    - Auth errors (401): fail immediately, never retry (misconfiguration)
    - Timeout: 120s max (long narratives take 30-60s)
    """

    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.generation_model

    @retry(
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIStatusError)),
        wait=wait_exponential(multiplier=2, min=4, max=120),
        stop=stop_after_attempt(5),
        before_sleep=lambda rs: logger.warning(
            "Claude API retry %d/5: %s", rs.attempt_number, rs.outcome.exception()
        ),
    )
    async def generate_narrative(
        self,
        prompt: AuditPrompt,
        max_output_tokens: int = 1024,
    ) -> GenerationResult:
        """Generate an audit narrative using Claude.

        Args:
            prompt: AuditPrompt from AuditPromptBuilder
            max_output_tokens: Max tokens to generate (1024 ~= 750 words)

        Returns:
            GenerationResult with narrative text and token usage.

        Raises:
            anthropic.AuthenticationError: Immediately — never retry, fix config
            anthropic.RateLimitError: After max retries
            anthropic.APITimeoutError: After max retries
        """
        # Don't retry auth errors — they indicate misconfiguration
        start_ms = int(time.monotonic() * 1000)

        try:
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=max_output_tokens,
                system=prompt.system_prompt,
                messages=[{"role": "user", "content": prompt.user_prompt}],
            )
        except anthropic.AuthenticationError:
            logger.error("Claude API authentication failed — check ANTHROPIC_API_KEY")
            raise  # Never retry auth errors

        latency_ms = int(time.monotonic() * 1000) - start_ms

        narrative = message.content[0].text if message.content else ""

        return GenerationResult(
            narrative=narrative,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=latency_ms,
            stop_reason=message.stop_reason or "end_turn",
        )

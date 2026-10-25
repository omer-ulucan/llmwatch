"""
Module: llm_service.py
Purpose: Chat completions for the legacy "qwen" / "gemini" model aliases.
WHY: The chat endpoint still accepts the two original aliases. Both now go through the
provider-neutral OpenAI-compatible client (llmwatch.llm), so token counts are the
ones the provider reports and reasoning text is real or absent, never invented.
The provider/model registry replaces these env-configured aliases next.
"""

from dataclasses import dataclass
from typing import Any, Dict

from llmwatch.config import logger, settings
from llmwatch.exceptions import LLMServiceException
from llmwatch.llm import LLMClient, LLMError, ProviderConfig, Usage, compute_cost

# USD per 1M tokens (input, output) for the legacy aliases.
LEGACY_PRICES: dict[str, tuple[float, float]] = {
    # Self-hosted: $0.0001 per 1K tokens, input and output alike.
    "qwen": (0.10, 0.10),
    "gemini": (0.50, 3.00),
}


@dataclass
class LegacyRoute:
    alias: str
    client: LLMClient
    model_id: str
    preset: str


def _thinking_params(preset: str, thinking_mode: bool) -> dict[str, Any]:
    """Provider-specific knobs for reasoning on/off."""
    if preset == "gemini":
        # Gemini's OpenAI-compatible endpoint maps reasoning_effort onto its
        # thinking levels.
        return {"reasoning_effort": "high" if thinking_mode else "low"}
    return {}


def _messages(preset: str, prompt: str, thinking_mode: bool) -> list[dict[str, str]]:
    messages = []
    if preset == "vllm" and not thinking_mode:
        # WHY: Qwen3-style models honour this soft switch to skip reasoning.
        messages.append({"role": "system", "content": "/no_think"})
    messages.append({"role": "user", "content": prompt})
    return messages


class LLMService:
    """Routes legacy aliases to configured providers."""

    def __init__(self):
        self.routes: Dict[str, LegacyRoute] = {}
        # WHY: Only register providers that are configured, so the server starts
        # without any LLM credentials (zero-config install).
        if settings.google_api_key:
            self.routes["gemini"] = LegacyRoute(
                alias="gemini",
                client=LLMClient(
                    ProviderConfig(
                        name="gemini",
                        base_url=settings.gemini_base_url,
                        api_key=settings.google_api_key,
                        preset="gemini",
                    )
                ),
                model_id=settings.gemini_model,
                preset="gemini",
            )
        # API key is optional for self-hosted or gateway-authenticated deployments.
        if settings.qwen_base_url:
            self.routes["qwen"] = LegacyRoute(
                alias="qwen",
                client=LLMClient(
                    ProviderConfig(
                        name="qwen",
                        base_url=settings.qwen_base_url,
                        api_key=settings.qwen_api_key or None,
                        preset="vllm",
                    )
                ),
                model_id=settings.qwen_model,
                preset="vllm",
            )
        logger.debug(f"LLM aliases configured: {sorted(self.routes)}")

    def calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """
        Computes cost in USD for a legacy alias (0.0 for unknown aliases).
        """
        prices = LEGACY_PRICES.get(model)
        if prices is None:
            return 0.0
        usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
        return compute_cost(usage, *prices) or 0.0

    async def execute_chat(
        self, prompt: str, model: str, thinking_mode: bool
    ) -> Dict[str, Any]:
        """
        Runs one completion for a legacy alias and calculates cost.

        Raises:
            LLMServiceException: For unconfigured aliases or provider failures
                (the normalised LLMError is attached as `.llm_error`).
        """
        route = self.routes.get(model)
        if route is None:
            raise LLMServiceException(
                f"Unsupported model: {model}",
                provider="system",
                http_status=400,
                error_type="unsupported_model",
            )

        try:
            result = await route.client.chat(
                route.model_id,
                _messages(route.preset, prompt, thinking_mode),
                **_thinking_params(route.preset, thinking_mode),
            )
        except LLMError as err:
            exc = LLMServiceException(
                f"{model} generation failed: {err.message}",
                provider=model,
                http_status=err.http_status,
                error_type=err.kind,
                retry_after_s=err.retry_after_s,
            )
            exc.llm_error = err  # type: ignore[attr-defined]
            raise exc from err

        return {
            "response": result.content,
            # WHY: Only what the provider actually returned; None otherwise.
            "thinking_content": result.reasoning if thinking_mode else None,
            "latency_ms": result.latency_ms,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cost_usd": self.calculate_cost(
                model, result.usage.input_tokens, result.usage.output_tokens
            ),
            "model_used": model,
            "thinking_mode": thinking_mode,
        }


llm_service = LLMService()


def get_llm_service() -> LLMService:
    """Lazy factory for LLMService. Enables easy mocking in tests."""
    return llm_service

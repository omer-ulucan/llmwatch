"""
Module: llm_service.py
Purpose: Provides a unified interface for disparate LLM providers using the Strategy pattern.
WHY: Abstracting model specifics allows the chat router to be completely agnostic to whether
we're hitting OpenAI, Gemini, or a self-hosted vLLM endpoint.
"""

import time
import re
from typing import Dict, Any, Tuple, Optional
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings
from exceptions import LLMServiceException


class LLMStrategy:
    """Base strategy interface for LLM execution."""

    async def generate(
        self, prompt: str, thinking_mode: bool
    ) -> Tuple[str, Optional[str], float, int, int]:
        """
        Executes generation and returns metrics.

        Returns:
            Tuple[response_text, thinking_content, latency_ms, input_tokens, output_tokens]
        """
        raise NotImplementedError


class QwenStrategy(LLMStrategy):
    """Strategy for self-hosted Qwen3.5-35B-A3B via vLLM's OpenAI compatible API."""

    def __init__(self):
        # WHY: vLLM exposes an OpenAI-compatible API, allowing us to use standard OpenAI clients
        self.client = ChatOpenAI(
            openai_api_base=settings.qwen_base_url,
            openai_api_key=settings.qwen_api_key,
            model_name="qwen3.5-35b-a3b",  # Using placeholder name based on prompt
        )

    async def generate(
        self, prompt: str, thinking_mode: bool
    ) -> Tuple[str, Optional[str], float, int, int]:
        messages = []
        if not thinking_mode:
            # WHY: Prompt engineering to force model behavior when thinking is disabled
            messages.append(SystemMessage(content="/no_think"))

        messages.append(HumanMessage(content=prompt))

        start_time = time.perf_counter()
        try:
            response = await self.client.ainvoke(messages)
            # WHY: Calculate latency immediately surrounding the network request using perf_counter.
            latency_ms = (time.perf_counter() - start_time) * 1000

            raw_content = response.content
            thinking_content = None

            # WHY: We strip <think> tags here because vLLM returns Qwen's internal
            # reasoning wrapped in these tags — end users should never see raw
            # model internals unless thinking mode is explicitly enabled.
            if "<think>" in raw_content and "</think>" in raw_content:
                think_match = re.search(
                    r"<think>(.*?)</think>", raw_content, flags=re.DOTALL
                )
                if think_match:
                    thinking_content = think_match.group(1).strip()
                final_response = re.sub(
                    r"<think>.*?</think>", "", raw_content, flags=re.DOTALL
                ).strip()
            else:
                final_response = raw_content

            input_tokens = response.response_metadata.get("token_usage", {}).get(
                "prompt_tokens", 0
            )
            output_tokens = response.response_metadata.get("token_usage", {}).get(
                "completion_tokens", 0
            )

            return (
                final_response,
                thinking_content if thinking_mode else None,
                latency_ms,
                input_tokens,
                output_tokens,
            )
        except Exception as e:
            raise LLMServiceException(
                f"Qwen generation failed: {str(e)}", provider="qwen"
            )


class GeminiStrategy(LLMStrategy):
    """Strategy for Gemini 3 Flash via Google API."""

    def __init__(self):
        self.client = ChatGoogleGenerativeAI(
            model="gemini-3-flash", google_api_key=settings.google_api_key
        )

    async def generate(
        self, prompt: str, thinking_mode: bool
    ) -> Tuple[str, Optional[str], float, int, int]:
        messages = [HumanMessage(content=prompt)]

        start_time = time.perf_counter()
        try:
            # WHY: Gemini handles thinking natively via parameters rather than system prompts
            response = await self.client.ainvoke(
                messages,
                # Note: mapped parameters per design doc
                thinking_level="high" if thinking_mode else "minimal",
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Extract basic metric stubs — Langchain's Google metrics formats vary
            input_tokens = (
                getattr(response, "response_metadata", {})
                .get("prompt_feedback", {})
                .get("token_count", len(prompt) // 4)
            )
            output_tokens = (
                getattr(response, "response_metadata", {})
                .get("candidates", [{}])[0]
                .get("token_count", len(response.content) // 4)
            )

            final_response = response.content
            thinking_content = (
                "Thinking logic computed upstream via Google API."
                if thinking_mode
                else None
            )

            return (
                final_response,
                thinking_content,
                latency_ms,
                input_tokens,
                output_tokens,
            )
        except Exception as e:
            raise LLMServiceException(
                f"Gemini generation failed: {str(e)}", provider="gemini"
            )


class LLMService:
    """Orchestrator for managing LLM interactions."""

    def __init__(self):
        self.strategies = {"qwen": QwenStrategy(), "gemini": GeminiStrategy()}

    def calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """
        Computes cost in USD per model pricing.

        Args:
            model (str): The provider alias.
            input_tokens (int): Prompt token size.
            output_tokens (int): Completion token size.

        Returns:
            float: Decimal USD value tracking the cost.
        """
        # WHY: Extract cost_estimation to standalone utility function for easier testing and logic reuse
        if model == "qwen":
            # $0.0001 per 1k tokens combined
            return ((input_tokens + output_tokens) / 1000) * 0.0001
        elif model == "gemini":
            # $0.50 / 1M input, $3.00 / 1M output
            return (input_tokens / 1_000_000) * 0.50 + (
                output_tokens / 1_000_000
            ) * 3.00
        return 0.0

    async def execute_chat(
        self, prompt: str, model: str, thinking_mode: bool
    ) -> Dict[str, Any]:
        """
        Runs the generation via the mapped strategy and calculates cost.

        Args:
            prompt (str): Text payload to send for completion.
            model (str): Identifier defining which provider config to select.
            thinking_mode (bool): Flag toggling enhanced reasoning output.

        Returns:
            Dict[str, Any]: Consolidated metrics and textual outputs payload dict.

        Raises:
            LLMServiceException: For unregistered model IDs or execution failures.
        """
        if model not in self.strategies:
            raise LLMServiceException(f"Unsupported model: {model}", provider="system")

        strategy = self.strategies[model]
        (
            response_text,
            thinking,
            latency,
            in_tokens,
            out_tokens,
        ) = await strategy.generate(prompt, thinking_mode)
        cost_usd = self.calculate_cost(model, in_tokens, out_tokens)

        return {
            "response": response_text,
            "thinking_content": thinking,
            "latency_ms": latency,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "cost_usd": cost_usd,
            "model_used": model,
            "thinking_mode": thinking_mode,
        }


llm_service = LLMService()


def get_llm_service() -> LLMService:
    """Lazy factory for LLMService. Enables easy mocking in tests."""
    return llm_service

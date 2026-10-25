"""
Tests for the LLM service layer: cost calculation and execute_chat routing.

NOTE: No network: execute_chat runs against tests.fake_llm.FakeProvider.
"""

from unittest.mock import patch

import pytest

from llmwatch.exceptions import LLMServiceException
from llmwatch.services.llm_service import LegacyRoute, LLMService
from tests.fake_llm import FakeProvider

# ── Cost calculation ─────────────────────────────────────────────────────


class TestCalculateCost:
    def setup_method(self):
        # Patch out the __init__ to avoid hitting real APIs
        with patch.object(LLMService, "__init__", lambda self: None):
            self.svc = LLMService()
            self.svc.strategies = {}

    def test_qwen_cost(self):
        # $0.0001 per 1k tokens combined
        cost = self.svc.calculate_cost("qwen", 500, 500)
        assert cost == pytest.approx(0.0001)

    def test_gemini_cost(self):
        # $0.50 / 1M input + $3.00 / 1M output
        cost = self.svc.calculate_cost("gemini", 1_000_000, 1_000_000)
        assert cost == pytest.approx(3.50)

    def test_gemini_zero_tokens(self):
        cost = self.svc.calculate_cost("gemini", 0, 0)
        assert cost == 0.0

    def test_unknown_model_returns_zero(self):
        cost = self.svc.calculate_cost("gpt4", 100, 100)
        assert cost == 0.0


# ── execute_chat (against a fake OpenAI-compatible provider) ────────────


def _service_with(fake, alias="gemini", preset="gemini"):
    with patch.object(LLMService, "__init__", lambda self: None):
        svc = LLMService()
    svc.routes = {
        alias: LegacyRoute(
            alias=alias, client=fake.client(), model_id=f"{alias}-model", preset=preset
        )
    }
    return svc


class TestExecuteChat:
    async def test_unsupported_model_raises(self):
        with patch.object(LLMService, "__init__", lambda self: None):
            svc = LLMService()
        svc.routes = {}
        with pytest.raises(LLMServiceException) as exc_info:
            await svc.execute_chat("hi", "nonexistent", False)
        assert "Unsupported model" in exc_info.value.message

    async def test_returns_reported_usage_and_cost(self):
        fake = FakeProvider().reply("Paris", usage=(1_000_000, 1_000_000))
        result = await _service_with(fake).execute_chat("capital?", "gemini", False)

        assert result["response"] == "Paris"
        assert result["input_tokens"] == 1_000_000
        assert result["output_tokens"] == 1_000_000
        assert result["cost_usd"] == pytest.approx(3.50)
        assert result["model_used"] == "gemini"
        assert result["thinking_mode"] is False
        assert result["latency_ms"] >= 0
        assert fake.requests[-1]["model"] == "gemini-model"

    async def test_gemini_tokens_are_not_estimated_from_text_length(self):
        """Regression: missing Gemini usage fell back to len(text) // 4."""
        fake = FakeProvider().reply("x" * 4000, usage=None)
        result = await _service_with(fake).execute_chat("q" * 400, "gemini", False)
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0

    async def test_gemini_thinking_is_real_or_absent(self):
        """Regression: thinking content used to be a hardcoded string."""
        fake = FakeProvider().reply("answer")
        result = await _service_with(fake).execute_chat("q", "gemini", True)
        assert result["thinking_content"] is None
        assert fake.requests[-1]["reasoning_effort"] == "high"

        fake.reply("<thought>weighing options</thought>answer")
        result = await _service_with(fake).execute_chat("q", "gemini", True)
        assert result["response"] == "answer"
        assert result["thinking_content"] == "weighing options"

    async def test_thinking_hidden_when_mode_off(self):
        fake = FakeProvider().reply("answer", reasoning="secret steps")
        result = await _service_with(fake).execute_chat("q", "gemini", False)
        assert result["thinking_content"] is None
        assert result["response"] == "answer"
        assert fake.requests[-1]["reasoning_effort"] == "low"

    async def test_qwen_no_think_switch(self):
        fake = FakeProvider().reply("hi").reply("hi")
        svc = _service_with(fake, alias="qwen", preset="vllm")
        await svc.execute_chat("q", "qwen", False)
        assert fake.requests[-1]["messages"][0] == {
            "role": "system",
            "content": "/no_think",
        }
        await svc.execute_chat("q", "qwen", True)
        assert fake.requests[-1]["messages"] == [{"role": "user", "content": "q"}]

    async def test_provider_errors_carry_the_normalized_error(self):
        fake = FakeProvider().fail(429, message="slow down", retry_after="5")
        with pytest.raises(LLMServiceException) as info:
            await _service_with(fake).execute_chat("q", "gemini", False)
        assert info.value.llm_error.kind == "rate_limit"
        assert info.value.llm_error.retry_after_s == 5.0

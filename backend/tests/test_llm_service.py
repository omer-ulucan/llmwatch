"""
Tests for the LLM service layer: cost calculation and execute_chat routing.

NOTE: We do NOT instantiate real LLM strategies (they require network).
      Instead we test LLMService.calculate_cost directly and mock
      strategy.generate for execute_chat.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.llm_service import LLMService, LLMStrategy
from exceptions import LLMServiceException


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


# ── execute_chat ─────────────────────────────────────────────────────────


class TestExecuteChat:
    def setup_method(self):
        with patch.object(LLMService, "__init__", lambda self: None):
            self.svc = LLMService()
            self.svc.strategies = {}

    @pytest.mark.asyncio
    async def test_unsupported_model_raises(self):
        with pytest.raises(LLMServiceException) as exc_info:
            await self.svc.execute_chat("hi", "nonexistent", False)
        assert "Unsupported model" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_delegates_to_strategy(self):
        mock_strategy = MagicMock(spec=LLMStrategy)
        mock_strategy.generate = AsyncMock(
            return_value=("response text", None, 42.0, 10, 20)
        )
        self.svc.strategies["fake"] = mock_strategy

        result = await self.svc.execute_chat("hello", "fake", False)

        mock_strategy.generate.assert_awaited_once_with("hello", False)
        assert result["response"] == "response text"
        assert result["latency_ms"] == 42.0
        assert result["input_tokens"] == 10
        assert result["output_tokens"] == 20
        assert result["model_used"] == "fake"
        assert result["thinking_mode"] is False

    @pytest.mark.asyncio
    async def test_thinking_mode_forwarded(self):
        mock_strategy = MagicMock(spec=LLMStrategy)
        mock_strategy.generate = AsyncMock(
            return_value=("answer", "thought", 10.0, 5, 5)
        )
        self.svc.strategies["fake"] = mock_strategy

        result = await self.svc.execute_chat("q", "fake", True)
        assert result["thinking_content"] == "thought"
        assert result["thinking_mode"] is True
